# AI Coding Agent Instructions - KitKool Web Bot

## Project Overview
FastAPI-based RAG chatbot platform with dual services: **main.py** (port 8000) for chat widgets & admin, **my_agent.py** (port 8001) for voice assistant. Uses FAISS for vector embeddings, SQLAlchemy with SQLite, and OpenAI GPT-4o for RAG responses.

## Architecture

### Dual-Service Model
- **main.py**: Chat widget system, URL injection, admin/user auth, contact management
- **my_agent.py**: Voice assistant with WebSocket support, separate from main chat service
- Run both: `uvicorn main:app --reload --host 0.0.0.0 --port 8000` and `uvicorn my_agent:app --reload --host 0.0.0.0 --port 8001`

### Core Components
- **Vector Store**: FAISS-based (`utils/vector_store.py`) - stores website content + chat history as 384-dim embeddings using `paraphrase-multilingual-MiniLM-L12-v2`
- **Prompt Engine**: `utils/prompt_engine.py` - critical conversation flow controller with `CONVERSATION_ENDED` and `REQUEST_CONTACT_INFO` triggers
- **Service Layer**: Manager/Service pattern in `utils/` - `FirmManager`, `ContactManager`, `TaskManager`, `AdminAuthService`, `UserAuthService`, `URLProcessingService`
- **Background Tasks**: Async URL processing via `TaskManager` (max 3 concurrent)

### Data Flow
1. User submits URL → `FirmManager.get_or_create_firm_from_url()` extracts firm name → `TaskManager.create_task()`
2. Background scraper (`utils/scraper.py`) crawls max 10,000 pages (5 concurrent)
3. Text chunks → FAISS embeddings → persist to `rag_db_faiss/`
4. Chat query → RAG retrieval → `utils/llm_tools.py` calls GPT-4o with context
5. Prompt engine checks for `CONVERSATION_ENDED`/`REQUEST_CONTACT_INFO` signals → triggers popup

## Critical Patterns

### Prompt Engine Behavior (MUST PRESERVE)
In `utils/prompt_engine.py`, the prompt template has TWO priority checks that MUST come first:
1. **Contact request detection**: Keywords like "take my info", "contact me" → respond with `REQUEST_CONTACT_INFO` on new line
2. **Conversation end detection**: Keywords like "thanks", "bye", "got it" → respond with `CONVERSATION_ENDED`

Frontend (e.g., `static/js/widgets.js`) parses these signals to show contact forms. Never modify this logic without preserving signal detection.

### LLM Fallback Pattern
`utils/llm_tools.py` implements retry-with-fallback:
- Try LangChain `ChatOpenAI` first (3 retries, exponential backoff)
- Fallback to direct OpenAI client if LangChain fails
- Custom API key support via `call_llm_with_fallback(custom_api_key="...")`

### Service Singletons
Services are instantiated at module level in `main.py`:
```python
contact_mgr = ContactManager()
admin_auth_service, user_auth_service, url_processing_service, task_manager
```
Import these singletons, don't create new instances.

### Session-Based Storage
Both chat messages and scraped content use `session_id` in metadata. FAISS stores everything in one index with discriminating metadata:
- `{"role": "user", "session_id": "...", "firm_id": "..."}`
- `{"url": "...", "chunk_index": 0, "scraped_at": "..."}`

## Database

### Models Location
- `model/models.py`: Firm, Website, Page, Link, Contact
- `model/admin_models.py`: AdminUser, AdminSession
- `model/user_models.py`: User, UserSession
- `model/url_injection_models.py`: URLInjectionRequest

### Migration System
**ALWAYS use migration system for schema changes**:
```bash
python migrate.py           # Apply changes from model files
python migrate.py --preview # Preview changes without applying
migrate.bat                 # Windows shortcut
```
Migration auto-detects new models/columns from `model/*.py` and applies them safely with automatic backups. See `MIGRATION_QUICK_START.md`.

### Database URLs (config.py)
- `DATABASE_URL`: Main app DB (firms, users, admin) - defaults to `sqlite:///./kitkool_bot.db`

## Configuration

### Environment Variables (.env)
```
OPENAI_API_KEY, DEEPGRAM_API_KEY, CARTESIA_API_KEY
DATABASE_URL=sqlite:///./kitkool_bot.db
SECRET_KEY, DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD
SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS (for contact emails)
WIDGET_BASE_URL=http://127.0.0.1:8000/
FAISS_PERSIST_DIRECTORY=./rag_db_faiss
Model_name=gpt-4o
```

### Key Config Locations
- `loges.py`: Logging setup (imported at startup)
- `requirements.txt`: Python 3.9 < 3.11 required

## Development Workflow

### Running Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python -c "from database.db import init_db; init_db()"

# Run main service
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Run voice service (separate terminal)
uvicorn my_agent:app --reload --host 0.0.0.0 --port 8001
```

### Docker Deployment
```bash
docker-compose up -d --build
docker-compose logs -f
docker-compose down
```

### Key Routes
- Admin: `/admin`, `/admin/signup`, `/admin/login`
- User: `/signup`, `/login`, `/dashboard`
- Widgets: `/widget`, `/widget/firm-info`
- Chat: `/chat`, `/chat/url-specific`
- URL Injection: `/inject-url`, `/task-status/{task_id}`
- Voice: `/voice`, `/ws/voice` (WebSocket)

## Testing & Debugging

### Manual Testing Files
- `static/test_injection.html`: URL injection testing
- `static/simple_index.html`: Basic widget testing
- `test_v_agent.py`: Voice agent testing

### Common Issues
1. **FAISS index corruption**: Delete `rag_db_faiss/` directory to reset
2. **Token parallelism warning**: Already handled via `os.environ["TOKENIZERS_PARALLELISM"] = "false"`
3. **OpenAI timeouts**: `llm_tools.py` has 30s timeout + 3 retries built in
4. **Migration conflicts**: Use `python migrate.py --preview` first

## Code Conventions

### Import Order
Standard library → Third-party → Local (see `main.py` lines 1-40)

### Error Handling
Always wrap LLM calls in try-except with fallback:
```python
try:
    response = call_llm_with_fallback(prompt_text)
except Exception as e:
    print(f"LLM call failed: {e}")
    return JSONResponse({"error": "AI service unavailable"}, 500)
```

### Async Patterns
- Background tasks via `asyncio.create_task()` in `TaskManager`
- Use `httpx.AsyncClient` for concurrent web scraping (max 5 concurrent in `scraper.py`)

### Validation
Pydantic schemas in `model/validation_schema.py` for all API endpoints

## Widget Integration

### Embedding Pattern
```html
<script src="http://127.0.0.1:8000/static/js/launcher.js"></script>
<script>
  ChatWidget.init({
    baseUrl: 'http://127.0.0.1:8000',
    firmId: 'your-firm-id'
  });
</script>
```

### CORS Configuration
`main.py` sets `frame-ancestors` based on `ALLOWED_IFRAME_ORIGINS` env var. Update for production domains.

## Voice Assistant (my_agent.py)

### Architecture
- WebSocket endpoint `/ws/voice` handles audio streaming
- `VoiceAssistant` class in `voice_config/voice_helper.py`
- SQL agent with `langchain_community.agent_toolkits.SQLDatabaseToolkit` for database queries
- Separate FAISS index for voice RAG in `voice_config/rag_searcher.py`

### Voice Flow
1. Client sends base64-encoded audio
2. `VoiceAssistant.process_audio()` → transcription
3. SQL agent queries database OR RAG search
4. Response synthesized to audio
5. Send back to client

## Security Notes

### Middleware
- `SecurityHeadersMiddleware` adds CSP, X-Frame-Options, HSTS
- Session-based auth for admin/users (tokens in `AdminSession`/`UserSession` tables)
- Password hashing via `bcrypt` in auth services

### Query Sanitization
`utils/query_senetizer.py` validates user inputs before RAG queries

## When Modifying This Project

✅ **DO:**
- Use migration system for any model changes
- Test prompt engine changes against `REQUEST_CONTACT_INFO`/`CONVERSATION_ENDED` flows
- Preserve service singleton pattern
- Add proper error handling around LLM calls
- Update both services (main.py + my_agent.py) if shared functionality changes

❌ **DON'T:**
- Manually edit database schema (use migrations)
- Create new service instances (import existing singletons)
- Remove prompt engine signal detection logic
- Skip testing widget integration after frontend changes
- Forget to update requirements.txt for new dependencies

## Additional Resources
- `README.md`: Deployment commands and basic setup
- `MIGRATION_GUIDE.md`: Complete migration system documentation
- `MIGRATION_QUICK_START.md`: Quick migration reference
