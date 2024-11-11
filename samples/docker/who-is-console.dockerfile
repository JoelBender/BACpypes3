FROM bacpypes:latest

COPY who-is-console.py .

CMD ["python3", "who-is-console.py"]

