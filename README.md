# FastAPI RAG Chatbot with ChromaDB

This project implements a **session-based chatbot** using **FastAPI**, **SentenceTransformers embeddings**, and **Chroma vector database** for **Retrieval-Augmented Generation (RAG)**. It allows storing website content and chat history as vectors and retrieving relevant context during a conversation.

---

## Features

- Load website content and store as vectors in ChromaDB.
- Session-based chat: user and assistant messages are stored with `session_id`.
- RAG pipeline: queries are matched against website vectors for context.
- Inspect vectors at query time for debugging.
- Persistent vector storage with ChromaDB.
- Disable HuggingFace tokenizer parallelism warning.

---

## Requirements

- Python 3.9 <3.11
- [FastAPI](https://fastapi.tiangolo.com/)
- [Uvicorn](https://www.uvicorn.org/)
- [SentenceTransformers](https://www.sbert.net/)
- [ChromaDB](https://docs.trychroma.com/)

Install dependencies:

```bash
pip install fastapi uvicorn sentence-transformers chromadb
pip install -r reuirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000


## for docker deploy 
# go to the web-bot
docker compose build --no-cache docker compose up -d
or 
# Simple deployment
sudo docker-compose up -d --build

# View logs
sudo docker-compose logs -f

# Stop
sudo docker-compose down


for voice bot
uvicorn my_agent:app --reload --host 0.0.0.0 --port 8000
# use also this for run and deploy app

my server widgets,admin and user 
http://127.0.0.1:8000/admin
http://127.0.0.1:8000/widget
http://localhost:8000/new_wg
https://mickie-springy-unaccusingly.ngrok-free.dev/dashboard