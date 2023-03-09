export HOST_PORT=47808
export BBMD_ADDRESS=10.0.1.90
export TTL=30
export DEBUG="--debug bacpypes3.ipv4.IPv4DatagramServer bacpypes3.ipv4.service.BIPForeign --color"

docker run \
    -it \
    --rm \
    -p $HOST_PORT:47808/udp \
    --env BBMD_ADDRESS \
    --env TTL \
    --env DEBUG \
    who-is-console:latest
