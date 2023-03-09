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

# build the image passing in the file name
docker build --tag who-is:latest \
    --file who-is.dockerfile \
    --build-arg BACPYPES_WHEEL=`basename $BACPYPES_WHEEL` \
    .

popd
