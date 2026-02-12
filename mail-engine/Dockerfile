FROM golang:1.21-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o mail-engine ./cmd/main.go

FROM alpine:latest

RUN apk --no-cache add ca-certificates git

WORKDIR /app

COPY --from=builder /app/mail-engine .

RUN mkdir -p /etc/champmail

EXPOSE 8025

CMD ["./mail-engine"]