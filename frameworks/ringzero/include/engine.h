#pragma once

#include <pthread.h>
#include "reactor.h"
#include "acceptor.h"
#include "connection.h"

typedef struct engine {
    int              reactor_count;
    reactor_t       *reactors;
    acceptor_t       acceptor;
    int              listen_fd;
    volatile int     running;
    pthread_t       *reactor_threads;
    pthread_t        acceptor_thread;
    handler_fn       handler;
    pthread_barrier_t ready_barrier;
} engine_t;

void engine_listen(engine_t *eng, const char *ip, int port, int backlog,
                   int reactor_count, handler_fn handler);
void engine_stop(engine_t *eng);
