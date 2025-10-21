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
