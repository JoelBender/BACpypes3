FROM python:3.8-slim

WORKDIR /app

RUN pip install --upgrade pip
RUN pip install --upgrade --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ bacpypes3

COPY discover-ipv4-foreign.py .

ARG BBMD_ADDRESS
ARG TTL
ARG DEBUG=

CMD python3 discover-ipv4-foreign.py host:47808 ${BBMD_ADDRESS} ${TTL} --route-aware ${DEBUG}
