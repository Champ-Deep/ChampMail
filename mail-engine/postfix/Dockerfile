FROM alpine:3.19

RUN apk --no-cache add postfix postfix-pcre openssl ca-certificates

# entrypoint configures hostname and TLS at runtime from env vars
COPY entrypoint.sh /entrypoint.sh
COPY header_checks /etc/postfix/header_checks
RUN chmod +x /entrypoint.sh

# Submission (587) for app → Postfix, port 25 for inbound bounces/DSNs
EXPOSE 25 587

CMD ["/entrypoint.sh"]
