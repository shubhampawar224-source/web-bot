import uuid
import asyncio
import os
import httpx
from datetime import datetime
from typing import Optional, List, Dict
from collections import deque
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

# Database imports REMOVED for speed
from utils.vector_store import collection, embedding_model
from utils.prompt_engine import my_prompt_function
from utils.memory import SESSION_STORE

# Import Optimized Agentic Search
try:
    from utils.agentic_search import AgenticSearchAgent
    AGENTIC_SEARCH_ENABLED = True
    print("✅ Agentic Search enabled")
except ImportError:
    AGENTIC_SEARCH_ENABLED = False
    print("⚠️ Agentic Search not available")

load_dotenv(override=True)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# ==============================================================================
# 1. ULTRA-FAST LLM CLIENT SETUP
# ==============================================================================

connection_limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)

sync_http_client = httpx.Client(limits=connection_limits, timeout=20.0)
async_http_client = httpx.AsyncClient(limits=connection_limits, timeout=20.0)

llm = ChatOpenAI(
    model_name="gpt-4o",
    temperature=0,
    openai_api_key=OPENAI_API_KEY,
    http_client=sync_http_client,        
    http_async_client=async_http_client, 
    request_timeout=20,
    max_retries=1
)

# ==============================================================================
# 2. IN-MEMORY SESSION STORE (Integrated Memory Logic)
# ==============================================================================

# Global Store: { "session_id": deque([{role:..., content:...}]) }
# Ye RAM mein rahega for instant access
SESSION_STORE: Dict[str, deque] = {}

def get_chat_history_str(session_id: str) -> str:
    """Fetch recent history formatted for prompt"""
    history = SESSION_STORE.get(session_id)
    if not history:
        return ""
    
    # Format: "User: ... \n Assistant: ..."
    return "\n".join([f"{msg['role'].title()}: {msg['content']}" for msg in history])

def add_to_history(session_id: str, user_q: str, ai_a: str):
    """Update history (Keep last 6 turns)"""
    if session_id not in SESSION_STORE:
        SESSION_STORE[session_id] = deque(maxlen=6)
    
    SESSION_STORE[session_id].append({"role": "user", "content": user_q})
    SESSION_STORE[session_id].append({"role": "assistant", "content": ai_a})

def update_followup_suggestions(answer_text: str):
    """Extracts follow-up suggestions from text and updates global memory"""
    try:
        if "**Follow-Up" in answer_text:
            # Parse text like "- Question 1"
            section = answer_text.split("**Follow-Up")[1]
            suggestions = [
                line.strip()[2:] 
                for line in section.splitlines() 
                if line.strip().startswith("- ")
            ]
            if suggestions:
                SESSION_STORE["previous_suggestions"] = suggestions
    except Exception:
        pass

# ==============================================================================
# 3. ASYNC HELPERS
# ==============================================================================

async def get_embedding_async(text: str):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: embedding_model.encode(text).tolist())

async def search_vector_db_async(query_embedding, firm_id, n_results=5):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        where={"$and": [
            {"type": {"$in": ["website", "manual_knowledge"]}},
            {"firm_id": str(firm_id)}
        ]}
    ))

async def save_chat_background(session_id, firm_id, answer_text):
    """Save to Vector DB (Disk) without making user wait"""
    try:
        answer_embedding = await get_embedding_async(answer_text)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: collection.add(
            ids=[f"assistant_{session_id}_{uuid.uuid4()}"],
            embeddings=[answer_embedding],
            documents=[answer_text],
            metadatas=[{
                "type": "chat",
                "role": "assistant",
                "session_id": session_id,
                "firm_id": str(firm_id),
                "timestamp": datetime.now().isoformat()
            }]
        ))
    except Exception as e:
        print(f"Background Save Error: {e}")

# ==============================================================================
# 4. FIRM AGENT CLASS
# ==============================================================================

class FirmAgent:
    def __init__(self, session_id: str, firm_id: int):
        self.session_id = session_id
        self.firm_id = str(firm_id)

    async def ask(self, query: str, custom_api_key: str = None, url_context_ids: str = None) -> str:
        try:
            # 1. Parallel: Embedding + History
            embedding_task = get_embedding_async(query)
            # Memory ab direct yahan se fetch ho rahi hai (Integrated)
            chat_history_str = get_chat_history_str(self.session_id)
            query_embedding = await embedding_task

            # 2. Retrieval Strategy
            docs = []
            metadatas = []

            if url_context_ids:
                url_ids = [id.strip() for id in url_context_ids.split(',') if id.strip()]
                loop = asyncio.get_event_loop()
                raw_results = await loop.run_in_executor(None, lambda: collection.query(
                    query_embeddings=[query_embedding],
                    n_results=8,
                    where={"$and": [
                        {"type": "user_website"},
                        {"request_id": {"$in": url_ids}}
                    ]}
                ))
                docs = raw_results["documents"][0] if raw_results["documents"] else []
                metadatas = raw_results["metadatas"][0] if raw_results["metadatas"] else []

            elif AGENTIC_SEARCH_ENABLED:
                agent = AgenticSearchAgent(collection)
                search_data = await agent.search(query, firm_id=self.firm_id, n_results=5)
                docs = [r["content"] for r in search_data.get("final_results", [])]
                metadatas = [r["metadata"] for r in search_data.get("final_results", [])]
            
            else:
                raw_results = await search_vector_db_async(query_embedding, self.firm_id)
                docs = raw_results["documents"][0] if raw_results["documents"] else []
                metadatas = raw_results["metadatas"][0] if raw_results["metadatas"] else []

            # 3. Metadata Extraction
            firm_name = "Assistant"
            relevant_urls = []
            if metadatas:
                first_meta = metadatas[0]
                if isinstance(first_meta, dict):
                    firm_name = first_meta.get("firm_name", "Firm")
                
                seen_urls = set()
                for meta in metadatas:
                    if isinstance(meta, dict):
                        url = meta.get("url") or meta.get("source")
                        if url and url not in seen_urls:
                            relevant_urls.append(url)
                            seen_urls.add(url)

            # 4. Prompt Generation
            if not docs:
                context_text = "No specific documents found."
            else:
                context_text = "\n\n".join([str(d)[:2000] for d in docs[:4]])

            prompt_text = my_prompt_function(
                firm=firm_name,
                context=context_text,
                question=query,
                chat_history_str=chat_history_str, # Passing history for follow-up context
                Urls=relevant_urls
            )

            # 5. LLM Call
            print("🚀 Sending to LLM...")
            active_llm = llm
            if custom_api_key:
                active_llm = ChatOpenAI(
                    model_name="gpt-4o",
                    temperature=0,
                    openai_api_key=custom_api_key,
                    http_async_client=async_http_client,
                    request_timeout=20
                )

            response_obj = await active_llm.ainvoke(prompt_text)
            response_text = response_obj.content

            # 6. Post-Process (Update Memory & DB)
            # Update History Logic Integrated Here
            add_to_history(self.session_id, query, response_text)
            
            # Extract & Update Follow-ups for UI
            update_followup_suggestions(response_text)
            
            # Background Save to DB
            asyncio.create_task(save_chat_background(self.session_id, self.firm_id, response_text))

            return response_text

        except Exception as e:
            print(f"❌ Agent Error: {e}")
            return "I encountered a temporary issue. Please try again."

# ==============================================================================
# 5. API WRAPPER
# ==============================================================================

async def get_answer_from_db(query: str, firm_id: int = None, session_id: Optional[str] = None, url_context: Optional[str] = None, custom_api_key: str = None) -> str:
    if not session_id:
        session_id = str(uuid.uuid4())
        
    agent = FirmAgent(session_id, firm_id)
    return await agent.ask(query, custom_api_key=custom_api_key, url_context_ids=url_context)