import os
import logging
import asyncio
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv(override=True)

# Logger Setup
logger = logging.getLogger("LiteRAG")
logger.setLevel(logging.INFO)

class EnhancedRAGAgent:
    def __init__(self):
        self.store = None
        
        # 1. Connect to FAISS
        try:
            from utils.vector_store import FAISSVectorStore
            self.store = FAISSVectorStore()
            logger.info("✅ Successfully connected to FAISS Vector Database.")
        except Exception as e:
            logger.error(f"❌ Error loading FAISS Store: {e}")

    # =======================================================
    # 🚀 MAIN SEARCH FUNCTION (Returns Raw Context)
    # =======================================================
    async def search_and_respond(self, query: str) -> str:
        if not self.store: return "Database not connected."

        logger.info(f"🔎 Raw User Query: {query}")

        # 1. FAISS Search
        try:
            # Results fetch karo
            results = await asyncio.to_thread(self.store.search, query=query, n_results=5)
            
            # --- DEBUG LOGS ---
            print(f"\n[DEBUG] Found {len(results) if results else 0} results.")
            if results:
                print(f"[DEBUG] First Result Key Check: {list(results[0].keys())}")
            # ------------------

        except Exception as e:
            logger.error(f"FAISS Search Error: {e}")
            return "Database search failed."

        if not results:
            return "I checked the database but found nothing matching that."

        # 2. Extract Text (NO FILTERING)
        context_parts = []
        for res in results:
            # Har key try karo taaki text miss na ho
            text = (
                res.get("text") or 
                res.get("content") or 
                res.get("page_content") or 
                res.get("document") or
                res.get("metadata", {}).get("text") or 
                ""
            )
            
            # Bas check karo text exist karta hai ya nahi
            if text and str(text).strip():
                context_parts.append(str(text).strip())

        if not context_parts:
             return "Records found but empty."

        # 3. Join & Return Raw Text (No GPT Processing)
        # Duplicate hata kar join kar diya
        unique_context = list(set(context_parts))
        
        # Top 3 sabse relevant chunks ko join karke bhej do
        # Zyada bada text voice ke liye acha nahi hota
        final_answer = "\n".join(unique_context[:3]) 
        
        return final_answer