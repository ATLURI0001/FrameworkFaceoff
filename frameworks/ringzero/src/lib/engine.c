#include "engine.h"
#include "listener.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Thread args carry everything needed for init + loop */

typedef struct {
    reactor_t          *reactor;
    int                 id;
    volatile int       *running;
    handler_fn          handler;
    pthread_barrier_t  *barrier;
} reactor_thread_arg_t;

typedef struct {
    engine_t *eng;
    int       listen_fd;
} acceptor_thread_arg_t;

static void *reactor_thread_fn(void *arg)
{
    reactor_thread_arg_t *a = (reactor_thread_arg_t *)arg;
    /* Init ring ON this thread (required for SINGLE_ISSUER) */
    reactor_init(a->reactor, a->id, a->running, a->handler);
    pthread_barrier_wait(a->barrier);
    reactor_loop(a->reactor);
    free(a);
    return NULL;
}

static void *acceptor_thread_fn(void *arg)
{
    acceptor_thread_arg_t *a = (acceptor_thread_arg_t *)arg;
    /* Wait for all reactors to be ready */
    pthread_barrier_wait(&a->eng->ready_barrier);
    /* Init ring ON this thread */
    acceptor_init(&a->eng->acceptor, a->listen_fd, &a->eng->running);
    acceptor_loop(&a->eng->acceptor, a->eng->reactors, a->eng->reactor_count);
    free(a);
    return NULL;
}

void engine_listen(engine_t *eng, const char *ip, int port, int backlog,
                   int reactor_count, handler_fn handler)
{
    eng->running       = 1;
    eng->reactor_count = reactor_count;
    eng->handler       = handler;

    /* Create listen socket */
    eng->listen_fd = create_listener_socket(ip, port, backlog);
    fprintf(stderr, "Listening on %s:%d (fd=%d)\n", ip, port, eng->listen_fd);

    /* Allocate reactors + threads */
    eng->reactors       = (reactor_t *)calloc(reactor_count, sizeof(reactor_t));
    eng->reactor_threads = (pthread_t *)calloc(reactor_count, sizeof(pthread_t));

    /* Barrier: all reactors + acceptor must reach it before acceptor starts */
    pthread_barrier_init(&eng->ready_barrier, NULL, reactor_count + 1);

    /* Spawn reactor threads — each inits its own ring */
    for (int i = 0; i < reactor_count; i++) {
        reactor_thread_arg_t *ra = (reactor_thread_arg_t *)malloc(sizeof(*ra));
        ra->reactor = &eng->reactors[i];
        ra->id      = i;
        ra->running = &eng->running;
        ra->handler = handler;
        ra->barrier = &eng->ready_barrier;
        pthread_create(&eng->reactor_threads[i], NULL, reactor_thread_fn, ra);
    }

    /* Spawn acceptor thread — inits its own ring */
    acceptor_thread_arg_t *aa = (acceptor_thread_arg_t *)malloc(sizeof(*aa));
    aa->eng       = eng;
    aa->listen_fd = eng->listen_fd;
    pthread_create(&eng->acceptor_thread, NULL, acceptor_thread_fn, aa);

    fprintf(stderr, "Server started with %d reactors + 1 acceptor\n", reactor_count);
}

void engine_stop(engine_t *eng)
{
    eng->running = 0;

    pthread_join(eng->acceptor_thread, NULL);
    for (int i = 0; i < eng->reactor_count; i++)
        pthread_join(eng->reactor_threads[i], NULL);

    acceptor_destroy(&eng->acceptor);
    for (int i = 0; i < eng->reactor_count; i++)
        reactor_destroy(&eng->reactors[i]);

    free(eng->reactors);
    free(eng->reactor_threads);
    pthread_barrier_destroy(&eng->ready_barrier);

    fprintf(stderr, "Server stopped.\n");
}
