import asyncio
import io
import os
import re
import json
import base64
import time
import uuid
from fastapi import WebSocket
from collections import defaultdict
from dotenv import load_dotenv
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.memory import ConversationSummaryBufferMemory
from langchain.agents import create_sql_agent, AgentType
from sqlalchemy import inspect
from voice_config.prompt_manager import voice_rag_prompt

# ========================================
# ENVIRONMENT
# ========================================
load_dotenv(override=True)
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
# Use the main application database that contains firms, websites, and pages data
db_uri = os.getenv("DATABASE_URL", "sqlite:///./kitkool_bot.db")

if not OPENAI_KEY:
    raise RuntimeError("Please set OPENAI_API_KEY in .env")

# ========================================
# DYNAMIC SCHEMA HANDLER
# ========================================
def get_allowed_columns(db: SQLDatabase):
    """Auto-detect table names and their columns dynamically."""
    try:
        inspector = inspect(db._engine)
        schema_summary = {}

        for table_name in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns(table_name)]
            schema_summary[table_name] = columns

        return schema_summary
    except Exception as e:
        print(f"⚠️ Schema introspection failed: {e}")
        return {}


def summarize_schema(db: SQLDatabase, max_cols=8):
    """Generate a compact schema summary for prompts (avoids large schema dumps)."""
    inspector = inspect(db._engine)
    summaries = []
    for table in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns(table)]
        if len(cols) > max_cols:
            cols = cols[:max_cols] + ["..."]
        summaries.append(f"{table}({', '.join(cols)})")
    return "; ".join(summaries)


# ========================================
# MEMORY MANAGER
# ========================================
class MemoryManager:
    """Manages session-based memory with expiration."""
    def __init__(self, expiry_seconds: int = 1800):
        self.memories = defaultdict(
            lambda: {
                "memory": ConversationSummaryBufferMemory(
                    llm=ChatOpenAI(model="gpt-4o-mini", temperature=0),
                    max_token_limit=1000
                ),
                "last_access": time.time()
            }
        )
        self.expiry_seconds = expiry_seconds

    def get_memory(self, session_id: str):
        self.cleanup()
        self.memories[session_id]["last_access"] = time.time()
        return self.memories[session_id]["memory"]

    def cleanup(self):
        now = time.time()
        expired = [sid for sid, data in self.memories.items()
                   if now - data["last_access"] > self.expiry_seconds]
        for sid in expired:
            del self.memories[sid]

# ========================================
# VOICE ASSISTANT CLASS
# ========================================

class VoiceAssistant:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_KEY)
        self.memory_manager = MemoryManager()

        # --- Database setup ---
        self.db = SQLDatabase.from_uri(db_uri)
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

        # --- Dynamic schema mapping ---
        allowed_columns = get_allowed_columns(self.db)
        schema_summary = summarize_schema(self.db)

        # --- Toolkit with dynamic schema ---
        self.toolkit = SQLDatabaseToolkit(
            db=self.db,
            llm=self.llm,
            allowed_columns=allowed_columns
        )

        # --- Custom prompt with actual schema summary ---
        self.prompt = voice_rag_prompt(schema_summary)

        # --- SQL Agent ---
        self.voice_agent = create_sql_agent(
            llm=self.llm,
            toolkit=self.toolkit,
            verbose=False,
            handle_parsing_errors=True,
            agent_type=AgentType.OPENAI_FUNCTIONS,
            prompt=self.prompt,
        )

    # -------------------------
    # WebSocket Handling
    # -------------------------
    SILENCE_TIMEOUT = 10  # seconds

    async def handle_ws(self, ws: WebSocket):
        await ws.accept()
        session_id = str(uuid.uuid4())
        ws.session_id = session_id
        await ws.send_json({"info": "Session created", "session_id": session_id})

        silence_task = asyncio.create_task(self.silence_watchdog(ws))

        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)

                # Stop connection
                if msg.get("stop"):
                    silence_task.cancel()
                    await ws.close()
                    break

                # Handle audio
                audio_b64 = msg.get("audio")
                if audio_b64:
                    audio_bytes = base64.b64decode(audio_b64)
                    silence_task.cancel()
                    silence_task = asyncio.create_task(self.silence_watchdog(ws))
                    await self.process_audio(ws, audio_bytes, ws.session_id)

        except Exception as e:
            print(f"WebSocket error: {e}")
            await ws.close()
            silence_task.cancel()

    async def silence_watchdog(self, ws: WebSocket):
        try:
            await asyncio.sleep(self.SILENCE_TIMEOUT)
            if ws.client_state.name == "CONNECTED":
                await ws.send_json({"bot_text": "No input detected. Ending the session.", "audio": ""})
                await ws.close()
        except asyncio.CancelledError:
            pass

    # -------------------------
    # Audio -> Text -> Agent
    # -------------------------
    async def process_audio(self, ws: WebSocket, audio_bytes: bytes, session_id: str):
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "input.wav"

        try:
            stt_resp = self.client.audio.transcriptions.create(
                model="whisper-1", file=audio_file
            )
            user_text = stt_resp.text.strip()
        except Exception as e:
            print(f"STT Error: {e}")
            await self.safe_send(ws, "Sorry, I couldn't understand you clearly.")
            return None

        if not user_text:
            return None

        print(f"🧠 User said: {user_text}")

        if any(kw in user_text.lower() for kw in ["bye","thanks", "exit", "stop", "thanks"]):
            await self.safe_send(ws, "Goodbye! Have a great day!")
            return "exit"

        bot_text = await self.ask_agent(session_id, user_text)
        await self.safe_send(ws, bot_text)
        return None

    # -------------------------
    # Agent Processing
    # -------------------------
    async def ask_agent(self, session_id: str, user_text: str) -> str:
        try:
            memory = self.memory_manager.get_memory(session_id)
            memory.chat_memory.add_user_message(user_text)

            # Add context to help the agent understand it's a voice interface
            enhanced_input = f"Voice query: {user_text}"
            
            result = self.voice_agent.invoke({"input": enhanced_input})
            bot_text = result.get("output", "") if isinstance(result, dict) else str(result)

            # Clean up the response for voice output
            bot_text = self.clean_response(bot_text, user_text)
            
            if not bot_text or len(bot_text.strip()) < 5:
                bot_text = "I'm sorry, I couldn't find the information you're looking for. Could you try asking in a different way?"

            memory.chat_memory.add_ai_message(bot_text)
            return bot_text

        except Exception as e:
            print(f"❌ Agent error: {e}")
            return "I'm sorry, I encountered an issue while searching for that information. Please try again."
    
    def clean_response(self, text: str, user_text: str) -> str:
        """Clean and optimize response for voice output"""
        if not text:
            return ""
            
        # Remove common SQL/technical artifacts
        text = re.sub(r"(User:|Bot:|Assistant:|Human:|created on|\d{4}-\d{2}-\d{2})", "", text, flags=re.I)
        text = re.sub(r"Voice query:", "", text, flags=re.I)
        text = re.sub(r"JSON_EXTRACT|scraped_data|sql|query", "", text, flags=re.I)
        text = text.replace(user_text, "").strip()
        
        # Remove excessive whitespace and newlines
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        # Remove any remaining technical jargon
        text = re.sub(r'\$\.\w+\.[\w.]+', '', text)  # Remove JSON path expressions
        text = re.sub(r'LIKE\s*%\w+%', '', text, flags=re.I)  # Remove SQL LIKE expressions
        
        # Ensure response is conversational
        if text and not text.endswith(('?', '.', '!', ':')):
            text += "."
            
        return text

    # -------------------------
    # Text-to-speech + Send
    # -------------------------
    async def safe_send(self, ws: WebSocket, text: str):
        try:
            tts = self.client.audio.speech.create(
                model="tts-1", voice="alloy", input=text
            )
            audio_stream = io.BytesIO(tts.read())
            audio_b64 = base64.b64encode(audio_stream.getvalue()).decode()

            if ws.client_state.name == "CONNECTED":
                await ws.send_json({"bot_text": text, "audio": audio_b64})
        except Exception as e:
            print(f"TTS Error: {e}")
            if ws.client_state.name == "CONNECTED":
                await ws.send_json({"bot_text": "I couldn't speak the response.", "audio": ""})
