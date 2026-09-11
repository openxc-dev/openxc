# Multistage: build a static Go binary, then ship just that binary in a
# minimal image — no Go toolchain, no shell dependencies at runtime.
FROM golang:1.24-alpine AS build

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY server.go .
RUN CGO_ENABLED=0 go build -o /out/events-server server.go

FROM scratch

COPY --from=build /out/events-server /events-server

EXPOSE 8001

ENTRYPOINT ["/events-server"]
