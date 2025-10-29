# file: voice_ws_app.py
import asyncio
import io
import os
import re
import json
import base64
import time
import uuid
import logging
from typing import Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from collections import defaultdict
from dotenv import load_dotenv

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.memory import ConversationSummaryBufferMemory
from langchain.agents import create_sql_agent, AgentType
from sqlalchemy import inspect

from voice_config.prompt_manager import voice_rag_prompt  # your prompt factory (accepts schema summary)

# -----------------------
# Configuration + logging
# -----------------------
load_dotenv(override=True)
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
DB_URI = os.getenv("DATABASE_URI", "sqlite:///voice_data.db")
SILENCE_TIMEOUT = int(os.getenv("SILENCE_TIMEOUT", "10"))  # seconds before auto-closing
INTENT_MODEL = os.getenv("INTENT_MODEL", "gpt-4o-mini")     # small classifier
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")         # fallback chat
TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")       # tts model
STT_MODEL = os.getenv("STT_MODEL", "whisper-1")            # speech-to-text

if not OPENAI_KEY:
    raise RuntimeError("Please set OPENAI_API_KEY in environment (.env)")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-assistant")

# -----------------------
# FastAPI app
# -----------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_methods=["*"],
    allow_headers=["*"],
)
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/voice")
async def get_index():
    return FileResponse("static/voice.html")


# -----------------------
# Utilities: DB schema
# -----------------------
def get_allowed_columns(db: SQLDatabase) -> Dict[str, list]:
    """Return content-focused allowed columns per table (fallback to name/title)."""
    try:
        inspector = inspect(db._engine)
        out = {}
        text_keywords = ["content", "text", "body", "description", "notes", "details", "scraped", "about"]
        for table in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns(table)]
            allowed = [c for c in cols if any(k in c.lower() for k in text_keywords)]
            if not allowed:
                allowed = [c for c in cols if c.lower() in ("name", "title")]
            out[table] = allowed
        logger.info("Allowed columns: %s", out)
        return out
    except Exception as e:
        logger.exception("Schema introspection failed: %s", e)
        return {}

def summarize_schema(db: SQLDatabase, max_cols=8) -> str:
    """Compact schema summary for use inside prompts (not the full dump)."""
    try:
        inspector = inspect(db._engine)
        summaries = []
        for table in inspector.get_table_names():
            cols = [c["name"] for c in inspector.get_columns(table)]
            if len(cols) > max_cols:
                cols = cols[:max_cols] + ["..."]
            summaries.append(f"{table}({', '.join(cols)})")
        return "; ".join(summaries)
    except Exception as e:
        logger.exception("summarize_schema error: %s", e)
        return ""

# -----------------------
# Memory Manager
# -----------------------
class MemoryManager:
    def __init__(self, expiry_seconds: int = 1800):
        self.expiry_seconds = expiry_seconds
        self.memories = defaultdict(lambda: {
            "memory": ConversationSummaryBufferMemory(
                llm=ChatOpenAI(model=CHAT_MODEL, temperature=0),
                max_token_limit=1000
            ),
            "last_access": time.time()
        })

    def get_memory(self, session_id: str):
        self.cleanup()
        self.memories[session_id]["last_access"] = time.time()
        return self.memories[session_id]["memory"]

    def cleanup(self):
        now = time.time()
        expired = [sid for sid, data in self.memories.items() if now - data["last_access"] > self.expiry_seconds]
        for sid in expired:
            del self.memories[sid]

# -----------------------
# VoiceAssistant
# -----------------------
class VoiceAssistant:
    def __init__(self):
        # OpenAI low-level client (used for STT, TTS, quick chat completions)
        self.client = OpenAI(api_key=OPENAI_KEY)

        # Memory manager
        self.memory_manager = MemoryManager()

        # SQL DB + LangChain toolkit/agent
        self.db = SQLDatabase.from_uri(DB_URI)
        self.llm = ChatOpenAI(model=CHAT_MODEL, temperature=0)

        # Allowed columns and schema summary
        allowed_columns = get_allowed_columns(self.db)
        schema_summary = summarize_schema(self.db)

        # Toolkit: pass discovered allowed_columns to restrict queries
        self.toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm, allowed_columns=allowed_columns)

        # Keep a prompt template for chat-mode (you will format it with agent_scratchpad="")
        self.prompt_template = voice_rag_prompt(schema_summary)

        # Create SQL agent (OpenAI functions agent). Do NOT pass prompt here — toolkit has metadata.
        self.voice_agent = create_sql_agent(
            llm=self.llm,
            toolkit=self.toolkit,
            verbose=False,
            handle_parsing_errors=True,
            agent_type=AgentType.OPENAI_FUNCTIONS,
        )

    # ---- websocket helpers ----
    def is_ws_connected(self, ws: WebSocket) -> bool:
        return getattr(ws, "client_state", None) and ws.client_state.name == "CONNECTED"

    async def safe_close(self, ws: WebSocket, reason: str = ""):
        try:
            if self.is_ws_connected(ws):
                await ws.close(code=1000, reason=reason)
        except Exception:
            # ignore any close/send race
            pass

    # ---- STT ----
    def transcribe_audio(self, audio_bytes: bytes) -> str:
        """
        Synchronous wrapper around OpenAI STT call.
        Note: OpenAI client's methods are synchronous in this environment.
        """
        try:
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "input.wav"
            resp = self.client.audio.transcriptions.create(model=STT_MODEL, file=audio_file)
            return resp.text.strip()
        except Exception as e:
            logger.exception("STT error: %s", e)
            return ""

    # ---- TTS & send ----
    async def safe_send(self, ws: WebSocket, text: str):
        """Synthesize TTS and send JSON (bot_text + audio) if connected."""
        if not self.is_ws_connected(ws):
            return
        try:
            tts = self.client.audio.speech.create(model=TTS_MODEL, voice="alloy", input=text)
            buf = io.BytesIO(tts.read())
            audio_b64 = base64.b64encode(buf.getvalue()).decode()
            await ws.send_json({"bot_text": text, "audio": audio_b64})
        except Exception as e:
            logger.exception("TTS error: %s", e)
            # fallback: send text-only if possible
            try:
                if self.is_ws_connected(ws):
                    await ws.send_json({"bot_text": text, "audio": ""})
            except Exception:
                pass

    # ---- intent classification: 'db' or 'chat' ----
    def classify_intent_sync(self, user_text: str) -> str:
        """
        Use a tiny instruction to choose whether query requires DB lookup.
        Returns 'db' or 'chat'. Synchronous call to OpenAI.
        """
        try:
            system = "Decide if the user's message requires a database lookup (return only 'db' or 'chat')."
            resp = self.client.chat.completions.create(
                model=INTENT_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=6,
                temperature=0
            )
            text = resp.choices[0].message.get("content", "").strip().lower()
            if "db" in text:
                return "db"
            return "chat"
        except Exception as e:
            logger.exception("Intent classification error: %s", e)
            # Conservative default: treat as db if keywords present, else chat
            if re.search(r"\b(case|injury|lawsuit|client|firm|page|website|link|contact)\b", user_text, re.I):
                return "db"
            return "chat"

    # ---- fallback chat using your prompt template ----
    def chat_fallback_sync(self, user_text: str) -> str:
        """Uses the prompt_template and OpenAI chat for normal conversation responses."""
        try:
            # voice_rag_prompt expects input & agent_scratchpad variables.
            formatted = self.prompt_template.format(input=user_text, agent_scratchpad="")
            resp = self.client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": formatted},
                    {"role": "user", "content": user_text}
                ],
                max_tokens=512,
                temperature=0
            )
            return resp.choices[0].message.get("content", "").strip()
        except Exception as e:
            logger.exception("Chat fallback error: %s", e)
            return "I'm sorry, I couldn't process that. Could you rephrase?"

    # ---- SQL agent invocation ----
    def call_sql_agent_sync(self, user_text: str) -> str:
        """
        Invoke the LangChain SQL agent synchronously.
        Provide the user's natural text directly — the toolkit will generate SQL.
        """
        try:
            result = self.voice_agent.invoke({"input": user_text})
            if isinstance(result, dict):
                # LangChain agent may return a dict containing "output" or "result"
                out = result.get("output") or result.get("result") or str(result)
                return str(out).strip()
            return str(result).strip()
        except Exception as e:
            logger.exception("SQL agent error: %s", e)
            return "I couldn't retrieve data from the database right now."

    # ---- top-level processing pipeline ----
    async def process_audio_payload(self, ws: WebSocket, audio_bytes: bytes, session_id: str):
        user_text = self.transcribe_audio(audio_bytes)
        if not user_text:
            # nothing detected, ignore or notify
            if self.is_ws_connected(ws):
                await self.safe_send(ws, "Sorry, I couldn't understand you clearly.")
            return

        logger.info("🧠 User said: %s", user_text)

        # handle short exit phrases
        if any(kw in user_text.lower() for kw in ["bye", "goodbye", "exit", "stop", "thanks", "thank you"]):
            goodbye_text = "Goodbye! Have a great day!"
            await self.safe_send(ws, goodbye_text)
            await asyncio.sleep(0.5)
            await self.safe_close(ws, reason="user goodbye")
            logger.info("Session closed after goodbye.")
            return

        # choose path
        intent = self.classify_intent_sync(user_text)
        logger.info("Intent classified as: %s", intent)

        if intent == "db":
            # Use SQL agent
            bot_text = self.call_sql_agent_sync(user_text)
        else:
            # Chat fallback (use prompt)
            bot_text = self.chat_fallback_sync(user_text)

        if not bot_text:
            bot_text = "Hello! I'm sorry, I don't have that information. Is there anything else you'd like to know?"

        # save to memory
        try:
            memory = self.memory_manager.get_memory(session_id)
            memory.chat_memory.add_user_message(user_text)
            memory.chat_memory.add_ai_message(bot_text)
        except Exception:
            logger.debug("Memory save failed")

        await self.safe_send(ws, bot_text)

# -----------------------
# FastAPI WebSocket endpoint
# -----------------------
assistant = VoiceAssistant()

@app.websocket("/ws/voice")
async def ws_voice_endpoint(ws: WebSocket):
    await ws.accept()
    session_id = str(uuid.uuid4())
    ws.session_id = session_id

    # send session creation acknowledgment
    try:
        await ws.send_json({"info": "Session created", "session_id": session_id})
    except Exception:
        # if client disconnects early, just return
        await assistant.safe_close(ws)
        return

    # start silence watchdog
    silence_task = asyncio.create_task(silence_watchdog_helper(ws, assistant))

    try:
        while True:
            try:
                raw = await ws.receive_text()
            except WebSocketDisconnect:
                logger.info("Client disconnected")
                break
            except Exception as e:
                logger.exception("Receive error: %s", e)
                break

            # parse JSON
            try:
                msg = json.loads(raw)
            except Exception:
                logger.warning("Invalid JSON received: %s", raw)
                continue

            # stop command
            if msg.get("stop"):
                silence_task.cancel()
                await assistant.safe_close(ws, reason="stop requested")
                break

            # audio payload (base64)
            audio_b64 = msg.get("audio")
            if audio_b64:
                # Cancel and restart watchdog
                try:
                    silence_task.cancel()
                except Exception:
                    pass
                silence_task = asyncio.create_task(silence_watchdog_helper(ws, assistant))
                # decode and process
                try:
                    audio_bytes = base64.b64decode(audio_b64)
                except Exception:
                    logger.exception("Invalid base64 audio")
                    continue
                # process audio (synchronously inside sync wrappers) on background
                await assistant.process_audio_payload(ws, audio_bytes, session_id)

            # other messages (pause/resume/silence etc.) can be handled here
            if msg.get("silence"):
                # client says "silence" — optional handling
                logger.info("Client reported silence")
                continue

    except Exception as e:
        logger.exception("WebSocket main loop error: %s", e)
    finally:
        try:
            silence_task.cancel()
        except Exception:
            pass
        await assistant.safe_close(ws, reason="connection closed")
        logger.info("Connection cleaned up")


async def silence_watchdog_helper(ws: WebSocket, assistant: VoiceAssistant):
    """Helper coroutine that ends session after SILENCE_TIMEOUT seconds if no audio arrives."""
    try:
        await asyncio.sleep(SILENCE_TIMEOUT)
        if assistant.is_ws_connected(ws):
            await assistant.safe_send(ws, "No input detected. Ending the session.")
            await assistant.safe_close(ws, reason="silence timeout")
    except asyncio.CancelledError:
        # reset happened because audio arrived
        pass

# # -----------------------
# # If run as __main__, start uvicorn (dev)
# # -----------------------
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("voice_ws_app:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=True)
