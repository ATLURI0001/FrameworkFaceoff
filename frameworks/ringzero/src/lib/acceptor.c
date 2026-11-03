#include "acceptor.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>

void acceptor_init(acceptor_t *a, int listen_fd, volatile int *running)
{
    memset(a, 0, sizeof(*a));
    a->listen_fd   = listen_fd;
    a->running     = running;
    a->ring_entries = DEFAULT_ACCEPTOR_RING_ENTRIES;
    a->batch_cqes  = DEFAULT_BATCH_CQES;

    int ret = io_uring_queue_init(a->ring_entries, &a->ring, 0);
    if (ret < 0) {
        fprintf(stderr, "[acceptor] io_uring_queue_init: %s\n", strerror(-ret));
        exit(1);
    }

    /* Arm multishot accept (SOCK_NONBLOCK for accepted fds) */
    struct io_uring_sqe *sqe = io_uring_get_sqe(&a->ring);
    io_uring_prep_multishot_accept(sqe, listen_fd, NULL, NULL, SOCK_NONBLOCK);
    io_uring_sqe_set_data64(sqe, PACK_UD(UD_ACCEPT, listen_fd));
    io_uring_submit(&a->ring);

    fprintf(stderr, "[acceptor] initialized\n");
}

void acceptor_loop(acceptor_t *a, reactor_t *reactors, int reactor_count)
{
    struct io_uring_cqe *cqes[DEFAULT_BATCH_CQES];
    struct __kernel_timespec ts = { .tv_sec = 0, .tv_nsec = 100000000 }; /* 100 ms */
    int next_reactor = 0;
    int one = 1;

    while (*a->running) {
        io_uring_submit(&a->ring);

        unsigned got = io_uring_peek_batch_cqe(&a->ring, cqes, a->batch_cqes);
        if (got == 0) {
            struct io_uring_cqe *wait_cqe;
            io_uring_wait_cqe_timeout(&a->ring, &wait_cqe, &ts);
            got = io_uring_peek_batch_cqe(&a->ring, cqes, a->batch_cqes);
            if (got == 0) continue;
        }

        for (unsigned i = 0; i < got; i++) {
            struct io_uring_cqe *cqe = cqes[i];
            uint64_t   ud   = cqe->user_data;
            ud_kind_t  kind = UD_KIND(ud);
            int        res  = cqe->res;

            if (kind == UD_ACCEPT) {
                if (res >= 0) {
                    int client_fd = res;
                    setsockopt(client_fd, IPPROTO_TCP, TCP_NODELAY,
                               &one, sizeof(one));

                    int target = next_reactor;
                    next_reactor = (next_reactor + 1) % reactor_count;

                    while (!spsc_enqueue(&reactors[target].new_fd_queue, client_fd))
                        ;
                } else {
                    fprintf(stderr, "[acceptor] accept error: %d (%s)\n",
                            res, strerror(-res));
                }

                /* Re-arm if kernel dropped multishot */
                if (!(cqe->flags & IORING_CQE_F_MORE)) {
                    struct io_uring_sqe *sqe = io_uring_get_sqe(&a->ring);
                    io_uring_prep_multishot_accept(sqe, a->listen_fd,
                                                   NULL, NULL, SOCK_NONBLOCK);
                    io_uring_sqe_set_data64(sqe, PACK_UD(UD_ACCEPT, a->listen_fd));
                }
            }
        }

        io_uring_cq_advance(&a->ring, got);

        /* Flush any pending SQEs (e.g. re-armed accept) */
        if (io_uring_sq_ready(&a->ring) > 0)
            io_uring_submit(&a->ring);
    }

    close(a->listen_fd);
    fprintf(stderr, "[acceptor] shutdown complete\n");
}

void acceptor_destroy(acceptor_t *a)
{
    io_uring_queue_exit(&a->ring);
}
