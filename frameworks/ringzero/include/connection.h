#pragma once

#include <stdint.h>

typedef struct reactor reactor_t;

typedef struct conn {
    int          fd;
    reactor_t   *reactor;

    /* Write side (mirrors terraform/Connection/Connection.Write.cs) */
    uint8_t     *write_buf;
    int          write_slab_size;
    int          write_head;      /* bytes confirmed sent */
    int          write_tail;      /* bytes written by handler */
    int          write_target;    /* flush target (WriteInFlight) */
    int          send_inflight;   /* 0 or 1 */
    int          closed;
} conn_t;

void conn_init(conn_t *c, int fd, reactor_t *reactor);
void conn_write(conn_t *c, const uint8_t *data, int len);
void conn_flush(conn_t *c);
void conn_reset_write(conn_t *c);
void conn_clear(conn_t *c);
void conn_destroy(conn_t *c);
