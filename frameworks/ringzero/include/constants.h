#pragma once

#include <stdint.h>

/* User-data packing (64-bit: upper 32 = kind, lower 32 = fd) */
typedef enum { UD_ACCEPT = 1, UD_RECV = 2, UD_SEND = 3, UD_CANCEL = 4 } ud_kind_t;

#define PACK_UD(kind, fd)   (((uint64_t)(kind) << 32) | (uint32_t)(fd))
#define UD_KIND(ud)         ((ud_kind_t)((ud) >> 32))
#define UD_FD(ud)           ((int)((ud) & 0xFFFFFFFF))

/* Config defaults (from Playground.Terraform/Program.cs) */
#define DEFAULT_REACTOR_RING_ENTRIES    8192
#define DEFAULT_ACCEPTOR_RING_ENTRIES   8192
#define DEFAULT_RECV_BUF_SIZE           4096
#define DEFAULT_BUF_RING_ENTRIES        16384
#define DEFAULT_BATCH_CQES              4096
#define DEFAULT_MAX_CONNECTIONS         65536
#define DEFAULT_WRITE_SLAB_SIZE         16384   /* 16 KB */
#define BUFFER_RING_BGID                1
