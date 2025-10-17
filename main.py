import io
import base64
import time
from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from dotenv import load_dotenv
import os
from sqlalchemy.orm import Session
from database.db import SessionLocal
from utils.data_convert import embed_text, build_or_load_faiss

# ----------------- Load env & initialize OpenAI -----------------
load_dotenv(override=True)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ----------------- FastAPI setup -----------------
app = FastAPI()
app.mount("/static", "static", name="static")

@app.get("/voice")
async def get_index():
    return FileResponse("static/voice.html")

# ----------------- Load FAISS -----------------
faiss_index, faiss_texts, faiss_metadata = build_or_load_faiss()

# ----------------- Utilities -----------------
MAX_CHARS = 3500

def truncate_text(text: str, max_chars: int = MAX_CHARS) -> str:
    return text[:max_chars] + " …" if len(text) > max_chars else text

def retrieve_faiss_response(query: str, k: int = 1):
    query_emb = embed_text(query)
    D, I = faiss_index.search(query_emb, k)
    results = []
    for idx in I[0]:
        results.append({
            "text": faiss_texts[idx],
            "metadata": faiss_metadata[idx]
        })
    if results:
        results[0]["text"] = truncate_text(results[0]["text"])
        return results[0]
    return {"text": "No relevant data found.", "metadata": {}}

def refine_text_with_gpt(user_text: str, faiss_text: str) -> str:
    """Refine the FAISS + STT response using GPT for contextual accuracy"""
    prompt = (
        f"You are a helpful assistant. The user said:\n{user_text}\n\n"
        f"FAISS retrieved this context:\n{faiss_text}\n\n"
        "Return a clear, natural response based on both."
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an intelligent assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3
    )
    return response.choices[0].message.content

# ----------------- WebSocket voice assistant -----------------
@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await ws.accept()
    session_db: Session = SessionLocal()
    paused = False  # Pause control flag

    try:
        # Greeting message
        welcome_text = "Hello! I am your AI Agent. Start speaking and I will reply."
        tts_resp = client.audio.speech.create(
            model="gpt-4o-mini-tts", voice="alloy", input=welcome_text
        )
        audio_data = io.BytesIO(tts_resp.read())
        audio_b64 = base64.b64encode(audio_data.getvalue()).decode()
        await ws.send_json({"bot_text": welcome_text, "audio": audio_b64})

        while True:
            data = await ws.receive_json()

            # 🟡 Handle pause/resume commands
            if data.get("command") == "pause":
                paused = True
                await ws.send_json({"status": "paused"})
                continue
            elif data.get("command") == "resume":
                paused = False
                await ws.send_json({"status": "resumed"})
                continue

            if paused:
                await ws.send_json({"status": "paused_ignored"})
                continue

            # 🟢 Handle voice input
            audio_b64_input = data.get("audio")
            if not audio_b64_input:
                await ws.send_json({"error": "Empty input not allowed"})
                continue

            # 1️⃣ Speech-to-Text
            audio_bytes = base64.b64decode(audio_b64_input)
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "input.wav"

            stt_resp = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
            user_text = stt_resp.text.strip()

            if not user_text:
                await ws.send_json({"error": "No speech detected"})
                continue

            print(f"[User]: {user_text}")

            # 2️⃣ FAISS retrieval
            faiss_resp = retrieve_faiss_response(user_text)
            faiss_text = faiss_resp["text"]

            # 3️⃣ GPT refinement
            final_reply = refine_text_with_gpt(user_text, faiss_text)
            print(f"[Bot]: {final_reply}")

            # 4️⃣ TTS
            tts_resp = client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="alloy",
                input=final_reply
            )
            audio_data = io.BytesIO(tts_resp.read())
            audio_b64_out = base64.b64encode(audio_data.getvalue()).decode()

            # 5️⃣ Send back to client
            await ws.send_json({
                "user_text": user_text,
                "bot_text": final_reply,
                "metadata": faiss_resp["metadata"],
                "audio": audio_b64_out
            })

            time.sleep(5)

    except Exception as e:
        print(f"WebSocket error: {e}")
        await ws.send_json({"error": str(e)})
    finally:
        session_db.close()
