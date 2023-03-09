FROM python:3.10-slim

WORKDIR /app
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install -r requirements.txt

ARG BACPYPES_WHEEL
COPY ${BACPYPES_WHEEL} .
RUN pip install ${BACPYPES_WHEEL}

COPY who-is-console.py .

ARG BBMD_ADDRESS
ARG TTL
ARG DEBUG=

CMD python3 who-is-console.py \
    --address host:0 \
    --foreign ${BBMD_ADDRESS} --ttl ${TTL} \
    --route-aware ${DEBUG}
