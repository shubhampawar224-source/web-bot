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
# Build and run
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

---

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Main chat interface |
| `/inject-url` | POST | Scrape & index website |
| `/admin/dashboard` | GET | Admin panel |
| `/voice-chat` | WebSocket | Voice assistant |
| `/health` | GET | Server health check |

---

## 🧠 Agentic Search

When traditional RAG finds <3 results, **Agentic Search** activates:
1. LLM generates 3-5 query variations
2. Each query searches vector DB independently  
3. Results merged & deduplicated
4. Best matches returned

**Example:**
```
User: "hours and operations" 
  ↓ Agentic generates:
  - "business hours"
  - "opening closing time"
  - "office schedule"
  ↓ Result: 5+ documents found ✅
```

---

## 📁 Project Structure

```
web-bot/
├── main.py                 # Main FastAPI app (port 8000)
├── my_agent.py            # Voice assistant (port 8001)
├── config.py              # Environment config
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
├── routers/              # API routes
├── static/               # Frontend HTML/CSS/JS
└── rag_db_faiss/         # Vector store persistence
```

---

## 🔧 Key Scripts

```bash
# Reindex websites to FAISS
python reindex_websites.py

# Setup database
python setup_database.py

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

## 📄 License

MIT License - See LICENSE file

---

## 💡 Pro Tips

- Use **footer-focused scraping** for contact info
- **Agentic search** automatically activates for poor results
- Monitor console for `🔄 Activating Agentic Search` logs
- Voice bot requires LiveKit WebRTC server
- Re-scrape websites after scraper updates to populate FAISS

---

**Made with ❤️ using FastAPI + OpenAI GPT-4.1**

my server widgets,admin and user 
http://127.0.0.1:8000/admin
http://127.0.0.1:8000/widget
http://localhost:8000/djf-bot
