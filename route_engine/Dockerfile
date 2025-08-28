FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc libpq-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app

EXPOSE 5000

# Use gunicorn for production
CMD ["gunicorn", "-w", "4", "-k", "gthread", "--threads", "8", "-b", "0.0.0.0:5000", "app.main:create_app()"]
