#!/bin/bash

docker build \
    --tag bacpypes3-discover-ipv4-foreign:latest \
    --file discover-ipv4-foreign.dockerfile .
