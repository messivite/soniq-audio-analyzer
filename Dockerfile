FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN mkdir -p /tmp/soniq-audio

EXPOSE 8090

CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:8090", "--workers", "2", "--timeout", "120"]
