#pragma once

/* Create a listening TCP socket: SO_REUSEADDR, SO_REUSEPORT, O_NONBLOCK. */
int create_listener_socket(const char *ip, int port, int backlog);
