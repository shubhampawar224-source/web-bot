import os
import logging
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv(override=True)

# Logger setup
logger = logging.getLogger("LiteRAG")
logging.basicConfig(level=logging.INFO)

# Load Dependencies (Error handling agar utils folder na mile)
try:
    from utils.vector_store import FAISSVectorStore
except ImportError:
    print("⚠️ Warning: 'utils.vector_store' not found. Using Mock Store.")
    FAISSVectorStore = None

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
aclient = AsyncOpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

class EnhancedRAGAgent:
    def __init__(self):
        try:
            if FAISSVectorStore:
                self.store = FAISSVectorStore()
                # Cache total docs check
                self.has_docs = len(self.store.documents) > 0
                print(f"✅ RAG Initialized with {len(self.store.documents)} docs")
            else:
                self.store = None
                self.has_docs = False
        except Exception as e:
            print(f"❌ RAG Init Error: {e}")
            self.store = None
            self.has_docs = False

        self.llm_model = os.getenv("RAG_LLM_MODEL", "gpt-4o-mini")

    async def search_and_respond(self, query: str) -> str:
        # Fallback if no docs or query
        if not query: 
            return "Please say something."
        
        # Agar docs nahi hain toh seedha GPT se pucho (bina context ke)
        if not self.has_docs:
            return await self._generate_answer(query, "")

        # STEP 1: Direct Search
        try:
            results = self.store.search(query=query, n_results=3) # Top 3 is enough for speed
        except Exception:
            return "Database error."

        # STEP 2: Fast Context Build
        context_parts = []
        if results:
            for res in results:
                text = res.get("text", "").strip()
                if len(text) > 20:
                    context_parts.append(text)

        context = "\n---\n".join(context_parts)[:2000]

        # STEP 3: Generate Answer
        return await self._generate_answer(query, context)

    async def _generate_answer(self, query: str, context: str) -> str:
        if not aclient:
            return "OpenAI key missing."

        # Prompt engineering for speed & conversational tone
        system_msg = "You are a helpful voice assistant. Answer briefly (1-2 sentences). Speak naturally."
        
        if context:
            prompt = f"Context:\n{context}\n\nUser: {query}\nAnswer based on Context only."
        else:
            prompt = f"User: {query}\nAnswer general question briefly."

        try:
            resp = await aclient.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=80, # Fast token limit
                temperature=0.3
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM Error: {e}")
            return "I'm having trouble connecting."