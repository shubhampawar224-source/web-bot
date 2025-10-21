# backend.py
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

toolkit = SQLDatabaseToolkit(db=db, llm=llm)
agent_executor = create_sql_agent(
    llm=llm,
    toolkit=toolkit,
    verbose=True,
    agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    handle_parsing_errors=True
)

# -------------------------------
# CONVERSATION MEMORY
# -------------------------------
conversation_history = []

# -------------------------------
# TOOL FUNCTION
# -------------------------------
def query_db(user_text: str) -> str:
    """Query SQL agent with conversation memory."""
    try:
        full_input = "\n".join(conversation_history + [user_text])
        result = agent_executor.invoke({"input": full_input})

        if isinstance(result, dict):
            bot_text = result.get("output", "No matching data found.")
        else:
            bot_text = str(result) or "No matching data found."

        # Update conversation memory
        conversation_history.append(f"You: {user_text}")
        conversation_history.append(f"Bot: {bot_text}")
        return bot_text
    except Exception as e:
        print(f"DB query error: {e}")
        return "Sorry, I couldn't find matching data in the database."

# -------------------------------
# WEBSOCKET VOICE HANDLER
# -------------------------------
@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await ws.accept()
    print("🎧 Voice session started")

    async def process_audio(audio_bytes: bytes):
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "input.wav"

        # ---- Speech-to-Text ----
        try:
            stt_resp = client.audio.transcriptions.create(
                model="whisper-1", file=audio_file
            )
            user_text = stt_resp.text.strip()
            if not user_text:
                return
        except Exception as e:
            print(f"STT Error: {e}")
            reply = "Sorry, I couldn't hear that clearly."
            tts = client.audio.speech.create(model="tts-1", voice="alloy", input=reply)
            await ws.send_json({
                "bot_text": reply,
                "audio": base64.b64encode(io.BytesIO(tts.read()).getvalue()).decode()
            })
            return

        print(f"🧠 User said: {user_text}")

        # ---- Exit check ----
        if any(kw in user_text.lower() for kw in ["goodbye","thanks","thank you", "bye", "exit", "stop"]):
            closing = "Goodbye! Have a great day!"
            tts = client.audio.speech.create(model="tts-1", voice="alloy", input=closing)
            await ws.send_json({
                "bot_text": closing,
                "audio": base64.b64encode(io.BytesIO(tts.read()).getvalue()).decode()
            })
            await ws.close()
            return "exit"

        # ---- Query DB ----
        bot_text = query_db(user_text)
        if not bot_text.strip():
            bot_text = "Sorry, I could not find an answer in the database."

        # ---- Text-to-Speech ----
        try:
            tts = client.audio.speech.create(model="tts-1", voice="alloy", input=bot_text)
            await ws.send_json({
                "bot_text": bot_text,
                "audio": base64.b64encode(io.BytesIO(tts.read()).getvalue()).decode()
            })
        except Exception as e:
            print(f"TTS Error: {e}")
            await ws.send_json({
                "bot_text": "Sorry, I couldn't speak the response.",
                "audio": ""
            })

    try:
        # Initial greeting
        welcome = "Hello! I’m your AI voice assistant. How can I help you today?"
        tts = client.audio.speech.create(model="tts-1", voice="alloy", input=welcome)
        await ws.send_json({
            "bot_text": welcome,
            "audio": base64.b64encode(io.BytesIO(tts.read()).getvalue()).decode()
        })

        # ---- WebSocket loop ----
        while True:
            data = await ws.receive_json()
            if data.get("silence") or not data.get("audio"):
                continue
            audio_bytes = base64.b64decode(data["audio"])
            exit_signal = await process_audio(audio_bytes)
            if exit_signal == "exit":
                break

    except WebSocketDisconnect:
        print("⚠️ Client disconnected.")
    except Exception as e:
        print(f"💥 Unexpected error: {e}")
    finally:
        await ws.close()
        print("🔒 Connection closed.")
