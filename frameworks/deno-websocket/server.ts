export default {
  fetch(req: Request): Response {
    if (new URL(req.url).pathname === "/ws") {
      const { socket, response } = Deno.upgradeWebSocket(req);
      socket.onmessage = (e) => socket.send(e.data);
      return response;
    }
    return new Response("Not found", { status: 404 });
  },
};

console.log("Application started.");
