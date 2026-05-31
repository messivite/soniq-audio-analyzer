FROM python:3.11-bullseye

RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    libeigen3-dev \
    libfftw3-dev \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    libswresample-dev \
    libsamplerate0-dev \
    libtag1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

RUN mkdir -p /tmp/soniq-audio

CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:${PORT:-8090}", "--workers", "2", "--timeout", "120"]
