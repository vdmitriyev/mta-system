#!/bin/bash

#
# openrefine
#
function redeploy_openrefine(){

	container_name=openrefine
	container_name_port=3333
	docker_image_version=3.10.1

	echo -e "\nRedeploy docker container: $container_name"
	sleep 2s

	#cd /opt//docker

	docker stop $(docker ps -a | grep $container_name | awk '{print $1}')
	docker rm $(docker ps -a | grep $container_name | awk '{print $1}')
	docker build -t $container_name:$docker_image_version .
	#docker run -d -p $container_name_port:$container_name_port --name $container_name --restart unless-stopped  $container_name
}

redeploy_openrefine
