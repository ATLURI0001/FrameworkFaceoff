#pragma once

#include <liburing.h>
#include "constants.h"
#include "reactor.h"

typedef struct acceptor {
    struct io_uring  ring;
    int              listen_fd;
    int              ring_entries;
    int              batch_cqes;
    volatile int    *running;
} acceptor_t;

void acceptor_init(acceptor_t *a, int listen_fd, volatile int *running);
void acceptor_loop(acceptor_t *a, reactor_t *reactors, int reactor_count);
void acceptor_destroy(acceptor_t *a);
