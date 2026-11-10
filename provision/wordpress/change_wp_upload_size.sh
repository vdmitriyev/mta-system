#!/bin/bash

# Define the container prefix and filename
CONTAINER_PREFIX="wordpress"
FILENAME=".htaccess"
DESTINATION_PATH="/var/www/html"
SKIP_KEYWORD="-cli-"

# Get all containers with the specified prefix
CONTAINERS=$(docker ps -a --format '{{.Names}}' --filter "name=${CONTAINER_PREFIX}")

# Iterate over the containers
for CONTAINER in $CONTAINERS; do

    # Skip containers containing the skip keyword in their names
    if [[ "$CONTAINER" == *"$SKIP_KEYWORD"* ]]; then
        echo "Skipping container '${CONTAINER}' due to keyword '${SKIP_KEYWORD}'"
        continue
    fi

    echo "Copying file '${FILENAME}' to container '${CONTAINER}'..."

    # Start the container if it's not running
    if [ "$(docker inspect -f '{{.State.Running}}' ${CONTAINER})" = "false" ]; then
        docker start "${CONTAINER}"
    fi

    # Copy the file from the host to the container
    docker cp "${FILENAME}" "${CONTAINER}:${DESTINATION_PATH}"

    # Stop the container if it was not running initially
    if [ "$(docker inspect -f '{{.State.Paused}}' ${CONTAINER})" = "true" ]; then
        docker unpause "${CONTAINER}"
    else
        docker stop "${CONTAINER}"
    fi

    echo "File copied successfully."
done
