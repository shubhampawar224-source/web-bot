from Archive.utils.scraper import scrape_website
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
from typing import Optional, List
import os
import uuid
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import WEBSITE_URL
from cache_manager import load_website_text
from llm_tools import get_answer

import chromadb
from sentence_transformers import SentenceTransformer

# ---------------- Disable HuggingFace Tokenizer Warning ----------------
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# ---------------- FastAPI setup ----------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------------- ChromaDB setup ----------------
PERSIST_DIR = "rag_db"
os.makedirs(PERSIST_DIR, exist_ok=True)
chroma_client = chromadb.PersistentClient(path=PERSIST_DIR)

COLLECTION_NAME = "knowledge_base"
if COLLECTION_NAME in [c.name for c in chroma_client.list_collections()]:
    collection = chroma_client.get_collection(COLLECTION_NAME)
    print("Loaded existing vector collection from disk.")
else:
    collection = chroma_client.create_collection(name=COLLECTION_NAME)
    print("Created new vector collection.")

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# ---------------- Website Ingestion ----------------
def chunk_text(text, chunk_size=500, overlap=50):
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks

WEBSITE_TEXT = load_website_text(WEBSITE_URL)
print("Website content length:", len(WEBSITE_TEXT))

if collection.count() == 0:
    chunks = chunk_text(WEBSITE_TEXT)
    for i, chunk in enumerate(chunks):
        embedding = embedding_model.encode(chunk).tolist()
        collection.add(
            ids=[f"doc_chunk_{i}"],
            embeddings=[embedding],
            documents=[chunk],
            metadatas=[{"type": "website"}]
        )
    print(f"Inserted {len(chunks)} chunks into vector store.")
else:
    print(f"Collection already has {collection.count()} documents.")

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
@app.get("/")
async def root():
    return FileResponse("static/index.html")

@app.post("/chat")
async def chat_endpoint(data: dict):
    try:
        session_id = data.get("session_id") or str(uuid.uuid4())
        query = data.get("query")

        if not query:
            return JSONResponse({"error": "Query is required"}, status_code=400)

        # ---------------- Store user query ----------------
        query_embedding = embedding_model.encode(query).tolist()
        collection.add(
            ids=[f"user_{session_id}_{uuid.uuid4()}"],
            embeddings=[query_embedding],
            documents=[query],
            metadatas={"type": "chat", "role": "user", "session_id": session_id}
        )

        # ---------------- Retrieve relevant website chunks ----------------
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5,
            where={"type": "website"}  # only website content
        )

        # Flatten and deduplicate documents + metadata
        raw_docs = results["documents"][0] if results["documents"] else []
        raw_metas = results["metadatas"][0] if results["metadatas"] else []

        seen = set()
        retrieved_docs, retrieved_metas = [], []
        for doc, meta in zip(raw_docs, raw_metas):
            if doc not in seen:
                seen.add(doc)
                retrieved_docs.append(doc)
                retrieved_metas.append(meta)

        # ---------------- Generate answer ----------------
        retrieved_context_text = " ".join(retrieved_docs)
        answer = get_answer(retrieved_context_text, query)

        # ---------------- Store assistant answer ----------------
        answer_embedding = embedding_model.encode(answer).tolist()
        collection.add(
            ids=[f"assistant_{session_id}_{uuid.uuid4()}"],
            embeddings=[answer_embedding],
            documents=[answer],
            metadatas={"type": "chat", "role": "assistant", "session_id": session_id}
        )

        # ---------------- Return only what the user should see ----------------
        return {
            "answer": answer,
            "session_id": session_id,
            "history": get_session_history(session_id)  # optional; remove if you don't want to show history
        }

    except Exception as e:
        print(f"[Error] Chat endpoint failed: {e}")
        return JSONResponse({"error": "Something went wrong."}, status_code=500)

@app.get("/history/{session_id}")
async def get_history(session_id: str):
    """Fetch full chat history from vector DB"""
    return {"session_id": session_id, "history": get_session_history(session_id)}



# Request body schema
class URLPayload(BaseModel):
    url: HttpUrl
    tags: Optional[List[str]] = None
    session_id: Optional[str] = None  # optional if you want session-based storage

# Dummy storage (replace with DB/vector DB call)
url_store = []

@app.post("/inject-url")
async def inject_url(payload: URLPayload):
    """
    Inject a web URL + optional tags into DB / vector DB
    """
    try:
        entry = {
            "url": str(payload.url),
            "session_id": payload.session_id
        }

        # 🔹 Here you can push into DB or vector DB
        url_store.append(entry)
        check = scrape_website(str(payload.url))  # Call scraper to fetch and store content
        return {"status": "success", "data": entry}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 