# utils/vector_store.py

import os
import chromadb
from sentence_transformers import SentenceTransformer

# ---------------- ChromaDB Setup ----------------
PERSIST_DIR = "rag_db"
os.makedirs(PERSIST_DIR, exist_ok=True)

# Persistent Chroma client
chroma_client = chromadb.PersistentClient(path=PERSIST_DIR)

# Define global collection
COLLECTION_NAME = "knowledge_base"

if COLLECTION_NAME in [c.name for c in chroma_client.list_collections()]:
    collection = chroma_client.get_collection(COLLECTION_NAME)
    print(f"[VectorStore] Loaded existing collection '{COLLECTION_NAME}'")
else:
    collection = chroma_client.create_collection(name=COLLECTION_NAME)
    print(f"[VectorStore] Created new collection '{COLLECTION_NAME}'")

# ---------------- Embedding Model ----------------
# embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# ---------------- Helper: Chunk Text ----------------
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50):
    """
    Splits long text into overlapping chunks for vector embedding.
    """
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks

# ---------------- Helper: Add Document ----------------
def add_text_chunks_to_collection(chunks, metadata: dict):
    """
    Takes text chunks and metadata → stores in ChromaDB.
    """
    for i, chunk in enumerate(chunks):
        emb = embedding_model.encode(chunk).tolist()
        collection.add(
            ids=[f"{metadata.get('url', 'unknown')}_chunk_{i}"],
            embeddings=[emb],
            documents=[chunk],
            metadatas=[metadata]
        )

    print(f"[VectorStore] Added {len(chunks)} chunks for {metadata.get('url')}")


# ---------------- Helper: Query Similar Texts ----------------
# def query_similar_texts(query: str, n_results: int = 10):
#     """
#     Given a query → retrieves most relevant chunks.
#     """
#     query_embedding = embedding_model.encode(query).tolist()
#     results = collection.query(
#         query_embeddings=[query_embedding],
#         n_results=n_results,
#         where={"type": "website"}
#     )

#     return results

# ---------------- Helper: Query Similar Texts ----------------
def query_similar_texts(query: str, n_results: int = 10, doc_type: str = "website"):
    """
    Given a query (any language) → retrieves most relevant chunks from ChromaDB.
    Works with multi-lingual queries using SentenceTransformer embeddings.
    
    Args:
        query (str): User query in any language
        n_results (int): Number of top results to return
        doc_type (str): Filter metadata type (default: 'website')
    
    Returns:
        List of documents (chunks) with metadata
    """
    # Step 1: Encode the query
    query_embedding = embedding_model.encode(query).tolist()

    # Step 2: Query ChromaDB
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where={"type": doc_type}  # filter by document type
    )

    # Step 3: Extract documents & metadata
    retrieved_chunks = []
    if results and "documents" in results and results["documents"]:
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            retrieved_chunks.append({"text": doc, "metadata": meta})

    return retrieved_chunks
