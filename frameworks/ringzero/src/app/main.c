#include "engine.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>

static engine_t g_eng;

static void on_signal(int sig)
{
    (void)sig;
    g_eng.running = 0;
}

static const char RESPONSE[] =
    "HTTP/1.1 200 OK\r\n"
    "Content-Length: 13\r\n"
    "Content-Type: text/plain\r\n"
    "\r\n"
    "Hello, World!";

static void echo_handler(conn_t *conn, uint8_t *buf, int len)
{
    (void)buf;
    (void)len;
    conn_write(conn, (const uint8_t *)RESPONSE, sizeof(RESPONSE) - 1);
    conn_flush(conn);
}

int main(int argc, char **argv)
{
    int reactor_count = argc > 1 ? atoi(argv[1]) : 12;

    signal(SIGINT,  on_signal);
    signal(SIGTERM, on_signal);

    memset(&g_eng, 0, sizeof(g_eng));
    engine_listen(&g_eng, "0.0.0.0", 8080, 65535, reactor_count, echo_handler);

    printf("Press Ctrl+C to stop...\n");

    /* Block until signal sets running=0 */
    while (g_eng.running)
        pause();

    engine_stop(&g_eng);
    return 0;
}
