# utils/rag_search.py
import os
from sentence_transformers import SentenceTransformer
from utils.vector_store import query_similar_texts

class RAGSearcher:
    """Performs vector-based semantic search over your RAG database using FAISS."""
    def __init__(self, persist_dir="rag_db_faiss"):
        # FAISS vector store is initialized globally in vector_store.py
        self.encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    def search(self, query: str, top_k: int = 3) -> str:
        try:
            # Use the FAISS-based query function
            results = query_similar_texts(query, n_results=top_k, doc_type="website")

            if not results:
                return "No relevant information found in my knowledge."

            # Extract documents from results
            docs = [result["text"] for result in results]
            return "\n".join(docs)
        except Exception as e:
            print(f"❌ RAG search error: {e}")
            return "No relevant information found in my knowledge."
