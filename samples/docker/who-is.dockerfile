FROM python:3.10-slim

WORKDIR /app
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install -r requirements.txt

ARG BACPYPES_WHEEL
COPY ${BACPYPES_WHEEL} .
RUN pip install ${BACPYPES_WHEEL}

COPY who-is.py .

ARG LOW_LIMIT
ARG HIGH_LIMIT
ARG BBMD_ADDRESS
ARG TTL
ARG DEBUG=

CMD python3 who-is.py $LOW_LIMIT $HIGH_LIMIT \
    --address host:0 \
    --foreign $BBMD_ADDRESS --ttl $TTL \
    --route-aware \
    $DEBUG
