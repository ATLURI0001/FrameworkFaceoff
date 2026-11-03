#pragma once

#include <liburing.h>
#include "constants.h"
#include "queue.h"
#include "connection.h"

typedef void (*handler_fn)(conn_t *conn, uint8_t *buf, int len);

typedef struct reactor {
    int                          id;
    struct io_uring              ring;
    struct io_uring_buf_ring    *buf_ring;
    uint8_t                     *buf_slab;
    uint32_t                     buf_index;
    uint32_t                     buf_mask;

    int                          recv_buf_size;
    int                          buf_ring_entries;
    int                          ring_entries;
    int                          batch_cqes;
    int                          max_connections;

    conn_t                     **conns;          /* sparse fd → conn_t* */
    spsc_queue_t                 new_fd_queue;   /* acceptor → reactor */

    handler_fn                   handler;
    volatile int                *running;
} reactor_t;

void reactor_init(reactor_t *r, int id, volatile int *running, handler_fn handler);
void reactor_loop(reactor_t *r);
void reactor_submit_send(reactor_t *r, int fd, uint8_t *buf, int off, int target);
void reactor_destroy(reactor_t *r);
