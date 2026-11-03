# h2load — HTTP/2 load generator from the nghttp2 project.
#
# Uses Ubuntu + apt-installed `nghttp2-client` (glibc build) instead of
# alpine's musl build. The alpine h2load suffers ~20-40% throughput loss
# on high-QPS workloads because of musl's per-call malloc overhead and
# thread primitives — unacceptable for a benchmark load generator.
#
# Self-contained: installs nghttp2 directly from the Ubuntu archive during
# the build; no source checkout, no local file dependencies.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        nghttp2-client ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["h2load"]
