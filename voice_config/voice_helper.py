import io
import os
import re
import base64
import time
from fastapi import WebSocket
from collections import defaultdict
from dotenv import load_dotenv
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.memory import ConversationSummaryBufferMemory
from langchain.agents import create_sql_agent, AgentType
from langchain.prompts import PromptTemplate
from voice_config.prompt_manager import voice_rag_prompt
# ========================================
# ENVIRONMENT
# ========================================
load_dotenv(override=True)
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
db_uri = "sqlite:///scraped_data.db"

if not OPENAI_KEY:
    raise RuntimeError("Please set OPENAI_API_KEY in .env")


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
        expired = [sid for sid, data in self.memories.items() if now - data["last_access"] > self.expiry_seconds]
        for sid in expired:
            del self.memories[sid]

# ========================================
# VOICE ASSISTANT CLASS
# ========================================
class VoiceAssistant:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_KEY)
        self.memory_manager = MemoryManager()

        # Database + toolkit with strict column filtering
        self.db = SQLDatabase.from_uri(db_uri)
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.toolkit = SQLDatabaseToolkit(
            db=self.db,
            llm=self.llm,
            allowed_columns={
                "firms": ["name", "created_at"],
                "websites": ["domain", "base_url", "scraped_data", "created_at"]
            }
        )
        # SQL agent with JSON-searchable prompt
        self.voice_agent = create_sql_agent(
            llm=self.llm,
            toolkit=self.toolkit,
            verbose=False,
            handle_parsing_errors=True,
            agent_type=AgentType.OPENAI_FUNCTIONS,
            top_k=5,
            prompt=voice_rag_prompt()
        )

    # -------------------------
    # Main processing pipeline
    # -------------------------
    async def process_audio(self, ws: WebSocket, audio_bytes: bytes, session_id: str):
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "input.wav"

        # STT
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

        # Exit conditions
        if any(kw in user_text.lower() for kw in ["bye", "goodbye", "exit", "stop", "thanks", "thank you"]):
            await self.safe_send(ws, "Goodbye! Have a great day!")
            return "exit"

        # Query the SQL agent
        bot_text = await self.ask_agent(session_id, user_text)

        # Respond with TTS
        await self.safe_send(ws, bot_text)
        return None

    # -------------------------
    # Query the SQL agent
    # -------------------------
    async def ask_agent(self, session_id: str, user_text: str) -> str:
        try:
            memory = self.memory_manager.get_memory(session_id)
            memory.chat_memory.add_user_message(user_text)

            # Run agent on the user query
            result = self.voice_agent.invoke({"input": user_text})
            bot_text = result.get("output", "") if isinstance(result, dict) else str(result)

            # Clean echoed user query and extra info
            bot_text = re.sub(r"(User:|Bot:|created on|\d{4}-\d{2}-\d{2})", "", bot_text, flags=re.I).strip()
            bot_text = bot_text.replace(user_text, "").strip()

            if not bot_text:
                bot_text = "I’m sorry, I could not find the requested information."

            memory.chat_memory.add_ai_message(bot_text)
            return bot_text

        except Exception as e:
            print(f"❌ Agent error: {e}")
            return "I’m sorry, I could not find the requested information."

    # -------------------------
    # Text-to-speech + Send
    # -------------------------
    async def safe_send(self, ws: WebSocket, text: str):
        try:
            tts = self.client.audio.speech.create(model="gpt-4o-mini-tts", voice="alloy", input=text)
            audio_stream = io.BytesIO(tts.read())
            audio_b64 = base64.b64encode(audio_stream.getvalue()).decode()
            if ws.client_state.name == "CONNECTED":
                await ws.send_json({"bot_text": text, "audio": audio_b64})
            else:
                print("⚠️ Tried to send after disconnect")
        except Exception as e:
            print(f"TTS Error: {e}")
            if ws.client_state.name == "CONNECTED":
                await ws.send_json({"bot_text": "I couldn’t speak the response.", "audio": ""})
