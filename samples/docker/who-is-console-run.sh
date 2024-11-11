#!/bin/bash

docker run -it --rm \
    --network host \
    who-is-console:latest
