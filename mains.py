
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
from voice_config.voice_helper import *



# from cache_manager import load_website_text
from utils.llm_tools import get_answer_from_db
from utils.vector_store import (
    collection,
    embedding_model,
    chunk_text,
    add_text_chunks_to_collection,
    query_similar_texts
)

load_dotenv(override=True)


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
voice_assistant = VoiceAssistant()

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

# ----- APIs -----
@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("static/index.html")


@app.get("/voice")
async def get_index():
    return FileResponse("static/voice.html")


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


@app.get("/history/{session_id}")
async def get_history(session_id: str):
    """Fetch full chat history from vector DB"""
    return {"session_id": session_id, "history": get_session_history(session_id)}

@app.get("/widget")
async def get_widget():
    return FileResponse("static/widget.html")
  
# ----------------- WebSocket voice assistant ----------------

@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket):
    await ws.accept()
    session_id = str(ws.client.host)  # or uuid.uuid4() for uniqueness
    print(f"🎧 Voice session started: {session_id}")

    try:
        # Send greeting
        greeting = "Hello! I’m your AI voice assistant. How can I help you today?"
        await voice_assistant.safe_send(ws, greeting)

        # Listen loop
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                print("⚠️ Client disconnected during receive.")
                break

            if not data.get("audio") or data.get("silence"):
                continue

            audio_bytes = base64.b64decode(data["audio"])
            exit_signal = await voice_assistant.process_audio(ws, audio_bytes, session_id)
            if exit_signal == "exit":
                break

    except Exception as e:
        print(f"💥 WebSocket error: {e}")
    finally:
        if ws.client_state.name == "CONNECTED":
            await ws.close()
        print(f"🔒 Session {session_id} closed.")
