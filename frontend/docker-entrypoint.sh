#!/bin/sh
set -e

echo "Starting ChampMail frontend..."
echo "PORT=${PORT}"
echo "BACKEND_URL=${BACKEND_URL}"

# Substitute environment variables into nginx config
envsubst '$PORT $BACKEND_URL' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

# Verify config is valid
nginx -t

echo "Nginx config OK. Starting nginx..."

# Start nginx in foreground
exec nginx -g 'daemon off;'
