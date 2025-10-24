import io
import os
import base64
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit,create_sql_agent
from langchain.agents import AgentType
from langchain.memory import ConversationBufferMemory
from collections import defaultdict
from langchain.prompts import PromptTemplate
from database.db import SessionLocal
import re
import json
from sqlalchemy import or_, func
from sqlalchemy.orm import Session
from model.models import Website, Firm
from voice_config.prompt_manager import voice_prompt

# Load environment variables
load_dotenv(override=True)
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Please set OPENAI_API_KEY in your .env file")
db_uri = os.getenv("DATABASE_URI","")
if not db_uri:
    raise RuntimeError("Please set DATABASE_URI in your .env file")


# ========================================
# MEMORY MANAGER
# ========================================
class MemoryManager:
    """Manages conversation memory for each WebSocket session."""
    def __init__(self, expiry_seconds: int = 1800):
        self.memories = defaultdict(lambda: {"memory": ConversationBufferMemory(), "last_access": time.time()})
        self.expiry_seconds = expiry_seconds

    def get_memory(self, session_id: str):
        self.cleanup()
        self.memories[session_id]["last_access"] = time.time()
        return self.memories[session_id]["memory"]

    def cleanup(self):
        now = time.time()
        expired = [sid for sid, data in self.memories.items() if now - data["last_access"] > self.expiry_seconds]
        for sid in expired:
            del self.memories[sid]

# -------------------------------
# Recursive JSON search utility
# -------------------------------
def json_contains_keyword(data, keyword: str) -> bool:
    """Recursively check if keyword exists in JSON object or array."""
    if isinstance(data, dict):
        return any(json_contains_keyword(v, keyword) for v in data.values())
    elif isinstance(data, list):
        return any(json_contains_keyword(i, keyword) for i in data)
    elif isinstance(data, str):
        return keyword.lower() in data.lower()
    return False

# -------------------------------
# Database searcher with recursive JSON
# -------------------------------
class DatabaseSearcher:
    def __init__(self, db_session: Session):
        self.session = db_session

    def search(self, keyword: str) -> str:
        keyword_lower = keyword.lower()

        # 1️⃣ Relational fields
        relational_results = (
            self.session.query(Website)
            .join(Firm)
            .filter(
                or_(
                    Website.domain.ilike(f"%{keyword}%"),
                    Website.base_url.ilike(f"%{keyword}%"),
                    Firm.name.ilike(f"%{keyword}%")
                )
            )
            .all()
        )

        # 2️⃣ JSON fields (recursive search)
        json_results = []
        for website in self.session.query(Website).all():
            if json_contains_keyword(website.scraped_data, keyword_lower):
                json_results.append(website)

        # Combine uniquely
        all_results = {w.id: w for w in relational_results + json_results}

        # 3️⃣ Format results safely
        formatted_results = [self._format_website(w) for w in all_results.values()]

        # Ensure all are strings
        formatted_results_str = [str(r) for r in formatted_results]

        return "\n\n".join(formatted_results_str) if formatted_results_str else "No information found in the database."

    def _format_website(self, website: Website) -> str:
        """Convert Website object into human-readable text safely."""
        about = website.scraped_data.get("about", {})
        links = website.scraped_data.get("links", [])

        text = f"Website domain: {website.domain}\n"

        # Convert dict to string safely
        if isinstance(about, dict) and about:
            text += f"About info: {json.dumps(about, ensure_ascii=False)}\n"

        # Convert links list elements to string safely
        if isinstance(links, list) and links:
            text += f"Links: {', '.join([str(l) for l in links])}\n"

        return text
#----------------------------
# Voice Assistant
# -------------------------------
class VoiceAssistant:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_KEY)
        self.memory_manager = MemoryManager()
        self.session = SessionLocal()  # SQLAlchemy session

        # DB searcher
        self.db_searcher = DatabaseSearcher(self.session)

        # LangChain agent
        self.db = SQLDatabase.from_uri(db_uri)
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)

        self.voice_agent = create_sql_agent(
            llm=self.llm,
            toolkit=self.toolkit,
            verbose=True,
            handle_parsing_errors=True,
            agent_type="openai-tools",
            prompt=PromptTemplate(template=voice_prompt(), input_variables=["input"])
        )

    async def process_audio(self, ws: WebSocket, audio_bytes: bytes, session_id: str):
        """STT → DB search → Agent → TTS"""
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "input.wav"

        # 1️⃣ Speech-to-text
        try:
            stt_resp = self.client.audio.transcriptions.create(model="whisper-1", file=audio_file)
            user_text = stt_resp.text.strip()
        except Exception as e:
            print(f"STT Error: {e}")
            await self.safe_send(ws, "Sorry, I couldn't understand you clearly.")
            return None

        if not user_text:
            return None

        print(f"🧠 User said: {user_text}")

        # 2️⃣ Exit conditions
        if any(kw in user_text.lower() for kw in ["bye", "goodbye","thank you","thanks","exit","stop"]):
            farewell = "Goodbye! Have a great day!"
            await self.safe_send(ws, farewell)
            return "exit"

        # 3️⃣ Search database content
        search_content = self.db_searcher.search(user_text)

        # 4️⃣ Query the agent with search content
        bot_text = await self.ask_agent(session_id, user_text, search_content)

        # 5️⃣ Respond with TTS
        await self.safe_send(ws, bot_text)
        return None

    async def ask_agent(self, session_id: str, user_text: str, search_content: str) -> str:
        """Query the SQL agent with filtered DB content."""
        try:
            memory = self.memory_manager.get_memory(session_id)
            conversation_context = "\n".join(
                [f"User: {m.content}" if m.type == "human" else f"Bot: {m.content}"
                 for m in memory.chat_memory.messages]
            )
            full_context = f"{conversation_context}\nDatabase info:\n{search_content}\nUser: {user_text}"

            result = self.voice_agent.invoke({"input": full_context})

            # Extract text
            bot_text = result.get("output", "") if isinstance(result, dict) else str(result)

            # Clean dates / IDs
            bot_text = re.sub(r"(created on|[0-9]{4}-[0-9]{2}-[0-9]{2})", "", bot_text, flags=re.I).strip()

            # Save to memory
            memory.chat_memory.add_user_message(user_text)
            memory.chat_memory.add_ai_message(bot_text)

            return bot_text if bot_text else "Sorry, no information found."

        except Exception as e:
            print(f"❌ Agent error: {e}")
            return "Sorry, I encountered an issue while processing your request."

    async def safe_send(self, ws: WebSocket, text: str):
        """Convert text to speech and send over WebSocket."""
        try:
            tts = self.client.audio.speech.create(model="tts-1", voice="alloy", input=text)
            audio_b64 = base64.b64encode(io.BytesIO(tts.read()).getvalue()).decode()
            if ws.client_state.name == "CONNECTED":
                await ws.send_json({"bot_text": text, "audio": audio_b64})
            else:
                print("⚠️ Tried to send after disconnect")
        except Exception as e:
            print(f"TTS Error: {e}")
            if ws.client_state.name == "CONNECTED":
                await ws.send_json({"bot_text": "Sorry, I couldn’t speak the response.", "audio": ""})
