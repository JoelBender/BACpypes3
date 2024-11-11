#!/bin/bash

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

docker run -it --rm \
    --network host \
    --env LOW_LIMIT \
    --env HIGH_LIMIT \
    who-is:latest
