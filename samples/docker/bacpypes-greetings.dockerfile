FROM bacpypes:latest

WORKDIR /app

COPY bacpypes-greetings.py .

CMD ["python3", "bacpypes-greetings.py"]
