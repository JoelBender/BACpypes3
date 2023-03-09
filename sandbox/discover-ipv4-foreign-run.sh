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
if [[ -z "${BBMD_ADDRESS}" ]]
then
    echo "The address of the BBMD for foreign device registration"
    echo ""
    read -p "BBMD Address " BBMD_ADDRESS || exit 1
    export BBMD_ADDRESS
fi
if [[ -z "${TTL}" ]]
then
    read -p "Time-to-live " TTL || exit 1
    export TTL
fi
if [[ -z "${DEBUG}" ]]
then
    export DEBUG=""
fi

docker run \
    -it \
    --rm \
    -p ${HOST_ADDRESS}:47808/udp \
    --env BBMD_ADDRESS \
    --env TTL \
    --env DEBUG \
    bacpypes3-discover-ipv4-foreign:latest
