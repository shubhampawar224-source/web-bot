import io
import base64
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from openai import OpenAI

from langchain_community.utilities import SQLDatabase
from langchain.chat_models import ChatOpenAI
from langchain.agents import create_sql_agent
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.agents.agent_types import AgentType
from langchain_core.pydantic_v1 import BaseModel, Field

# -------------------------------
# ENVIRONMENT
# -------------------------------
load_dotenv(override=True)
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    raise RuntimeError("Please set OPENAI_API_KEY in .env")

client = OpenAI(api_key=OPENAI_KEY)

# -------------------------------
# FASTAPI APP
# -------------------------------
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/voice")
async def get_index():
    return FileResponse("static/voice.html")

# -------------------------------
# DATABASE CONNECTION
# -------------------------------
db = SQLDatabase.from_uri("sqlite:///scraped_data.db")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# SQL toolkit + agent
toolkit = SQLDatabaseToolkit(db=db, llm=llm)
agent_executor = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    handle_parsing_errors=True
)

# -------------------------------
# QUERY CLASSIFIER
# -------------------------------
class QueryType(BaseModel):
    is_database_query: bool = Field(..., description="Always True: All queries go through DB")
    response: str = Field(..., description="Fallback if DB returns nothing")

# Custom prompt forcing all queries to use DB
query_classifier_prompt = """You are a voice assistant.
All queries MUST be answered using the database only.
Return ONLY JSON: {{ "is_database_query": true, "response": "<fallback text>" }}"""

# Wrap LLM with structured output
query_classifier_chain = llm.with_structured_output(QueryType, prompt=query_classifier_prompt)

# -------------------------------
# WEBSOCKET VOICE HANDLER
# -------------------------------
# -------------------------------
# WEBSOCKET VOICE HANDLER
# -------------------------------
@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await ws.accept()
    print("🎧 Voice session started")

    try:
        # Greeting
        welcome = "Hello! I’m your AI voice assistant. How can I help you today?"
        tts = client.audio.speech.create(model="tts-1", voice="alloy", input=welcome)
        await ws.send_json({
            "bot_text": welcome,
            "audio": base64.b64encode(io.BytesIO(tts.read()).getvalue()).decode()
        })

        while True:
            data = await ws.receive_json()

            # Ignore silence or missing audio
            if data.get("silence") or not data.get("audio"):
                continue

            audio_bytes = base64.b64decode(data["audio"])
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "input.wav"

            # ---- Speech-to-Text ----
            try:
                stt_response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
                user_text = stt_response.text.strip()
                if not user_text:
                    continue
            except Exception as e:
                print(f"🎙️ STT Error: {e}")
                reply = "Sorry, I couldn't hear that clearly. Please try again."
                tts = client.audio.speech.create(model="tts-1", voice="alloy", input=reply)
                await ws.send_json({
                    "bot_text": reply,
                    "audio": base64.b64encode(io.BytesIO(tts.read()).getvalue()).decode()
                })
                continue

            print(f"🧠 User said: {user_text}")

            # ---- Exit check ----
            if any(kw in user_text.lower() for kw in ["nothing else", "goodbye", "bye", "exit", "stop"]):
                closing = "Goodbye! Have a great day!"
                tts = client.audio.speech.create(model="tts-1", voice="alloy", input=closing)
                await ws.send_json({
                    "bot_text": closing,
                    "audio": base64.b64encode(io.BytesIO(tts.read()).getvalue()).decode()
                })
                break

            # ---- SQL Agent safely ----
            try:
                # Force all queries to DB
                classification = {"is_database_query": True, "response": "I couldn't find matching data."}

                if classification["is_database_query"]:
                    print("📊 Running SQL agent...")
                    try:
                        result = agent_executor.invoke({"input": user_text})
                        # result might be dict or string
                        if isinstance(result, dict):
                            bot_text = result.get("output", "I couldn't find matching data in the database.")
                        else:
                            bot_text = str(result) or "I couldn't find matching data in the database."
                    except Exception as e:
                        print(f"❌ SQL agent error: {e}")
                        bot_text = "I couldn't find matching data in the database."
                else:
                    bot_text = classification["response"]

                # Ensure TTS input is never empty
                if not bot_text.strip():
                    bot_text = "Sorry, I could not understand the query."

            except Exception as e:
                print(f"❌ Processing Error: {e}")
                bot_text = "Something went wrong while processing your request."

            # ---- Text-to-Speech ----
            try:
                tts = client.audio.speech.create(model="tts-1", voice="alloy", input=bot_text)
                await ws.send_json({
                    "bot_text": bot_text,
                    "audio": base64.b64encode(io.BytesIO(tts.read()).getvalue()).decode()
                })
            except Exception as e:
                print(f"🎤 TTS Error: {e}")
                await ws.send_json({
                    "bot_text": "Sorry, I couldn't speak the response.",
                    "audio": ""
                })

    except WebSocketDisconnect:
        print("⚠️ Client disconnected.")
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
    finally:
        await ws.close()
        print("🔒 Connection closed.")


# -------- raw code with agent prompt----------------


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
from langchain.memory import ConversationBufferMemory
from langchain.agents import create_sql_agent, AgentType, create_react_agent
from langchain.prompts import PromptTemplate
# ========================================
# ENVIRONMENT
# ========================================
load_dotenv(override=True)
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
db_uri = "sqlite:///scraped_data.db"  # Adjust if needed

if not OPENAI_KEY:
    raise RuntimeError("Please set OPENAI_API_KEY in .env")


# ========================================
# MEMORY MANAGER
# ========================================
class MemoryManager:
    """Manages session-based memory with expiration."""
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


# ========================================
# VOICE ASSISTANT CLASS
# ========================================
class VoiceAssistant:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_KEY)
        self.memory_manager = MemoryManager()

        # Database + agent
        self.db = SQLDatabase.from_uri(db_uri)
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.toolkit = SQLDatabaseToolkit(db=self.db, llm=self.llm)

        # Custom prompt for the SQL agent
        self.custom_prompt = PromptTemplate(
                    input_variables=["input", "tools", "tool_names", "agent_scratchpad"],
                    template="""
                You are a smart SQL assistant.
                You can answer questions by writing and executing SQL queries on the given database.
                Do not mention table names, IDs, or timestamps in your answer.

                Available tools: {tools}
                [{tool_names}]

                Question: {input}

                {agent_scratchpad}

                Answer:
                """
                )
        # Pass prompt correctly to the agent
        self.voice_agent = create_sql_agent(
            llm=self.llm,
            toolkit=self.toolkit,
            verbose=False,
            handle_parsing_errors=True,
            agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            top_k=5,
            # prompt=self.custom_prompt  # pass the prompt here
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
            bot_text = re.sub(r"(User:|Bot:|created on|\d{4}-\d{2}-\d{2})", "", bot_text, flags=re.I).strip()
            bot_text = bot_text.replace(user_text, "").strip()  # remove echoed query

            if not bot_text:
                bot_text = "Sorry, I couldn't find that information."

            memory.chat_memory.add_ai_message(bot_text)
            return bot_text

        except Exception as e:
            print(f"❌ Agent error: {e}")
            return "Sorry, I encountered an issue while processing your request."

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
                await ws.send_json({"bot_text": "Sorry, I couldn’t speak the response.", "audio": ""})

                