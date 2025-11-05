# utils/chat_service.py

import re
import uuid
from datetime import datetime
from typing import Tuple, List, Optional
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
# from langchain.chat_models import ChatOpenAI
from langchain_openai import ChatOpenAI
import httpx
import openai
from openai import OpenAI

from database.db import SessionLocal
from model.models import Firm, Website
from utils.vector_store import collection, embedding_model, query_similar_texts
from utils.prompt_engine import my_prompt_function, session_memory
from config import OPENAI_API_KEY

# Debug API key loading
if OPENAI_API_KEY:
    print(f"✅ OpenAI API key loaded (starts with: {OPENAI_API_KEY[:10]}...)")
else:
    print("❌ OpenAI API key not found in environment variables")

# ---------------- LLM Setup with Error Handling ----------------
def create_llm_client():
    """Create LLM client with proper timeout and retry settings"""
    try:
        # Create direct OpenAI client as fallback
        openai_client = OpenAI(
            api_key=OPENAI_API_KEY,
            timeout=30.0,  # 30 second timeout
            max_retries=3
        )
        
        # Create LangChain ChatOpenAI with custom HTTP client
        custom_http_client = httpx.Client(
            timeout=30.0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        
        llm = ChatOpenAI(
            model_name="gpt-4o", 
            temperature=0, 
            openai_api_key=OPENAI_API_KEY,
            http_client=custom_http_client,
            request_timeout=30
        )
        
        return llm, openai_client
    except Exception as e:
        print(f"Error creating LLM client: {e}")
        return None, None

llm, openai_client = create_llm_client()

def test_connectivity():
    """Test connectivity to OpenAI API"""
    try:
        if openai_client is not None:
            # Make a simple API call to test connectivity
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=5,
                timeout=10
            )
            print("✅ OpenAI API connectivity test successful")
            return True
    except httpx.ConnectError:
        print("❌ Network connectivity issue - cannot reach OpenAI API")
        return False
    except openai.AuthenticationError:
        print("❌ Invalid OpenAI API key")
        return False
    except Exception as e:
        print(f"❌ Connectivity test failed: {e}")
        return False

def call_llm_with_fallback(prompt_text: str, max_retries: int = 3) -> str:
    """Call LLM with fallback to direct OpenAI client if LangChain fails"""
    
    # Try LangChain ChatOpenAI first
    for attempt in range(max_retries):
        try:
            if llm is not None:
                print(f"Attempting LangChain call (attempt {attempt + 1}/{max_retries})")
                response_obj = llm.invoke(prompt_text)
                return response_obj.content
        except (httpx.ConnectError, openai.APIConnectionError, Exception) as e:
            print(f"LangChain attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
            continue
    
    # Fallback to direct OpenAI client
    for attempt in range(max_retries):
        try:
            if openai_client is not None:
                print(f"Attempting direct OpenAI call (attempt {attempt + 1}/{max_retries})")
                response = openai_client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt_text}],
                    temperature=0,
                    timeout=30
                )
                return response.choices[0].message.content
        except (httpx.ConnectError, openai.APIConnectionError, Exception) as e:
            print(f"Direct OpenAI attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(2 ** attempt)  # Exponential backoff
            continue
    
    # If all attempts fail, return error message
    return "I'm currently experiencing connectivity issues. Please try again in a moment."

# ---------------- Session Memory Utilities ----------------
def update_session_suggestions(session_id: str, suggestions: List[str]):
    """Store follow-up suggestions for a session."""
    session_memory["previous_suggestions"] = suggestions
    session_memory.setdefault("last_selected_firm", {})[session_id] = None


def update_session_firm(session_id: str, firm_id: int):
    """Store last selected firm for a session."""
    session_memory.setdefault("last_selected_firm", {})[session_id] = firm_id


def get_last_selected_firm(session_id: str) -> Optional[int]:
    """Get last selected firm for a session."""
    return session_memory.get("last_selected_firm", {}).get(session_id)


# ---------------- Helper: Extract Follow-Up Suggestions ----------------
def extract_suggestions_from_response(response_text: str) -> List[str]:
    suggestions = []
    marker = "**Follow-Up"
    if marker in response_text:
        section = response_text.split(marker, 1)[1]
        for line in section.splitlines():
            if line.strip().startswith("- "):
                suggestions.append(line.strip()[2:])
    return suggestions


# ---------------- Helper: Load Firm & Links from DB ----------------
def load_firm_and_links(firm_id: int) -> Tuple[str, List[str]]:
    """Fetch firm name and all links from websites associated with this firm."""
    db: Session = SessionLocal()
    try:
        firm = db.query(Firm).filter(Firm.id == firm_id).first()
        if not firm:
            return "Unknown Firm", []

        websites = db.query(Website).filter(Website.firm_id == firm.id).all()
        links_list = []
        about_texts = []

        for w in websites:
            # about_data = w.scraped_data.get("about", {}) if w.scraped_data else {}
            links_data = w.scraped_data.get("links", []) if w.scraped_data and isinstance(w.scraped_data, dict) else []

            # about_texts.append(about_data.get("full_text", ""))
            for link in links_data:
                if isinstance(link, dict):
                    links_list.append(f"{link.get('text','')} → {link.get('url','')}")
                elif isinstance(link, str):
                    links_list.append(link)

        firm_name = re.sub(r"^(www\.)|(\.com)$", "", firm.name, flags=re.IGNORECASE)
        # context_text = " ".join(about_texts)
        return firm_name, links_list
    finally:
        db.close()


# ---------------- Main: Get Answer ----------------
def get_answer_from_db(query: str, firm_id: int = None, session_id: Optional[str] = None, url_context: Optional[str] = None) -> str:
    """Get answer from database - supports both firm_id and URL-specific context"""
    session_id = session_id or str(uuid.uuid4())

    try:
        # 1️⃣ Embed user query
        query_embedding = embedding_model.encode(query).tolist()

        docs = []
        firm_name = "Assistant"
        links_list = []

        if url_context:
            # URL-specific context - query user-submitted content
            url_ids = [id.strip() for id in url_context.split(',') if id.strip()]
            print(f"🔍 Searching vector DB for request_ids: {url_ids}")
            
            if url_ids:
                # Query user_website type content with specific request_ids
                # Note: ChromaDB uses $in operator for matching multiple values
                results = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=10,
                    where={"$and": [
                        {"type": "user_website"},
                        {"request_id": {"$in": url_ids}}
                    ]},
                )
                docs = results["documents"][0] if results["documents"] else []
                print(f"📄 Found {len(docs)} documents from vector search")
                
                # Try to get firm name from metadata
                if results["metadatas"] and results["metadatas"][0]:
                    for metadata in results["metadatas"][0]:
                        if isinstance(metadata, dict) and metadata.get("firm_name"):
                            firm_name = metadata["firm_name"]
                            print(f"🏢 Extracted firm name from metadata: {firm_name}")
                            break
                        
        elif firm_id:
            # 2️⃣ Retrieve top 5 firm-specific docs from vector DB
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=5,
                where={"$and": [{"type": "website"}, {"firm_id": str(firm_id)}]},
            )
            docs = results["documents"][0] if results["documents"] else []

            # 3️⃣ Load firm context & links
            firm_name, links_list = load_firm_and_links(firm_id)
        
        # 4️⃣ Merge retrieved docs + context
        MAX_DOC_CHARS = 5000
        docs = [d[:MAX_DOC_CHARS] for d in docs]
        context_text = " ".join(docs)

        # 5️⃣ Generate prompt (use session memory suggestions)
        is_followup = bool(session_memory.get("previous_suggestions"))
        prompt_text = my_prompt_function(
            firm=firm_name,
            context=context_text,
            question=query,
            is_followup=is_followup,
            Urls= links_list,
        )

        # 6️⃣ LLM response with fallback handling
        print("Calling LLM for response...")
        response_text = call_llm_with_fallback(prompt_text)
        
        # Check if we got a connectivity error message
        if "connectivity issues" in response_text:
            return response_text

        # 7️⃣ Extract follow-up suggestions & update session
        new_suggestions = extract_suggestions_from_response(response_text)
        if new_suggestions:
            update_session_suggestions(session_id, new_suggestions)

        # 8️⃣ Clean final text
        try:
            answer_text = response_text[:response_text.index("{")].strip()
        except ValueError:
            answer_text = response_text

        # 9️⃣ Store assistant answer in vector DB
        answer_embedding = embedding_model.encode(answer_text).tolist()
        collection.add(
            ids=[f"assistant_{session_id}_{uuid.uuid4()}"],
            embeddings=[answer_embedding],
            documents=[answer_text],
            metadatas=[{
                "type": "chat",
                "role": "assistant",
                "session_id": session_id,
                "firm_id": str(firm_id) if firm_id else "general",
                "timestamp": datetime.now().isoformat()
            }],
        )

        # 🔟 Update last selected firm in session memory
        if firm_id:
            update_session_firm(session_id, firm_id)
        return answer_text

    except httpx.ConnectError as e:
        print(f"[Network Error in get_answer_from_db]: Connection failed - {e}")
        return "I'm having trouble connecting to my AI service. Please check your internet connection and try again."
    except openai.APIConnectionError as e:
        print(f"[OpenAI Connection Error in get_answer_from_db]: {e}")
        return "I'm having trouble reaching the AI service. Please try again in a moment."
    except openai.RateLimitError as e:
        print(f"[Rate Limit Error in get_answer_from_db]: {e}")
        return "I'm receiving too many requests right now. Please wait a moment and try again."
    except openai.AuthenticationError as e:
        print(f"[Authentication Error in get_answer_from_db]: {e}")
        return "There's an issue with my AI service configuration. Please contact support."
    except Exception as e:
        print(f"[General Error in get_answer_from_db]: {type(e).__name__}: {e}")
        return "Sorry, I encountered an unexpected issue. Please try again."