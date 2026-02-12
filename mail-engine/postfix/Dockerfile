FROM alpine:latest

RUN apk --no-cache add postfix postfix-pcre cyrus-sasl cyrus-sasl-plain

RUN postconf -e "myhostname = mail.champmail.com" && \
    postconf -e "mydomain = champmail.com" && \
    postconf -e "myorigin = \$mydomain" && \
    postconf -e "mydestination = localhost.\$mydomain, localhost, \$mydomain" && \
    postconf -e "inet_interfaces = all" && \
    postconf -e "relay_domains = *" && \
    postconf -e "smtpd_relay_restrictions = permit_mynetworks permit_sasl_authenticated defer_unauth_destination"

RUN echo "champmail.com" > /etc/mailname

EXPOSE 25 465 587

CMD ["postfix", "start-fg"]