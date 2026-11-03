#include "connection.h"
#include "reactor.h"
#include "constants.h"

#include <stdlib.h>
#include <string.h>

void conn_init(conn_t *c, int fd, reactor_t *reactor)
{
    c->fd             = fd;
    c->reactor        = reactor;
    c->write_slab_size = DEFAULT_WRITE_SLAB_SIZE;
    if (!c->write_buf)
        c->write_buf = (uint8_t *)aligned_alloc(64, DEFAULT_WRITE_SLAB_SIZE);
    c->write_head     = 0;
    c->write_tail     = 0;
    c->write_target   = 0;
    c->send_inflight  = 0;
    c->closed         = 0;
}

void conn_write(conn_t *c, const uint8_t *data, int len)
{
    if (c->write_tail + len > c->write_slab_size)
        return;   /* silently drop on overflow — same as terraform throwing */
    memcpy(c->write_buf + c->write_tail, data, len);
    c->write_tail += len;
}

void conn_flush(conn_t *c)
{
    int target = c->write_tail;
    if (target == 0)
        return;
    c->write_target = target;

    if (c->send_inflight)
        return;   /* reactor will chain the remaining bytes when current send completes */
    c->send_inflight = 1;
    reactor_submit_send(c->reactor, c->fd, c->write_buf, c->write_head, target);
}

void conn_reset_write(conn_t *c)
{
    c->write_head   = 0;
    c->write_tail   = 0;
    c->write_target = 0;
}

void conn_clear(conn_t *c)
{
    c->fd            = -1;
    c->reactor       = NULL;
    c->write_head    = 0;
    c->write_tail    = 0;
    c->write_target  = 0;
    c->send_inflight = 0;
    c->closed        = 0;
}

void conn_destroy(conn_t *c)
{
    if (c->write_buf) {
        free(c->write_buf);
        c->write_buf = NULL;
    }
}
