# 🤖 KitKool Web Bot - Agentic RAG Chatbot

AI-powered web chatbot with **Agentic RAG**, voice assistant, and intelligent multi-query search for accurate, context-aware responses.

---

## 🚀 Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | FastAPI (Python 3.9-3.11) |
| **AI/LLM** | OpenAI GPT-4.1-preview |
| **Vector DB** | FAISS + ChromaDB-compatible wrapper |
| **Embeddings** | SentenceTransformers (paraphrase-multilingual-MiniLM-L12-v2) |
| **Database** | SQLite (SQLAlchemy ORM) |
| **Voice AI** | Deepgram STT + Cartesia TTS + LiveKit |
| **Web Scraping** | BeautifulSoup4 + httpx (async) |
| **Auth** | bcrypt + Google OAuth |

---

## ✨ Features

- 🔍 **Agentic RAG**: Auto-generates multiple search queries for fuzzy/vague questions
- 🎤 **Voice Assistant**: Real-time voice interaction via LiveKit
- 📊 **Admin Dashboard**: Manage firms, websites, users, and chat analytics
- 🌐 **Smart Web Scraping**: Prioritizes footer content (hours, contact, address)
- 💬 **Session-Based Chat**: Maintains conversation context
- 🔐 **Multi-Auth**: Admin/User with Google OAuth support
- 📈 **Vector Search**: FAISS indexing for fast semantic retrieval

---

## 🛠️ Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Create `.env` file:
```env
OPENAI_API_KEY=your_key_here
DEEPGRAM_API_KEY=your_key
CARTESIA_API_KEY=your_key
LIVEKIT_URL=wss://your-livekit-url
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret
SECRET_KEY=your-secret-key
```

### 3. Start Servers

**Main Chat Server (Port 8000):**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Voice Assistant (Port 8001):**
```bash
uvicorn my_agent:app --reload --host 0.0.0.0 --port 8001
```

---

## 🐳 Docker Deployment

```bash
pip install fastapi uvicorn sentence-transformers chromadb
pip install -r reuirements.txt
uvicorn mains:app --reload --host 0.0.0.0 --port 8000


## for docker deploy 
# go to the web-bot
docker compose build --no-cache docker compose up -d
or 
# Simple deployment
docker-compose up -d --build

# View logs
sudo docker-compose logs -f

# Stop
docker-compose down


for voice bot
uvicorn my_agent:app --reload --host 0.0.0.0 --port 8000
# use also this for run and deploy app

my server widgets,admin and user 
http://127.0.0.1:8000/admin
http://127.0.0.1:8000/widget
http://localhost:8000/new_wg
https://mickie-springy-unaccusingly.ngrok-free.dev/dashboard