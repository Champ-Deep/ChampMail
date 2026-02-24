#!/bin/sh
set -e

echo "Starting ChampMail frontend..."
echo "PORT=${PORT}"
echo "BACKEND_URL=${BACKEND_URL}"

# Normalize BACKEND_URL: ensure http:// protocol prefix
case "$BACKEND_URL" in
  http://*|https://*) ;;
  *) BACKEND_URL="http://${BACKEND_URL}" ;;
esac
export BACKEND_URL

echo "Normalized BACKEND_URL=${BACKEND_URL}"

# Extract DNS resolver from /etc/resolv.conf for Railway private networking
# Railway uses IPv6 for internal networking, nginx needs a resolver to handle it
DNS_RESOLVER=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf 2>/dev/null || true)
DNS_RESOLVER="${DNS_RESOLVER:-8.8.8.8}"
# Wrap IPv6 addresses in brackets for nginx resolver directive
case "$DNS_RESOLVER" in
  *:*) DNS_RESOLVER="[$DNS_RESOLVER]" ;;
esac
export DNS_RESOLVER
echo "DNS_RESOLVER=${DNS_RESOLVER}"

# Substitute environment variables into nginx config
envsubst '$PORT $BACKEND_URL $DNS_RESOLVER' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

echo "=== Generated nginx config ==="
cat /etc/nginx/conf.d/default.conf
echo "=== End nginx config ==="

# Verify config is valid
nginx -t

echo "Nginx config OK. Starting nginx..."

# Start nginx in foreground
exec nginx -g 'daemon off;'
