#!/bin/bash

# the script needs to be run from its directory
DIR=`dirname $0`
pushd $DIR > /dev/null

# find the latest wheel put in this directory
BACPYPES_WHEEL=`ls -1 bacpypes3-*-py3-none-any.whl | tail -n 1`

if [[ -z "${BACPYPES_WHEEL}" ]]
then
    echo "missing wheel"
    exit 1
fi

docker build \
    --tag who-is-console:latest \
    --file who-is-console.dockerfile \
    --build-arg BACPYPES_WHEEL=`basename $BACPYPES_WHEEL` \
    .

popd
