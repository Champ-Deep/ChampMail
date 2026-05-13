FROM alpine:3.19

RUN apk --no-cache add opendkim opendkim-utils

RUN mkdir -p /etc/opendkim/keys /run/opendkim && \
    chown -R opendkim:opendkim /etc/opendkim /run/opendkim

COPY opendkim.conf /etc/opendkim/opendkim.conf
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# milter port
EXPOSE 8891

CMD ["/entrypoint.sh"]
