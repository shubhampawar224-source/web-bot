# utils/rag_search.py
import os
import chromadb
from sentence_transformers import SentenceTransformer

class RAGSearcher:
    """Performs vector-based semantic search over your RAG database."""
    def __init__(self, persist_dir="rag_db"):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection("knowledge_base")
        self.encoder = SentenceTransformer("all-MiniLM-L6-v2")

    def search(self, query: str, top_k: int = 3) -> str:
        try:
            query_emb = self.encoder.encode([query]).tolist()
            results = self.collection.query(query_embeddings=query_emb, n_results=top_k)

            if not results or not results["documents"][0]:
                return "No relevant information found in my knowledge."

            docs = results["documents"][0]
            return "\n".join(docs)
        except Exception as e:
            print(f"❌ RAG search error: {e}")
            return "No relevant information found in my knowledge."
