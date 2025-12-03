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
        self.db = SQLDatabase.from_uri(
            db_uri,
            sample_rows_in_table_info=3,  # Show more examples including JSON data
            max_string_length=2000  # Allow longer strings to show full JSON structures
        )
        self.llm = ChatOpenAI(
            model="gpt-4o-mini", 
            temperature=0,
            request_timeout=15,  # 15 second timeout for LLM calls
            max_retries=1  # Reduce retries for faster failure
        )

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

        # --- SQL Agent with optimization ---
        self.voice_agent = create_sql_agent(
            llm=self.llm,
            toolkit=self.toolkit,
            verbose=True,  # Enable verbose to see what agent is doing
            handle_parsing_errors=True,
            agent_type=AgentType.OPENAI_FUNCTIONS,
            prompt=self.prompt,
            max_iterations=8,  # Increase for deeper search
            max_execution_time=20,  # Increase timeout for thorough search
            early_stopping_method="generate"  # Stop early if answer found
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
            # Check if WebSocket is still connected before sending timeout message
            if ws.client_state.name == "CONNECTED":
                try:
                    await ws.send_json({"bot_text": "No input detected. Ending the session.", "audio": ""})
                    await ws.close()
                except Exception as e:
                    print(f"Error sending timeout message: {e}")
                    # Try to close anyway
                    try:
                        await ws.close()
                    except:
                        pass
        except asyncio.CancelledError:
            pass

    # -------------------------
    # Audio -> Text -> Agent
    # -------------------------
    async def process_audio(self, ws: WebSocket, audio_bytes: bytes, session_id: str):
        # Check if WebSocket is still connected
        if ws.client_state.name != "CONNECTED":
            print("WebSocket disconnected during audio processing")
            return None
            
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
            enhanced_input = f"Voice query (provide detailed answer): {user_text}"
            
            # Run agent with timeout
            start_time = time.time()
            result = await asyncio.wait_for(
                asyncio.to_thread(self.voice_agent.invoke, {"input": enhanced_input}),
                timeout=30.0  # 30 second total timeout for thorough search
            )
            elapsed = time.time() - start_time
            print(f"⏱️ Agent response time: {elapsed:.2f}s")
            
            bot_text = result.get("output", "") if isinstance(result, dict) else str(result)

            # Clean up the response for voice output
            bot_text = self.clean_response(bot_text, user_text)
            
            # Check for agent timeout/iteration limit and ask user to repeat
            if "agent stopped due to iteration limit" in bot_text.lower() or "agent stopped due to time limit" in bot_text.lower():
                bot_text = "That's a great question, but I need a bit more time to search thoroughly. Would you mind asking that again? I promise to find you the best answer I can."
            
            if not bot_text or len(bot_text.strip()) < 5:
                bot_text = "I wasn't able to find specific information about that. Could you try asking your question in a different way, or perhaps ask about something else I can help you with?"

            memory.chat_memory.add_ai_message(bot_text)
            return bot_text

        except asyncio.TimeoutError:
            print(f"⏰ Agent timeout after 20 seconds")
            return "I apologize, but I'm taking a bit longer than usual to find that information. Could you please try asking your question again, maybe in a slightly different way? I'll do my best to help you."
        except Exception as e:
            print(f"❌ Agent error: {e}")
            return "I apologize, but I'm having a little trouble finding that information right now. Would you mind rephrasing your question or asking something else? I'm here to help."
    
    def clean_response(self, text: str, user_text: str) -> str:
        """Basic cleanup for voice output - main filtering done by prompt"""
        if not text:
            return ""
            
        # Remove any remaining user query echo
        text = text.replace(user_text, "").strip()
        
        # Basic cleanup only
        text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single space
        text = text.strip()
        
        # Ensure response ends properly
        if text and not text.endswith(('?', '.', '!', ':')):
            text += "."
            
        return text

    # -------------------------
    # Text-to-speech + Send
    # -------------------------
    async def safe_send(self, ws: WebSocket, text: str):
        try:
            # Check if WebSocket is still open
            if ws.client_state.name != "CONNECTED":
                print(f"WebSocket not connected, state: {ws.client_state.name}")
                return
                
            tts = self.client.audio.speech.create(
                model="tts-1", voice="alloy", input=text
            )
            audio_stream = io.BytesIO(tts.read())
            audio_b64 = base64.b64encode(audio_stream.getvalue()).decode()

            # Double-check before sending
            if ws.client_state.name == "CONNECTED":
                await ws.send_json({"bot_text": text, "audio": audio_b64})
            else:
                print("WebSocket closed before sending audio response")
                
        except Exception as e:
            print(f"TTS/Send Error: {e}")
            # Only try to send error message if WebSocket is still connected
            try:
                if ws.client_state.name == "CONNECTED":
                    await ws.send_json({"bot_text": "I couldn't speak the response.", "audio": ""})
            except Exception as send_error:
                print(f"Failed to send error message: {send_error}")
