#!/bin/sh
# Runs before nginx starts. Uses the Let's Encrypt certificate (task prod:cert)
# if it exists, else the self-signed one of the image.
set -eu
live="/etc/nginx/ssl/live/${SSL_CERT_NAME:-}"
if [ -n "${SSL_CERT_NAME:-}" ] && [ -f "$live/fullchain.pem" ] && [ -f "$live/privkey.pem" ]; then
    ln -sf "$live/fullchain.pem" /etc/nginx/conf.d/active-cert.pem
    ln -sf "$live/privkey.pem" /etc/nginx/conf.d/active-key.pem
    echo "ssl-cert: Let's Encrypt certificate $SSL_CERT_NAME"
else
    ln -sf /etc/nginx/conf.d/local-cert.pem /etc/nginx/conf.d/active-cert.pem
    ln -sf /etc/nginx/conf.d/local-key.pem /etc/nginx/conf.d/active-key.pem
    echo "ssl-cert: self-signed certificate (no certificate for '${SSL_CERT_NAME:-}')"
fi
