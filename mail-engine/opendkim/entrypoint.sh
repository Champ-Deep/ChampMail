#!/bin/sh
set -e

TRUSTED_HOSTS="/etc/opendkim/TrustedHosts"
KEY_TABLE="/etc/opendkim/KeyTable"
SIGNING_TABLE="/etc/opendkim/SigningTable"

# Seed TrustedHosts if missing
if [ ! -f "$TRUSTED_HOSTS" ]; then
    cat > "$TRUSTED_HOSTS" <<EOF
127.0.0.1
::1
localhost
smtp
postfix
172.16.0.0/12
10.0.0.0/8
EOF
fi

# Create empty tables if missing
[ -f "$KEY_TABLE" ]     || touch "$KEY_TABLE"
[ -f "$SIGNING_TABLE" ] || touch "$SIGNING_TABLE"

chown -R opendkim:opendkim /etc/opendkim /run/opendkim

echo "OpenDKIM starting on port 8891..."
exec opendkim -f -x /etc/opendkim/opendkim.conf
