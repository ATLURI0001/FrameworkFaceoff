#include "reactor.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <netinet/tcp.h>

/* ── helpers ───────────────────────────────────────────────────────── */

static inline struct io_uring_sqe *sqe_get(struct io_uring *ring)
{
    struct io_uring_sqe *sqe = io_uring_get_sqe(ring);
    if (__builtin_expect(!sqe, 0)) {
        io_uring_submit(ring);
        sqe = io_uring_get_sqe(ring);
    }
    return sqe;
}

static inline void arm_recv_multishot(struct io_uring *ring, int fd)
{
    struct io_uring_sqe *sqe = sqe_get(ring);
    io_uring_prep_recv_multishot(sqe, fd, NULL, 0, 0);
    sqe->flags    |= IOSQE_BUFFER_SELECT;
    sqe->buf_group = BUFFER_RING_BGID;
    io_uring_sqe_set_data64(sqe, PACK_UD(UD_RECV, fd));
}

static inline void return_buffer(reactor_t *r, uint16_t bid)
{
    uint8_t *addr = r->buf_slab + (size_t)bid * r->recv_buf_size;
    io_uring_buf_ring_add(r->buf_ring, addr, r->recv_buf_size,
                          bid, r->buf_mask, r->buf_index++);
    io_uring_buf_ring_advance(r->buf_ring, 1);
}

static inline void cancel_recv(reactor_t *r, int fd)
{
    struct io_uring_sqe *sqe = io_uring_get_sqe(&r->ring);
    if (!sqe) return;
    io_uring_prep_cancel64(sqe, PACK_UD(UD_RECV, fd), 0);
    io_uring_sqe_set_data64(sqe, PACK_UD(UD_CANCEL, fd));
}

/* ── init ──────────────────────────────────────────────────────────── */

void reactor_init(reactor_t *r, int id, volatile int *running, handler_fn handler)
{
    memset(r, 0, sizeof(*r));
    r->id               = id;
    r->running          = running;
    r->handler          = handler;
    r->recv_buf_size    = DEFAULT_RECV_BUF_SIZE;
    r->buf_ring_entries = DEFAULT_BUF_RING_ENTRIES;
    r->ring_entries     = DEFAULT_REACTOR_RING_ENTRIES;
    r->batch_cqes       = DEFAULT_BATCH_CQES;
    r->max_connections  = DEFAULT_MAX_CONNECTIONS;

    /* io_uring: SINGLE_ISSUER | DEFER_TASKRUN — must be inited on this thread */
    struct io_uring_params params;
    memset(&params, 0, sizeof(params));
    params.flags = IORING_SETUP_SINGLE_ISSUER | IORING_SETUP_DEFER_TASKRUN;

    int ret = io_uring_queue_init_params(r->ring_entries, &r->ring, &params);
    if (ret < 0) {
        fprintf(stderr, "[r%d] io_uring_queue_init: %s\n", id, strerror(-ret));
        exit(1);
    }

    /* Provided buffer ring */
    int bret;
    r->buf_ring = io_uring_setup_buf_ring(&r->ring, r->buf_ring_entries,
                                          BUFFER_RING_BGID, 0, &bret);
    if (!r->buf_ring) {
        fprintf(stderr, "[r%d] setup_buf_ring: %s\n", id, strerror(-bret));
        exit(1);
    }

    r->buf_mask = (uint32_t)(r->buf_ring_entries - 1);
    size_t slab_size = (size_t)r->buf_ring_entries * r->recv_buf_size;
    r->buf_slab = (uint8_t *)aligned_alloc(64, slab_size);
    memset(r->buf_slab, 0, slab_size);

    /* Pre-fill every buffer slot */
    for (int i = 0; i < r->buf_ring_entries; i++) {
        uint8_t *addr = r->buf_slab + (size_t)i * r->recv_buf_size;
        io_uring_buf_ring_add(r->buf_ring, addr, r->recv_buf_size,
                              i, r->buf_mask, r->buf_index++);
    }
    io_uring_buf_ring_advance(r->buf_ring, r->buf_ring_entries);

    /* Connections array (sparse, indexed by fd) */
    r->conns = (conn_t **)calloc(r->max_connections, sizeof(conn_t *));

    /* SPSC queue for acceptor → reactor fd handoff */
    spsc_init(&r->new_fd_queue, 8192);

    fprintf(stderr, "[r%d] initialized\n", id);
}

/* ── send ──────────────────────────────────────────────────────────── */

void reactor_submit_send(reactor_t *r, int fd, uint8_t *buf, int off, int target)
{
    struct io_uring_sqe *sqe = sqe_get(&r->ring);
    io_uring_prep_send(sqe, fd, buf + off, target - off, MSG_NOSIGNAL);
    io_uring_sqe_set_data64(sqe, PACK_UD(UD_SEND, fd));
}

/* ── main event loop ───────────────────────────────────────────────── */

void reactor_loop(reactor_t *r)
{
    struct io_uring_cqe *cqes[DEFAULT_BATCH_CQES];
    struct __kernel_timespec ts = { .tv_sec = 0, .tv_nsec = 1000000 }; /* 1 ms */

    while (*r->running) {

        /* 1. Drain new connections from acceptor */
        int new_fd;
        while (spsc_dequeue(&r->new_fd_queue, &new_fd)) {
            if (new_fd >= r->max_connections) {
                close(new_fd);
                continue;
            }
            conn_t *c = (conn_t *)calloc(1, sizeof(conn_t));
            conn_init(c, new_fd, r);
            r->conns[new_fd] = c;
            arm_recv_multishot(&r->ring, new_fd);
        }

        /* 2. Peek batch CQEs (submit pending + trigger GETEVENTS) */
        unsigned got = io_uring_peek_batch_cqe(&r->ring, cqes, r->batch_cqes);
        if (got == 0) {
            /* Submit pending SQEs and wait with timeout */
            struct io_uring_cqe *wait_cqe;
            io_uring_submit_and_wait_timeout(&r->ring, &wait_cqe, 1, &ts, NULL);
            got = io_uring_peek_batch_cqe(&r->ring, cqes, r->batch_cqes);
            if (got == 0) continue;
        }

        /* 3. Process CQEs */
        for (unsigned i = 0; i < got; i++) {
            struct io_uring_cqe *cqe = cqes[i];
            uint64_t   ud   = cqe->user_data;
            ud_kind_t  kind = UD_KIND(ud);
            int        res  = cqe->res;

            if (kind == UD_RECV) {
                int fd         = UD_FD(ud);
                int has_buffer = (cqe->flags & IORING_CQE_F_BUFFER) != 0;
                int has_more   = (cqe->flags & IORING_CQE_F_MORE)   != 0;

                if (res <= 0) {
                    if (has_buffer) {
                        uint16_t bid = cqe->flags >> IORING_CQE_BUFFER_SHIFT;
                        return_buffer(r, bid);
                    }
                    if (fd < r->max_connections && r->conns[fd]) {
                        conn_destroy(r->conns[fd]);
                        free(r->conns[fd]);
                        r->conns[fd] = NULL;
                        cancel_recv(r, fd);
                        close(fd);
                    }
                    continue;
                }

                if (!has_buffer) continue;

                uint16_t bid = cqe->flags >> IORING_CQE_BUFFER_SHIFT;

                if (fd < r->max_connections && r->conns[fd]) {
                    conn_t  *c   = r->conns[fd];
                    uint8_t *buf = r->buf_slab + (size_t)bid * r->recv_buf_size;

                    /* Handler runs synchronously on reactor thread */
                    r->handler(c, buf, res);

                    /* Return recv buffer to kernel immediately */
                    return_buffer(r, bid);

                    /* Re-arm multishot recv if kernel stopped it */
                    if (!has_more)
                        arm_recv_multishot(&r->ring, fd);
                } else {
                    return_buffer(r, bid);
                }

            } else if (kind == UD_SEND) {
                int fd = UD_FD(ud);
                if (fd >= r->max_connections || !r->conns[fd]) continue;

                conn_t *c = r->conns[fd];

                if (res <= 0) {
                    c->send_inflight = 0;
                    continue;
                }

                c->write_head += res;
                int target = c->write_target;

                if (c->write_head < target) {
                    /* Partial send — resubmit remainder */
                    reactor_submit_send(r, fd, c->write_buf,
                                        c->write_head, target);
                    continue;
                }

                /* Send complete */
                c->send_inflight = 0;
                c->write_target  = 0;
                conn_reset_write(c);
            }
            /* UD_CANCEL: no-op */
        }

        io_uring_cq_advance(&r->ring, got);
    }

    /* ── shutdown: close all connections ───────────────────────────── */
    for (int i = 0; i < r->max_connections; i++) {
        if (r->conns[i]) {
            close(r->conns[i]->fd);
            conn_destroy(r->conns[i]);
            free(r->conns[i]);
            r->conns[i] = NULL;
        }
    }
    fprintf(stderr, "[r%d] shutdown complete\n", r->id);
}

/* ── cleanup ───────────────────────────────────────────────────────── */

void reactor_destroy(reactor_t *r)
{
    io_uring_free_buf_ring(&r->ring, r->buf_ring,
                           r->buf_ring_entries, BUFFER_RING_BGID);
    io_uring_queue_exit(&r->ring);
    free(r->buf_slab);
    free(r->conns);
    spsc_destroy(&r->new_fd_queue);
}
