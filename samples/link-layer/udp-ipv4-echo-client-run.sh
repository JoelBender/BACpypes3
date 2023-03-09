#!/bin/bash

if [[ -z "${HOST_ADDRESS}" ]]
then
    echo "The HOST_ADDRESS is the UDP port number of the docker host"
    echo "like '47808' or an IPv4 address and port number if the host"
    echo "has more than one home, like '10.0.1.70:47808' and may also"
    echo "have an alternative port number like '10.0.1.99:47809'"
    echo ""
    read -p "Host Address " HOST_ADDRESS || exit 1
    export HOST_ADDRESS
    echo ""
fi
if [[ -z "${LOCAL_PORT}" ]]
then
    echo "The LOCAL_PORT is the UDP port number the application"
    echo "uses on the docker network, normally '47808'.  The"
    echo "IPv4 address is assigned by docker"
    echo ""
    read -p "Local Port " LOCAL_PORT || exit 1
    export LOCAL_PORT
    echo ""
fi
if [[ -z "${DEBUG}" ]]
then
    export DEBUG=""
fi

docker run \
    -it \
    --rm \
    -p $HOST_ADDRESS:${LOCAL_PORT} \
    --env LOCAL_PORT \
    --env DEBUG \
    bacpypes3-udp-ipv4-echo-client:latest
