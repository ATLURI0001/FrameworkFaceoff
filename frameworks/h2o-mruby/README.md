# h2o-mruby

h2o web server with mruby scripting handlers and native HTTP/3 (QUIC) support via quicly.

## Stack

- **Language:** mruby (embedded Ruby)
- **Engine:** h2o with quicly (HTTP/3)
- **Build:** `buildpack-deps:bookworm` → `debian:bookworm-slim`

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/pipeline` | GET | Returns `ok` (plain text) |
| `/baseline11` | GET | Sums query parameter values |
| `/baseline11` | POST | Sums query parameters + request body |
| `/baseline2` | GET | Sums query parameter values (HTTP/2 variant) |
| `/json` | GET | Processes 50-item dataset, serializes JSON |
| `/compression` | GET | Gzip-compressed large JSON response |
| `/static` | GET | Serves static files from `/data/static` |

## Notes

- Routes configured via mruby Proc handlers in h2o.conf
- HTTP/2 and HTTP/3 (QUIC) support
- Config generated dynamically by `entrypoint.sh`
- Large dataset pre-processed via jq at startup
- TLS cert/key detection for HTTPS listeners
