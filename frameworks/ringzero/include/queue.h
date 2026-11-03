#pragma once

/*
 * Lock-free SPSC (Single Producer, Single Consumer) int queue.
 * One acceptor (producer) → one reactor (consumer) per queue.
 * Capacity must be a power of two.
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>

typedef struct {
    int      *buf;
    int       capacity;
    int       mask;
    _Alignas(64) _Atomic(uint64_t) head;
    _Alignas(64) _Atomic(uint64_t) tail;
} spsc_queue_t;

static inline void spsc_init(spsc_queue_t *q, int capacity)
{
    q->capacity = capacity;
    q->mask     = capacity - 1;
    q->buf      = (int *)calloc(capacity, sizeof(int));
    atomic_store_explicit(&q->head, 0, memory_order_relaxed);
    atomic_store_explicit(&q->tail, 0, memory_order_relaxed);
}

static inline void spsc_destroy(spsc_queue_t *q)
{
    free(q->buf);
    q->buf = NULL;
}

/* Returns 1 on success, 0 if full. Called only by the producer thread. */
static inline int spsc_enqueue(spsc_queue_t *q, int val)
{
    uint64_t tail = atomic_load_explicit(&q->tail, memory_order_relaxed);
    uint64_t head = atomic_load_explicit(&q->head, memory_order_acquire);
    if (tail - head >= (uint64_t)q->capacity)
        return 0;
    q->buf[tail & q->mask] = val;
    atomic_store_explicit(&q->tail, tail + 1, memory_order_release);
    return 1;
}

/* Returns 1 on success (value written to *out), 0 if empty. Consumer thread only. */
static inline int spsc_dequeue(spsc_queue_t *q, int *out)
{
    uint64_t head = atomic_load_explicit(&q->head, memory_order_relaxed);
    uint64_t tail = atomic_load_explicit(&q->tail, memory_order_acquire);
    if (head >= tail)
        return 0;
    *out = q->buf[head & q->mask];
    atomic_store_explicit(&q->head, head + 1, memory_order_release);
    return 1;
}
