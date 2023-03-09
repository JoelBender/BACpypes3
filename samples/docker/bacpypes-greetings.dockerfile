FROM python:3.10-slim

WORKDIR /app
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install -r requirements.txt

ARG BACPYPES_WHEEL
COPY ${BACPYPES_WHEEL} .
RUN pip install ${BACPYPES_WHEEL}

COPY bacpypes-greetings.py .

CMD python3 bacpypes-greetings.py
