import base64
import io
import os
import re
import time
import uuid
from dotenv import load_dotenv
from flask import render_template_string, Flask, request
import loges
from utils.voice_bot_helper import refine_text_with_gpt, retrieve_faiss_response
from utils.query_senetizer import is_safe_query
from database.db import init_db
from utils.scraper import build_about
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, HttpUrl
from fastapi import FastAPI, WebSocket
from typing import Optional, List
from sqlalchemy.orm import Session
from database.db import SessionLocal
from model.models import Contact, Website, Firm
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from model.validation_schema import ChatRequest, ContactIn, SecurityHeadersMiddleware, URLPayload
from utils.voice_bot_helper import client
from voice_config.voice_helper import *
from utils.email_send import ContactManager


# from cache_manager import load_website_text
from utils.llm_tools import get_answer_from_db
from utils.vector_store import (
    collection,
    embedding_model,
    chunk_text,
    add_text_chunks_to_collection,
    query_similar_texts
)

load_dotenv()
ALLOWED_IFRAME_ORIGINS = os.getenv("ALLOWED_IFRAME_ORIGINS", "")  # space-separated list e.g. "https://siteA.com https://siteB.com"


# ---------------- Disable HuggingFace Tokenizer Warning ----------------
os.environ["TOKENIZERS_PARALLELISM"] = "false"
loges.log_check(message="INFO")
# ---------------- FastAPI setup ----------------
app = FastAPI()
contact_mgr = ContactManager()

# After CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.middleware("http")
async def allow_iframe(request, call_next):
    response = await call_next(request)

    # Allow embedding anywhere
    response.headers["Content-Security-Policy"] = "frame-ancestors *;"
    
    # Old browser fallback
    response.headers["X-Frame-Options"] = "ALLOWALL"
    
    # Allow widget JS to fetch API
    response.headers["Access-Control-Allow-Origin"] = "*"

    return response


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

        # Get firm-specific answer from vector DB
        answer = get_answer_from_db(query=query, session_id=session_id, firm_id=firm.id)
        if not answer:
            answer= {"action": "SHOW_CONTACT_FORM",
                       "message": "Before we finish, we would like to collect your contact details so our team can assist further."
}
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

@app.post("/save-contact")
async def save_contact(payload: ContactIn, background_tasks: BackgroundTasks):
    try:
        # prefer explicit notify_to, otherwise send to the contact's email
        notify_to = payload.notify_to or payload.email
        contact_id = contact_mgr.save_and_notify(
            payload.model_dump(),
            background_tasks=background_tasks,
            notify_to=notify_to
        )
        return {"status": "ok", "id": contact_id}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

@app.get("/history/{session_id}")
async def get_history(session_id: str):
    """Fetch full chat history from vector DB"""
    return {"session_id": session_id, "history": get_session_history(session_id)}

@app.get("/widget")
async def get_widget():
    return FileResponse("static/widgets.html")
  
# ----------------- WebSocket voice assistant ----------------

@app.get("/chat_widget", response_class=HTMLResponse)
def chat_ui():
    with open("static/index.html") as f:
        return f.read()

@app.get("/config")
def get_config():
    return {
        "baseUrl": os.getenv("WIDGET_BASE_URL")  # only public value
    }

@app.middleware("http")
async def frame_headers_middleware(request: Request, call_next):
    resp = await call_next(request)

    # remove restrictive headers if present (MutableHeaders: delete instead of pop)
    for hdr in ("Content-Security-Policy", "X-Frame-Options", "Permissions-Policy"):
        if hdr in resp.headers:
            try:
                del resp.headers[hdr]
            except Exception:
                pass

    if ALLOWED_IFRAME_ORIGINS:
        origins = ALLOWED_IFRAME_ORIGINS.split()
        allowed = " ".join(origins)
        resp.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {allowed};"
        # do NOT re-add Permissions-Policy that blocks unload; only add explicit safe feature policies if you understand them
    else:
        resp.headers["Content-Security-Policy"] = "frame-ancestors *;"

    return resp

