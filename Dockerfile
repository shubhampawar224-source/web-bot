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


# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install -r requirements.txt
# RUN pip install -U langchain-community langchain-openai

# Copy project files
COPY . .

# Expose port
EXPOSE 8000

# Start FastAPI using Uvicorn
CMD ["uvicorn", "mains:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
