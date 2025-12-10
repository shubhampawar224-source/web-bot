import os
import logging
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI

# Load Environment Variables
load_dotenv(override=True)

# Logger Setup
logger = logging.getLogger("LiteRAG")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
aclient = AsyncOpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# --- MAIN AGENT LINKED TO FAISS ---
class EnhancedRAGAgent:
    def __init__(self):
        self.store = None
        self.llm_model = os.getenv("RAG_LLM_MODEL", "gpt-4o-mini")

        # 1. Connect to Real FAISS Database
        try:
            from utils.vector_store import FAISSVectorStore
            self.store = FAISSVectorStore()
            logger.info("✅ Successfully connected to FAISS Vector Database.")
        except ImportError:
            logger.error("❌ CRITICAL: 'utils.vector_store' not found. Please check your file structure.")
        except Exception as e:
            logger.error(f"❌ Error loading FAISS Store: {e}")

    # =======================================================
    # 🚀 MAIN SEARCH FUNCTION (Async Wrapper)
    # =======================================================
    async def search_and_respond(self, query: str) -> str:
        if not query:
            return "Please ask a question."

        if not self.store:
            return "Database connection is not active."

        logger.info(f"🔎 FAISS Searching for: {query}")

        # STEP 1: Search FAISS (Run in Thread to prevent Audio Lag)
        # Hum 'asyncio.to_thread' use kar rahe hain kyunki FAISS CPU heavy hota hai
        try:
            # Note: Ensure your FAISSVectorStore.search accepts 'n_results' or change to 'k'
            results = await asyncio.to_thread(self.store.search, query=query, n_results=4)
        except Exception as e:
            logger.error(f"FAISS Search Error: {e}")
            return "I encountered an error searching the database."

        if not results:
            logger.info("⚠️ No results found in FAISS.")
            return "I checked the database, but I couldn't find specific details on that."

        # STEP 2: Context Build
        # Extract text from results (Robust handling)
        context_parts = []
        for res in results:
            # Different RAG setups use different keys ('text', 'content', 'page_content')
            text = res.get("text") or res.get("content") or res.get("page_content") or ""
            text = str(text).strip()
            if len(text) > 10:  
                context_parts.append(text)

        if not context_parts:
             return "I found some records, but they were empty."

        context = "\n---\n".join(context_parts)[:2500] # Limit context size

        # STEP 3: Generate Answer using GPT-4o-mini
        answer = await self._generate_answer(query, context)
        return answer

    # =======================================================
    # 🤖 GPT GENERATION (Context -> Human Voice)
    # =======================================================
    async def _generate_answer(self, query: str, context: str) -> str:
        if not aclient:
            return "OpenAI client is not configured."

        # Prompt Optimized for FAISS Data
        prompt = f"""
        You are a helpful voice assistant for DGF Law Firm. 
        Answer the User's question using ONLY the retrieved Context from the database.
        
        Context from FAISS:
        {context}

        User Question: {query}

        Guidelines:
        1. Answer strictly based on the Context.
        2. Keep it conversational and short (under 2 sentences).
        3. Do not say "Based on the database" or "According to the context". Just answer.
        4. If the context doesn't match the question, say you don't know.
        """

        try:
            resp = await aclient.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "system", "content": "You are a concise voice assistant."},
                          {"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1 
            )
            return resp.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"LLM Generation Error: {e}")
            return "I'm having trouble retrieving that information right now."