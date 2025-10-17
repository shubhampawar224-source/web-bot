#!/bin/bash

# -----------------------------
# FastAPI RAG Chatbot Deployment Script
# -----------------------------

# Exit on error
set -e

echo "🚀 Starting deployment..."

# 1. Check for Python 3.9+
if ! python3 --version &>/dev/null; then
    echo "Python3 not found. Please install Python 3.9+"
    exit 1
fi

# 2. Create virtual environment
VENV_DIR="venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv $VENV_DIR
fi

# 3. Activate virtual environment
echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

# 4. Upgrade pip
pip install --upgrade pip

# 5. Install dependencies
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    pip install -r requirements.txt
else
    echo "requirements.txt not found!"
    exit 1
fi

# 6. Create rag_db directory if not exists
if [ ! -d "rag_db" ]; then
    echo "Creating ChromaDB directory..."
    mkdir -p rag_db
fi

# 7. Run FastAPI app using uvicorn
echo "Starting FastAPI server at http://127.0.0.1:8000 ..."
uvicorn mains:app --host 0.0.0.0 --port 8000 --reload
