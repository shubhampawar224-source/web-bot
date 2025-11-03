import torch
import numpy as np
import faiss
from transformers import AutoTokenizer, AutoModel, Wav2Vec2Model, Wav2Vec2Processor
from sqlalchemy.orm import Session
from model.models import Website
from database.db import SessionLocal


import os
import pickle

# ---------------- VECTOR STORE PATH ----------------
VECTOR_STORE_DIR = "./vector_store"
os.makedirs(VECTOR_STORE_DIR, exist_ok=True)
FAISS_INDEX_PATH = os.path.join(VECTOR_STORE_DIR, "faiss_index.bin")
FAISS_META_PATH = os.path.join(VECTOR_STORE_DIR, "faiss_metadata.pkl")

# ---------------- TEXT EMBEDDING MODEL ----------------
# Lazy loading for models to speed up startup
tokenizer = None
text_model = None

def get_models():
    """Lazy load models only when first needed"""
    global tokenizer, text_model
    if tokenizer is None or text_model is None:
        print("Loading SentenceTransformer models...")
        tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
        text_model = AutoModel.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
        print("Models loaded successfully!")
    return tokenizer, text_model

def embed_text(text: str):
    tokenizer, text_model = get_models()
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True)
    with torch.no_grad():
        embeddings = text_model(**inputs, output_hidden_states=True, return_dict=True).last_hidden_state
    return embeddings.mean(dim=1).numpy()

def build_or_load_faiss():
    if os.path.exists(FAISS_INDEX_PATH) and os.path.exists(FAISS_META_PATH):
        print("Loading FAISS index from disk...")
        index = faiss.read_index(FAISS_INDEX_PATH)
        with open(FAISS_META_PATH, "rb") as f:
            texts, metadata = pickle.load(f)
        return index, texts, metadata

    # Build FAISS from DB
    db: Session = SessionLocal()
    websites = db.query(Website).all()
    texts, metadata = [], []

    for w in websites:
        scraped = w.scraped_data or {}
        about_text = scraped.get("about", {}).get("description", "") if isinstance(scraped.get("about"), dict) else ""
        links_list = scraped.get("links", [])
        links_text = " ".join([l["url"] if isinstance(l, dict) and "url" in l else str(l) for l in links_list])
        full_text = f"{w.firm.name}: {about_text} {links_text}".strip()
        if full_text:
            texts.append(full_text)
            metadata.append({"website_id": w.id, "domain": w.domain, "firm_id": w.firm_id})

    # Check if we have texts to create embeddings from
    if not texts:
        print("No website data found. Creating empty FAISS index...")
        # Create a dummy embedding to get the dimension
        dummy_embedding = embed_text("dummy text for dimension")
        index = faiss.IndexFlatL2(dummy_embedding.shape[0])
        
        # Save empty index and metadata
        faiss.write_index(index, FAISS_INDEX_PATH)
        with open(FAISS_META_PATH, "wb") as f:
            pickle.dump(([], []), f)
        
        print("Empty FAISS index created")
        return index, [], []
    
    embeddings = np.vstack([embed_text(t) for t in texts])
    index = faiss.IndexFlatL2(embeddings.shape[1])
    index.add(embeddings)

    faiss.write_index(index, FAISS_INDEX_PATH)
    with open(FAISS_META_PATH, "wb") as f:
        pickle.dump((texts, metadata), f)

    print(f"FAISS index built and saved with {len(texts)} entries")
    return index, texts, metadata
