FROM python:3.10-slim

WORKDIR /app
RUN pip install --root-user-action=ignore --upgrade pip

COPY requirements.txt .
RUN pip install --root-user-action=ignore -r requirements.txt

ARG BACPYPES_WHEEL
COPY ${BACPYPES_WHEEL} .
RUN pip install --root-user-action=ignore ${BACPYPES_WHEEL}

CMD ["python3", "-m", "bacpypes3"]

