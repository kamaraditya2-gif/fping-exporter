FROM python:3.11-slim

RUN apt-get update && apt-get install -y fping && rm -rf /var/lib/apt/lists/*
RUN pip install psycopg2-binary

WORKDIR /app

RUN setcap cap_net_raw+ep $(which fping)

CMD ["python", "-u", "/app/worker.py"]
