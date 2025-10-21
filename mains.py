
import base64
import io
import os
import re
import time
import uuid
from dotenv import load_dotenv
import loges
from utils.voice_bot_helper import refine_text_with_gpt, retrieve_faiss_response
from utils.query_senetizer import is_safe_query
from database.db import init_db
from utils.scraper import build_about
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from fastapi import FastAPI, WebSocket
from typing import Optional, List
from sqlalchemy.orm import Session
from database.db import SessionLocal
from model.models import Website, Firm
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from model.validation_schema import ChatRequest, SecurityHeadersMiddleware, URLPayload
from utils.voice_bot_helper import client



# from cache_manager import load_website_text
from utils.llm_tools import get_answer_from_db
from utils.vector_store import (
    collection,
    embedding_model,
    chunk_text,
    add_text_chunks_to_collection,
    query_similar_texts
)


# ---------------- Disable HuggingFace Tokenizer Warning ----------------
os.environ["TOKENIZERS_PARALLELISM"] = "false"
loges.log_check(message="INFO")
# ---------------- FastAPI setup ----------------
app = FastAPI()
# After CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Add CSP + Security middleware
app.add_middleware(SecurityHeadersMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")
init_db()
load_dotenv(override=True)

# ---------------- Helper ----------------
def get_session_history(session_id: str):
    results = collection.get(
        where={"session_id": session_id},
        include=["documents", "metadatas"]
    )
    history = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        if meta.get("role") in ["user", "assistant"]:
            history.append({"role": meta["role"], "content": doc})
    return history

# ---------------- Routes ----------------
# @app.get("/")
# async def root():
#     return FileResponse("static/index.html")

# ----- APIs -----
@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("static/index.html")
# @app.post("/chat")
# async def chat_endpoint(data: dict):
#     try:
#         session_id = data.get("session_id") or str(uuid.uuid4())
#         query = data.get("query")

#         if not query:
#             return JSONResponse({"error": "Query is required"}, status_code=400)

#         # ---------------- Store user query ----------------
#         query_embedding = embedding_model.encode(query).tolist()
#         collection.add(
#             ids=[f"user_{session_id}_{uuid.uuid4()}"],
#             embeddings=[query_embedding],
#             documents=[query],
#             metadatas={"type": "chat", "role": "user", "session_id": session_id}
#         )

#         # ---------------- Retrieve relevant website chunks ----------------
#         results = collection.query(
#             query_embeddings=[query_embedding],
#             n_results=5,
#             where={"type": "website"}  # only website content
#         )

#         # Flatten and deduplicate documents + metadata
#         raw_docs = results["documents"][0] if results["documents"] else []
#         raw_metas = results["metadatas"][0] if results["metadatas"] else []

#         seen = set()
#         retrieved_docs, retrieved_metas = [], []
#         for doc, meta in zip(raw_docs, raw_metas):
#             if doc not in seen:
#                 seen.add(doc)
#                 retrieved_docs.append(doc)
#                 retrieved_metas.append(meta)

#         # ---------------- Generate answer ----------------
#         retrieved_context_text = " ".join(retrieved_docs)
#         answer = get_answer(retrieved_context_text, query)

#         # ---------------- Store assistant answer ----------------
#         answer_embedding = embedding_model.encode(answer).tolist()
#         collection.add(
#             ids=[f"assistant_{session_id}_{uuid.uuid4()}"],
#             embeddings=[answer_embedding],
#             documents=[answer],
#             metadatas={"type": "chat", "role": "assistant", "session_id": session_id}
#         )

#         # ---------------- Return only what the user should see ----------------
#         return {
#             "answer": answer,
#             "session_id": session_id,
#             "history": get_session_history(session_id)  # optional; remove if you don't want to show history
#         }

#     except Exception as e:
#         print(f"[Error] Chat endpoint failed: {e}")
#         return JSONResponse({"error": "Something went wrong."}, status_code=500)


@app.post("/chat")
async def chat_endpoint(data: ChatRequest):
    session_id = data.session_id or str(uuid.uuid4())
    query = data.query
    firm_id = data.firm_id
    
    if not query or not firm_id:
        return JSONResponse({"error": "Query and firm are required"}, status_code=400)
    
    if not is_safe_query(query):
        raise HTTPException(status_code=400, detail="Not valid query detected. please ask anything else.")

    db: Session = SessionLocal()
    try:
        # Validate firm exists
        firm = db.query(Firm).filter(Firm.id == firm_id).first()
        if not firm:
            return JSONResponse({"error": "Selected firm not found"}, status_code=404)

        # Fetch all websites for this firm
        websites = db.query(Website).filter(Website.firm_id == firm.id).all()
        # Aggregate "full_text" from the 'about' field in scraped_data
        context = " ".join([
            w.scraped_data.get("about", {}).get("full_text", "")
            for w in websites if w.scraped_data
        ])

        # Get firm-specific answer from vector DB
        answer = get_answer_from_db(query=query, session_id=session_id, firm_id=firm.id)
        return {"answer": answer, "session_id": session_id}

    finally:
        db.close()

@app.get("/history/{session_id}")
async def get_history(session_id: str):
    """Fetch full chat history from vector DB"""
    return {"session_id": session_id, "history": get_session_history(session_id)}

@app.post("/inject-url")
async def inject_url(payload: URLPayload):
    db: Session = SessionLocal()
    try:
        existing_site = db.query(Website).filter(Website.base_url == str(payload.url)).first()
        if existing_site:
            firm_name = existing_site.firm.name
            return {"status": "exists", "message": f"This firm already exists: '{firm_name}'."}

        # Run scraper
        about_obj = await build_about(str(payload.url))

        full_text = about_obj.get("full_text", "").strip()
        if not full_text:
            return {"status": "empty", "message": "No text content found for embedding."}
        chunks = chunk_text(full_text)
        metadata = {
            "type": "website",
            "url": str(payload.url),
            "firm_name": about_obj.get("firm_name"),
            "session_id": payload.session_id or "global"
        }
        add_text_chunks_to_collection(chunks, metadata)

        return {
            "status": "success",
            "data": {
                "url": payload.url,
                "firm_name": about_obj.get("firm_name"),
                "firm_id": about_obj.get("firm_id"),
                "indexed_chunks": len(chunks)
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

@app.get("/firms")
async def get_all_firms():
    """
    Fetch all firms to populate a dropdown in the frontend.
    Cleans the firm name by removing 'www.' and '.com'.
    """
    db: Session = SessionLocal()
    try:
        firms = db.query(Firm).all()
        firm_list = []
        for firm in firms:
            clean_name = re.sub(r"^(www\.)|(\.com)$", "", firm.name, flags=re.IGNORECASE)
            firm_list.append({"id": firm.id, "name": clean_name})
        return {"status": "success", "firms": firm_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()
        

@app.get("/voice")
async def get_index():
    return FileResponse("static/voice.html")

# ----------------- WebSocket voice assistant -----------------
@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await ws.accept()
    session_db: Session = SessionLocal()
    paused = False  # Pause control flag

    try:
        # Greeting message
        welcome_text = "Hello! I am your AI voice assistant. Start speaking and I will reply."
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
