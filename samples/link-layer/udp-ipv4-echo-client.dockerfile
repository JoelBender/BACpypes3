FROM python:3.8-slim-buster

WORKDIR /app

RUN python3 -m pip install --upgrade pip
RUN python3 -m pip install pipenv
RUN pipenv --python 3.8
RUN pipenv run python3 -m pip install --upgrade --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ bacpypes3

COPY udp-ipv4-echo-client.py .

ARG LOCAL_PORT
ARG DEBUG=

CMD pipenv run python3 udp-ipv4-echo-client.py host:${LOCAL_PORT} ${DEBUG}
