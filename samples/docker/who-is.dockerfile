FROM bacpypes:latest

WORKDIR /app

COPY who-is.py .

ARG LOW_LIMIT
ARG HIGH_LIMIT

CMD python3 who-is.py $LOW_LIMIT $HIGH_LIMIT

