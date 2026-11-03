const cluster = require('cluster');
const os = require('os');

if (cluster.isPrimary) {
  const numCPUs = os.availableParallelism ? os.availableParallelism() : os.cpus().length;
  for (let i = 0; i < numCPUs; i++) cluster.fork();
  console.log('Application started.');
} else {
  const http = require('http');
  const { WebSocketServer } = require('ws');

  const server = http.createServer((req, res) => {
    res.writeHead(404);
    res.end();
  });

  const wss = new WebSocketServer({ noServer: true });

  server.on('upgrade', (req, socket, head) => {
    if (req.url === '/ws') {
      wss.handleUpgrade(req, socket, head, ws => {
        ws.on('message', msg => ws.send(msg));
      });
    } else {
      socket.destroy();
    }
  });

  server.listen(8080);
}
