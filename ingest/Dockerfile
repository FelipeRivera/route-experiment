FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc libpq-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /ingest

COPY requirements.txt /ingest/requirements.txt
RUN pip install --no-cache-dir -r /ingest/requirements.txt

COPY ingest_bogota.py /ingest/ingest_bogota.py

CMD ["python", "/ingest/ingest_bogota.py"]
