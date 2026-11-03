FROM golang:1.24-bookworm AS build
WORKDIR /app
COPY . .
RUN CGO_ENABLED=0 go build -o server main.go

FROM debian:bookworm-slim
COPY --from=build /app/server /server
EXPOSE 8080
CMD ["/server"]
