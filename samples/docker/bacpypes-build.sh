#!/bin/bash

# the script needs to be run from its directory
DIR=`dirname $0`
pushd $DIR > /dev/null

# find the latest wheel put in this directory
BACPYPES_WHEEL=`ls -1 bacpypes3-*-py3-none-any.whl 2> /dev/null | tail -n 1`

if [[ -z "${BACPYPES_WHEEL}" ]]
then
    python3 -m pip download bacpypes3
    BACPYPES_WHEEL=`ls -1 bacpypes3-*-py3-none-any.whl | tail -n 1`
fi
echo Building from $BACPYPES_WHEEL

# build the image passing in the file name
docker build --tag bacpypes:latest \
    --file bacpypes.dockerfile \
    --build-arg BACPYPES_WHEEL=`basename $BACPYPES_WHEEL` \
    .

popd
