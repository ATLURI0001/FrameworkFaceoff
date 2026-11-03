Bun.serve({
  port: 8080,
  reusePort: true,
  fetch(req, server) {
    if (new URL(req.url).pathname === "/ws") {
      if (server.upgrade(req)) return;
      return new Response("Upgrade failed", { status: 400 });
    }
    return new Response("Not found", { status: 404 });
  },
  websocket: {
    message(ws, message) {
      ws.send(message);
    },
  },
});

console.log("Application started.");
