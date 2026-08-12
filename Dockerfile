FROM python:3.11-slim

WORKDIR /app

COPY main.py /app/
COPY config.json /app/

CMD ["python", "-u", "main.py"]