FROM ubuntu:24.04 AS build
RUN apt-get update && apt-get install -y gcc make git
RUN git clone --depth 1 --branch liburing-2.9 https://github.com/axboe/liburing.git /tmp/liburing \
    && cd /tmp/liburing && ./configure && make -C src -j$(nproc) && make -C src install && ldconfig \
    && rm -rf /tmp/liburing
WORKDIR /app

# Copy ringzero library source (provided via build context)
COPY include/ include/
COPY src/ src/

# Copy bench handler
COPY main.c .

# Build ringzero library objects
RUN for f in src/lib/*.c; do \
      gcc -O2 -Wall -march=native -pthread -Iinclude -c "$f" -o "$(basename "$f" .c).o"; \
    done

# Build bench server
RUN gcc -O2 -Wall -march=native -pthread -Iinclude -c main.c -o main.o
RUN gcc -o server main.o acceptor.o connection.o engine.o listener.o reactor.o -luring -lpthread

FROM ubuntu:24.04
COPY --from=build /usr/lib/liburing.so.2.9 /usr/lib/
RUN ln -s /usr/lib/liburing.so.2.9 /usr/lib/liburing.so.2 && ldconfig
COPY --from=build /app/server /server
EXPOSE 8080
CMD ["/server", "64"]
