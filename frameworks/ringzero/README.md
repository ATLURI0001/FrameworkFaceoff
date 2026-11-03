# ringzero

Custom C HTTP server built on Linux's `io_uring` interface. Uses a multi-reactor architecture with `liburing` for asynchronous I/O — no `epoll`, no thread-per-connection.

## Stack

- **Language:** C (GCC, `-O2 -march=native`)
- **Engine:** io_uring via liburing 2.9
- **Architecture:** Multi-reactor threads, shared accept
- **Build:** Ubuntu 24.04, builds liburing from source

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/pipeline` | GET | Returns `ok`, batches pipelined requests by scanning for multiple `\r\n\r\n` boundaries |
| `/baseline11` | GET | Sums query parameter values |
| `/baseline11` | POST | Sums query parameters + request body (Content-Length and chunked) |

## Notes

- Pipeline handler batches multiple responses per `read()` for maximum throughput
- Manual HTTP parsing with `memmem`/`memchr` — no framework overhead
- Chunked Transfer-Encoding decoded inline
- Worker count configurable via CLI argument (default 64)
