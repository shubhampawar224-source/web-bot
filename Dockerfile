# # Base image
# FROM python:3.11-slim

# # Set working directory
# WORKDIR /app

# # Install system dependencies for audio + build tools
# RUN apt-get update && apt-get install -y \
#     gcc \
#     g++ \
#     make \
#     python3-dev \
#     ffmpeg \
#     libsndfile1 \
#     ca-certificates \
#     && rm -rf /var/lib/apt/lists/*

# ENV HF_HOME=/root/.cache/huggingface


# # Copy requirements first for caching
# COPY requirements.txt .

# # Install Python dependencies
# RUN pip install --upgrade pip
# RUN pip install --no-cache-dir -r requirements.txt
# # RUN pip install -U langchain-community langchain-openai

# # Copy project files
# COPY . .

# # Expose port
# EXPOSE 8000

# # Start FastAPI using Uvicorn
# CMD ["uvicorn", "mains:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# Base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for audio + build tools
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    python3-dev \
    ffmpeg \
    libsndfile1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV HF_HOME=/root/.cache/huggingface

# Copy only requirements to leverage cache
COPY requirements.txt .

# Install Python dependencies (BuildKit-independent)
# Using `--no-cache-dir` prevents pip from leaving cache in image layers.
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy rest of the project
COPY . .

# Expose port
EXPOSE 8000

# Start FastAPI
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
