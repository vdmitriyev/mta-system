###################
# Based on:
#		https://github.com/opencultureconsulting/openrefine-docker/blob/master/3.4/Dockerfile
###################

FROM openjdk:22-ea-22-jdk-slim

# Version of OpenRefine: OPENREFINE_VERSION in versions.env (project folder).
#   task services:build-openrefine
ARG OPENREFINE_VERSION
RUN test -n "$OPENREFINE_VERSION" || (echo "Build argument OPENREFINE_VERSION is missing: see versions.env" && false)
ENV OR_URL=https://github.com/OpenRefine/OpenRefine/releases/download/${OPENREFINE_VERSION}/openrefine-linux-${OPENREFINE_VERSION}.tar.gz

WORKDIR /app

#RUN set -xe \
#    && apk add --no-cache bash curl grep tar \
#    && curl -sSL ${OR_URL} | tar xz --strip 1
RUN apt-get update && apt-get install -y curl
RUN curl -fsSL ${OR_URL} | tar xz --strip 1

VOLUME /data
WORKDIR /data

EXPOSE 3333

ENTRYPOINT ["/app/refine"]
CMD ["-i", "0.0.0.0", "-d", "/data", "-p", "80"]

# does not work properly
#CMD ["-i", "0.0.0.0", "-d", "/data", "-m", "768m"]
