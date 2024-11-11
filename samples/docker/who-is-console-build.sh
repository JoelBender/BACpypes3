#!/bin/bash

# the script needs to be run from its directory
DIR=`dirname $0`
pushd $DIR > /dev/null

docker build \
    --tag who-is-console:latest \
    --file who-is-console.dockerfile \
    .

popd
