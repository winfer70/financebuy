FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
  && rm -rf /var/lib/apt/lists/*

COPY server-b-worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server-b-worker/worker.py /app/worker.py
COPY server-b-worker/sources.py /app/sources.py
COPY server-b-worker/article_queue.py /app/article_queue.py

ENV PYTHONUNBUFFERED=1
VOLUME ["/data"]

CMD ["python", "-u", "worker.py"]
