# 🤖 KitKool Web Bot - Agentic RAG Chatbot

AI-powered web chatbot with **Agentic RAG**, voice assistant, and intelligent multi-query search for accurate, context-aware responses.

---

## 🚀 Tech Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | FastAPI (Python 3.9-3.11) |
| **AI/LLM** | OpenAI GPT-4o |
| **Vector DB** | FAISS + ChromaDB-compatible wrapper |
| **Embeddings** | SentenceTransformers (paraphrase-multilingual-MiniLM-L12-v2) |
| **Database** | SQLite (SQLAlchemy ORM) |
| **Voice AI** | OpenAI Whisper STT + OpenAI TTS (English-only) |
| **Web Scraping** | BeautifulSoup4 + httpx (async) |

---

## ✨ Features

- 🔍 **Agentic RAG**: Auto-generates multiple search queries for fuzzy/vague questions
- 🎤 **Voice Assistant**: Real-time voice interaction via WebSocket (English-only)
- 📊 **Admin Dashboard**: Manage firms, websites, users, and chat analytics
- 🌐 **Smart Web Scraping**: Prioritizes footer content (hours, contact, address)
- 💬 **Session-Based Chat**: Maintains conversation context
- 📈 **Vector Search**: FAISS indexing for fast semantic retrieval
- 📋 **Manual Knowledge**: Upload custom documents via admin panel

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
```

### 3. Start Servers

**Main Chat Server (Port 8000):**
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Voice Assistant (Port 8000):**
```bash
# Access voice bot via WebSocket at /voice endpoint
# Frontend: /voice.html
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


## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Main chat interface |
| `/inject-url` | POST | Scrape & index website |
| `/admin/dashboard` | GET | Admin panel |
| `/voice` | WebSocket | Voice assistant (English-only) |
| `/admin/upload-knowledge` | POST | Upload manual knowledge |
| `/firms` | GET | List all firms |

---

## 🧠 Agentic Search

When traditional RAG finds <3 results, **Agentic Search** activates:
1. LLM generates 3-5 query variations
2. Each query searches vector DB independently  
3. Results merged & deduplicated
4. Best matches returned

---

## 📁 Project Structure

```
web-bot/
├── main.py                 # Main FastAPI app (port 8000)
├── my_agent.py            # Legacy voice assistant file
├── requirements.txt       # Dependencies
├── database/
│   └── db.py             # SQLAlchemy models
├── model/                # Pydantic schemas
├── utils/
│   ├── llm_tools.py      # RAG + LLM logic
│   ├── agentic_search.py # Intelligent multi-query search
│   ├── scraper.py        # Web scraping (footer priority)
│   ├── vector_store.py   # FAISS wrapper
│   └── voice_bot_helper.py
├── voice_config/
│   ├── voice_helper.py   # Voice assistant WebSocket handler
│   └── simple_rag_agent.py # Enhanced RAG agent for voice
├── static/               # Frontend HTML/CSS/JS
└── rag_db_faiss/         # Vector store persistence
```

---

## 🔧 Key Scripts

# Migration
python migrate.py
```

---

## 📊 Database Models

- **Firm**: Client organizations
- **Website**: Scraped website data
- **ChatHistory**: Conversation logs
- **User**: End users
- **Admin**: Admin users

---

## 🤝 Contributing

1. Fork the repo
2. Create feature branch: `git checkout -b feature/amazing`
3. Commit: `git commit -m 'Add amazing feature'`
4. Push: `git push origin feature/amazing`
5. Open Pull Request

---
## 💡 Pro Tips

- Use **footer-focused scraping** for contact info
- **Agentic search** automatically activates for poor results
- Monitor console for `🔄 Activating Agentic Search` logs
- **Voice bot** uses OpenAI Whisper + TTS (English-only enforcement)
- Upload **manual knowledge** via admin panel for firm-specific info
- Re-scrape websites after scraper updates to populate FAISS

---

## 🎤 Voice Bot Features

- **English-only transcription** using OpenAI Whisper
- **Real-time WebSocket** communication
- **Enhanced RAG agent** with context merging
- **Automatic language detection** - rejects non-English input
- **Session management** with silence timeout
- **Contact info extraction** from both website and manual knowledge

---

**Made with ❤️ using FastAPI + OpenAI GPT-4o + Whisper**

## 🌐 Server URLs
- **Admin Panel**: http://127.0.0.1:8000/admin  
- **Widget Demo**: http://127.0.0.1:8000/widget  
- **Chat Interface**: http://localhost:8000/djf-bot
- **Voice Bot**: http://localhost:8000/voice
