#!/bin/bash

docker build \
    --tag bacpypes3-udp-ipv4-echo-client:latest \
    --file udp-ipv4-echo-client.dockerfile .
