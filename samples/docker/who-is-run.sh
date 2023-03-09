#!/bin/bash

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
if [[ -z "${LOW_LIMIT}" ]]
then
    read -p "Low limit " LOW_LIMIT || exit 1
    export LOW_LIMIT
fi
if [[ -z "${HIGH_LIMIT}" ]]
then
    read -p "High limit " HIGH_LIMIT || exit 1
    export HIGH_LIMIT
fi
if [[ -z "${DEBUG}" ]]
then
    export DEBUG=""
fi

docker run -it --rm \
    --network host \
    --env BBMD_ADDRESS \
    --env TTL \
    --env LOW_LIMIT \
    --env HIGH_LIMIT \
    --env DEBUG \
    who-is:latest
