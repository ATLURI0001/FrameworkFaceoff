#include "listener.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <arpa/inet.h>

int create_listener_socket(const char *ip, int port, int backlog)
{
    int lfd = socket(AF_INET, SOCK_STREAM, 0);
    if (lfd < 0) { perror("socket"); exit(1); }

    int one = 1;
    if (setsockopt(lfd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one)) < 0)
    { perror("setsockopt(SO_REUSEADDR)"); close(lfd); exit(1); }

    if (setsockopt(lfd, SOL_SOCKET, SO_REUSEPORT, &one, sizeof(one)) < 0)
    { perror("setsockopt(SO_REUSEPORT)"); close(lfd); exit(1); }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port   = htons((uint16_t)port);

    if (inet_pton(AF_INET, ip, &addr.sin_addr) != 1)
    { fprintf(stderr, "Invalid IPv4 address: %s\n", ip); close(lfd); exit(1); }

    if (bind(lfd, (struct sockaddr *)&addr, sizeof(addr)) < 0)
    { perror("bind"); close(lfd); exit(1); }

    if (listen(lfd, backlog) < 0)
    { perror("listen"); close(lfd); exit(1); }

    int fl = fcntl(lfd, F_GETFL, 0);
    if (fl < 0) { perror("fcntl(F_GETFL)"); close(lfd); exit(1); }
    if (fcntl(lfd, F_SETFL, fl | O_NONBLOCK) < 0)
    { perror("fcntl(F_SETFL)"); close(lfd); exit(1); }

    return lfd;
}
