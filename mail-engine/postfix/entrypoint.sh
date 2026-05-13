#!/bin/sh
set -e

MAIL_HOSTNAME="${MAIL_HOSTNAME:-mail.championsmail.com}"
MAIL_DOMAIN="${MAIL_DOMAIN:-$(echo "$MAIL_HOSTNAME" | cut -d. -f2-)}"
RELAY_HOST="${RELAY_HOST:-}"
RELAY_USER="${RELAY_USER:-}"
RELAY_PASS="${RELAY_PASS:-}"
RELAY_PORT="${RELAY_PORT:-587}"
TLS_CERT="${TLS_CERT:-/etc/letsencrypt/live/${MAIL_HOSTNAME}/fullchain.pem}"
TLS_KEY="${TLS_KEY:-/etc/letsencrypt/live/${MAIL_HOSTNAME}/privkey.pem}"
OPENDKIM_HOST="${OPENDKIM_HOST:-opendkim}"
OPENDKIM_PORT="${OPENDKIM_PORT:-8891}"

echo "$MAIL_DOMAIN" > /etc/mailname

# ── Identity ─────────────────────────────────────────────────────────────────
postconf -e "myhostname = ${MAIL_HOSTNAME}"
postconf -e "mydomain = ${MAIL_DOMAIN}"
postconf -e "myorigin = \$mydomain"
postconf -e "mydestination = localhost.\$mydomain, localhost"

# ── Relay / direct delivery ───────────────────────────────────────────────────
if [ -n "$RELAY_HOST" ] && [ -n "$RELAY_USER" ]; then
    echo "Mode: smarthost relay via ${RELAY_HOST}:${RELAY_PORT}"
    postconf -e "relayhost = [${RELAY_HOST}]:${RELAY_PORT}"
    echo "[${RELAY_HOST}]:${RELAY_PORT} ${RELAY_USER}:${RELAY_PASS}" > /etc/postfix/sasl_passwd
    postmap /etc/postfix/sasl_passwd
    chmod 600 /etc/postfix/sasl_passwd /etc/postfix/sasl_passwd.db
    postconf -e "smtp_sasl_auth_enable = yes"
    postconf -e "smtp_sasl_password_maps = hash:/etc/postfix/sasl_passwd"
    postconf -e "smtp_sasl_security_options = noanonymous"
    postconf -e "smtp_sasl_tls_security_options = noanonymous"
else
    echo "Mode: direct delivery (no relay)"
    postconf -e "relayhost ="
fi

# ── Close the open relay ──────────────────────────────────────────────────────
postconf -e "relay_domains ="
postconf -e "mynetworks = 127.0.0.0/8 [::ffff:127.0.0.0]/104 [::1]/128 172.16.0.0/12 10.0.0.0/8"
postconf -e "smtpd_relay_restrictions = permit_mynetworks permit_sasl_authenticated reject_unauth_destination"

# ── TLS outbound ──────────────────────────────────────────────────────────────
postconf -e "smtp_tls_security_level = may"
postconf -e "smtp_tls_loglevel = 1"
postconf -e "smtp_tls_CAfile = /etc/ssl/certs/ca-certificates.crt"
postconf -e "smtp_tls_protocols = !SSLv2, !SSLv3, !TLSv1, !TLSv1.1"

# ── TLS inbound ───────────────────────────────────────────────────────────────
if [ -f "$TLS_CERT" ] && [ -f "$TLS_KEY" ]; then
    echo "TLS: using Let's Encrypt cert at ${TLS_CERT}"
    postconf -e "smtpd_tls_cert_file = ${TLS_CERT}"
    postconf -e "smtpd_tls_key_file = ${TLS_KEY}"
else
    echo "TLS: Let's Encrypt cert not found, generating self-signed for dev"
    mkdir -p /etc/postfix/ssl
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout /etc/postfix/ssl/server.key \
        -out /etc/postfix/ssl/server.crt \
        -subj "/CN=${MAIL_HOSTNAME}" 2>/dev/null
    postconf -e "smtpd_tls_cert_file = /etc/postfix/ssl/server.crt"
    postconf -e "smtpd_tls_key_file = /etc/postfix/ssl/server.key"
fi

postconf -e "smtpd_tls_security_level = may"
postconf -e "smtpd_tls_auth_only = yes"
postconf -e "smtpd_tls_protocols = !SSLv2, !SSLv3, !TLSv1, !TLSv1.1"
postconf -e "smtpd_banner = \$myhostname ESMTP"

# ── OpenDKIM milter ───────────────────────────────────────────────────────────
postconf -e "milter_default_action = accept"
postconf -e "milter_protocol = 6"
postconf -e "smtpd_milters = inet:${OPENDKIM_HOST}:${OPENDKIM_PORT}"
postconf -e "non_smtpd_milters = inet:${OPENDKIM_HOST}:${OPENDKIM_PORT}"

# ── Queue tuning ──────────────────────────────────────────────────────────────
postconf -e "maximal_queue_lifetime = 5d"
postconf -e "bounce_queue_lifetime = 2d"
postconf -e "default_destination_concurrency_limit = 5"
postconf -e "smtp_destination_rate_delay = 1s"

# ── Header checks — strip internal IPs ───────────────────────────────────────
postconf -e "header_checks = regexp:/etc/postfix/header_checks"

# ── Submission port (587) ─────────────────────────────────────────────────────
# Ensure submission is in master.cf only once
if ! grep -q "^submission" /etc/postfix/master.cf; then
    cat >> /etc/postfix/master.cf <<'EOF'
submission inet n - n - - smtpd
  -o smtpd_sasl_auth_enable=no
  -o smtpd_tls_security_level=may
  -o smtpd_relay_restrictions=permit_mynetworks,reject
EOF
fi

# ── VERP bounce pipe ──────────────────────────────────────────────────────────
# Emails to bounce+*@domain get piped to bounce_handler.py
BOUNCE_DOMAIN="${BOUNCE_DOMAIN:-${MAIL_DOMAIN}}"
cat > /etc/postfix/virtual_regexp <<EOF
/^bounce\+.+@${BOUNCE_DOMAIN}$/ bounce_handler@localhost
EOF
echo "bounce_handler@localhost  |/usr/local/bin/python3 /app/bounce_handler.py" >> /etc/aliases
newaliases 2>/dev/null || true
postconf -e "virtual_alias_maps = regexp:/etc/postfix/virtual_regexp"
postconf -e "local_recipient_maps ="

exec postfix start-fg
