FROM alpine:latest
RUN apk --no-cache add postfix postfix-pcre openssl

RUN echo "champmail.com" > /etc/mailname

RUN postconf -e "myhostname = mail.champmail.com" && \
    postconf -e "mydomain = champmail.com" && \
    postconf -e "myorigin = \$mydomain" && \
    postconf -e "mydestination = localhost.\$mydomain, localhost, \$mydomain" && \
    postconf -e "inet_interfaces = all" && \
    postconf -e "relay_domains = *" && \
    postconf -e "smtpd_relay_restrictions = permit_mynetworks permit_sasl_authenticated defer_unauth_destination" && \
    postconf -e "smtpd_tls_security_level = may" && \
    postconf -e "smtpd_tls_auth_only = no" && \
    postconf -e "smtp_tls_security_level = may"

RUN mkdir -p /etc/postfix/ssl && \
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/postfix/ssl/server.key -out /etc/postfix/ssl/server.crt \
    -subj "/C=US/ST=State/L=City/O=ChampMail/CN=mail.champmail.com" && \
    postconf -e "smtpd_tls_cert_file=/etc/postfix/ssl/server.crt" && \
    postconf -e "smtpd_tls_key_file=/etc/postfix/ssl/server.key"

RUN echo "" >> /etc/postfix/master.cf && \
    echo "submission inet n - n - - smtpd" >> /etc/postfix/master.cf && \
    echo "  -o smtpd_sasl_auth_enable=yes" >> /etc/postfix/master.cf && \
    echo "  -o smtpd_tls_security_level=may" >> /etc/postfix/master.cf

EXPOSE 25 465 587

CMD ["postfix", "start-fg"]
