# FrameworkFaceoff

Different frameworks. Comparable workloads. Measurable trade-offs.

FrameworkFaceoff is a benchmarking platform for comparing how web frameworks handle HTTP requests, JSON processing, database queries, gRPC calls, and WebSocket traffic.

It measures throughput, response latency, CPU usage, and memory consumption to help explain how each implementation behaves under load.

## What Gets Measured

| Metric | What it tells you |
| --- | --- |
| Requests per second | How much traffic an implementation handles |
| p99 latency | Response time at the 99th percentile |
| Mean latency | Average response time, including the effects of queueing |
| CPU usage | Processing resources consumed by the workload |
| Memory usage | Memory consumed during execution |
| CPU cost per request | Processing efficiency at a fixed offered request rate |

A high request rate is only one part of the result. Latency and resource consumption matter when comparing implementations.

## Test Coverage

Frameworks run the profiles they support and subscribe to. Not every framework participates in every test.

| Category | Profiles | Focus |
| --- | --- | --- |
| Connections | `baseline`, `pipelined`, `limited-conn` | Request handling, pipelining, and connection turnover |
| Concurrency | `async` | Many pending requests with a controlled asynchronous delay |
| Efficiency | `latency-1m`, `latency-10k`, `latency-500k-8cpu` | CPU cost and latency under fixed offered request rates |
| Response workloads | `json-comp`, `json-tls`, `8gbit`, `static-tls` | JSON, compression, TLS, body transfer, and static files |
| Database | `async-db` | Asynchronous PostgreSQL queries |
| Templates | `fortunes` | Database retrieval and HTML template rendering |
| HTTP/2 | `baseline-h2`, `static-h2`, `baseline-h2c`, `json-h2c` | TLS and cleartext HTTP/2 workloads |
| HTTP/3 | `baseline-h3`, `static-h3` | HTTP over QUIC |
| gRPC | `unary-grpc`, `unary-grpc-tls` | Unary calls with and without TLS |
| Gateways | `gateway-64`, `gateway-h3` | Reverse proxies combined with application servers |
| Production stack | `production-stack` | Edge service, Redis, JWT authentication sidecar, and application server |
| WebSockets | `echo-ws`, `echo-ws-pipeline`, `echo-ws-limited` | Echo throughput, pipelining, and connection turnover |

Some profiles are reference-only and excluded from composite rankings. Consult the scoring implementation and documentation when interpreting results.

## Repository Layout

| Directory | Contents |
| --- | --- |
| `frameworks/` | Framework implementations and metadata |
| `scripts/` | Validation and benchmark tooling |
| `requests/` | Request definitions and workload assets |
| `docker/` | Container-related configuration |
| `data/` | Supporting benchmark data |
| `site/` | Leaderboard website and published result assets |
| `.github/` | GitHub workflow configuration |

## Run Locally

The benchmark scripts use Bash. On Windows, use a suitably configured Linux environment such as WSL.

Clone the repository:

```bash
git clone https://github.com/ATLURI0001/FrameworkFaceoff.git
cd FrameworkFaceoff
```

Before running benchmarks, review the scripts and install the container, load-generator, and system dependencies required by your selected profiles. Cloning the repository does not install those dependencies.

Choose a framework directory under `frameworks/`:

```bash
FRAMEWORK="your-framework-directory"
```

Validate its implementation:

```bash
./scripts/validate.sh "$FRAMEWORK"
```

Run its benchmark profiles:

```bash
./scripts/benchmark.sh "$FRAMEWORK"
```

Run a specific profile:

```bash
./scripts/benchmark.sh "$FRAMEWORK" baseline
```

Run and save results:

```bash
./scripts/benchmark.sh "$FRAMEWORK" --save
```

Validate correctness before comparing performance.

## Reading Results

Compare runs with equivalent conditions:

- Hardware and CPU allocation
- Operating system and runtime versions
- Framework versions and configuration
- Request bodies and response sizes
- Connections, concurrency, and pipelining
- TLS and compression settings
- Warm-up and measurement duration
- Load-generator capacity

Fixed-rate profiles measure behavior at a specified offered load. A profile named `latency-1m` is not proof that every participating framework successfully sustains one million requests per second.

Database, template, and gateway results also reflect the dependencies surrounding the framework.

## Pull Request Benchmark Commands

The inherited automation supports the following commands when its workflows, runner infrastructure, permissions, and dependencies are configured for this repository.

| Command | Purpose |
| --- | --- |
| `/benchmark -f <framework>` | Run the framework's subscribed tests |
| `/benchmark -f <framework> -t <test>` | Run one test |
| `/benchmark -f <framework> --save` | Run and save results |
| `/benchmark -f <framework> -t <test> --save` | Run one test and save results |
| `/benchmark -f <framework> --compare <other>` | Compare against another framework entry |
| `/benchmark-multiple -f <fw1>,<fw2>` | Run several frameworks together |
| `/benchmark-multiple --save` | Benchmark and save results for frameworks touched by the PR |
| `/benchmark-test -t <test>` | Run and save a test across its enabled subscribers |

Single-framework runs require `-f <framework>`. The `--compare` option applies to single-framework runs.

By default, comparisons use the framework's published results on `main`. A comparison against another entry uses that entry as the baseline.

These commands require repository-specific setup; they are not activated merely by copying the source.

## Leaderboard and Result Provenance

The repository includes leaderboard code and inherited result assets.

Existing upstream measurements describe the upstream testing environment. They should not be presented as new FrameworkFaceoff measurements.

For new published runs, record the hardware, software versions, test configuration, and measurement date. Keep independently collected results distinguishable from inherited data.

Upstream leaderboard and badge URLs continue to represent upstream rankings. A separately hosted leaderboard requires its own deployment and URL configuration.

## Contributing

- Add or improve implementations under `frameworks/`.
- Run the relevant correctness checks.
- Include reproducible configuration details with performance changes.
- Explain changes in throughput, latency, CPU, and memory.
- Open issues and pull requests in this repository.

Framework metadata can include a `maintainers` array:

```json
{
  "maintainers": ["your-github-username"]
}
```

Maintainer notifications depend on the corresponding automation being configured.
