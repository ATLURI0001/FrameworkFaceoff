FROM denoland/deno:2.2.2
WORKDIR /app
COPY server.ts .
RUN deno cache server.ts
EXPOSE 8080
CMD ["deno", "serve", "--parallel", "--port", "8080", "--host", "0.0.0.0", "-A", "server.ts"]
