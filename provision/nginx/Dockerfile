FROM nginx:1.31.8-trixie

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
           ca-certificates \
           openssl \
           wget \
           bash \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /etc/nginx/conf.d/

# Self-signed certificate, so HTTPS works from the start. Use a certificate
# from Let's Encrypt in production (see the ssl_certificate lines in nginx-docker.conf).
RUN openssl req -x509 -nodes -newkey rsa:2048 -keyout local-key.pem -out local-cert.pem -sha256 -days 365 -subj "/C=DE/ST=City/L=City/O=Oldenburg/OU=Oldenburg/CN=localhost"

# On start, the nginx image turns templates into config files in conf.d and
# fills in the environment variables, here HTTPS_PORT (set in compose.prod.yaml).
ENV HTTPS_PORT=443
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx-docker.conf /etc/nginx/templates/nginx-docker.conf.template

# To debug the image, keep the container running without nginx:
# ENTRYPOINT ["tail", "-f", "/dev/null"]
