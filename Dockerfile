# Use a specific slim-bullseye tag (more reliable resolver)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    HF_HOME=/root/.cache/huggingface \
    PATH=/root/.cargo/bin:$PATH

WORKDIR /app

# System build deps (do NOT install rustc/cargo via apt; use rustup below)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    make \
    python3-dev \
    pkg-config \
    curl \
    ca-certificates \
    ffmpeg \
    libsndfile1 \
    libicu-dev \
    libxml2-dev \
  && rm -rf /var/lib/apt/lists/*

# Install rustup (stable toolchain) so cargo supports edition=2021
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
  && . /root/.cargo/env \
  && rustup default stable \
  && rustc --version \
  && cargo --version

# Copy requirements first for layer caching
COPY requirements.txt /app/requirements.txt

# Upgrade pip & install python deps
RUN pip install --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r /app/requirements.txt

# Copy app source
COPY . /app

EXPOSE 8000

CMD ["uvicorn", "mains:app", "--host", "0.0.0.0", "--port", "8000"]
