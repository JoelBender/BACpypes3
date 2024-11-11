#!/bin/bash

if [[ -z "x" ]]
then
    if [[ -z "${BACPYPES_FOREIGN_BBMD}" ]]
    then
        echo "The address of the BBMD for foreign device registration"
        echo ""
        read -p "BBMD Address " BACPYPES_FOREIGN_BBMD || exit 1
        export BACPYPES_FOREIGN_BBMD
    fi
    if [[ -z "${BACPYPES_FOREIGN_TTL}" ]]
    then
        read -p "Time-to-live " BACPYPES_FOREIGN_TTL || exit 1
        export BACPYPES_FOREIGN_TTL
    fi
fi

docker run -it --rm \
    --network host \
    --env BACPYPES_DEVICE_ADDRESS \
    --env BACPYPES_DEVICE_NAME \
    --env BACPYPES_DEVICE_INSTANCE \
    --env BACPYPES_NETWORK \
    --env BACPYPES_VENDOR_IDENTIFIER \
    --env BACPYPES_FOREIGN_BBMD \
    --env BACPYPES_FOREIGN_TTL \
    --env BACPYPES_BBMD_BDT \
    --env BACPYPES_DEBUG \
    bacpypes:latest
