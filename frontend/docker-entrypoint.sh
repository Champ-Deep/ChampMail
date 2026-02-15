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

# Ensure port is present (default to 8000 if missing)
HOST_PART="${BACKEND_URL#http://}"
HOST_PART="${HOST_PART#https://}"
case "$HOST_PART" in
  *:*) ;;
  *) BACKEND_URL="${BACKEND_URL}:8000" ;;
esac
export BACKEND_URL

echo "Normalized BACKEND_URL=${BACKEND_URL}"

# Substitute environment variables into nginx config
envsubst '$PORT $BACKEND_URL' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

# Verify config is valid
nginx -t

echo "Nginx config OK. Starting nginx..."

# Start nginx in foreground
exec nginx -g 'daemon off;'
