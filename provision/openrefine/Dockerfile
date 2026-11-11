###################
# Based on:
#		https://github.com/opencultureconsulting/openrefine-docker/blob/master/3.4/Dockerfile
###################

FROM openjdk:22-ea-22-jdk-slim
#ENV OR_URL https://github.com/OpenRefine/OpenRefine/releases/download/3.7.6/openrefine-linux-3.7.6.tar.gz
# ENV OR_URL https://github.com/OpenRefine/OpenRefine/releases/download/3.8.7/openrefine-linux-3.8.7.tar.gz
# ENV OR_URL https://github.com/OpenRefine/OpenRefine/releases/download/3.9.5/openrefine-linux-3.9.5.tar.gz
ENV OR_URL https://github.com/OpenRefine/OpenRefine/releases/download/3.9.5/openrefine-linux-3.10.1.tar.gz

WORKDIR /app

#RUN set -xe \
#    && apk add --no-cache bash curl grep tar \
#    && curl -sSL ${OR_URL} | tar xz --strip 1
RUN apt-get update && apt-get install -y curl
RUN curl -sSL ${OR_URL} | tar xz --strip 1

VOLUME /data
WORKDIR /data

EXPOSE 3333

ENTRYPOINT ["/app/refine"]
CMD ["-i", "0.0.0.0", "-d", "/data", "-p", "80"]

# does not work properly
#CMD ["-i", "0.0.0.0", "-d", "/data", "-m", "768m"]
