# utils/chat_service.py

import re
import uuid
from datetime import datetime
from typing import Tuple, List, Optional
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from langchain.chat_models import ChatOpenAI
from database.db import SessionLocal
from model.models import Firm, Website
from utils.vector_store import collection, embedding_model
from utils.prompt_engine import my_prompt_function, session_memory
from config import OPENAI_API_KEY

# ---------------- LLM Setup ----------------
llm = ChatOpenAI(model_name="gpt-4o", temperature=0, openai_api_key=OPENAI_API_KEY)

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
def load_firm_and_links(firm_id: int) -> Tuple[str, str, List[str]]:
    """Fetch firm name and all links from websites associated with this firm."""
    db: Session = SessionLocal()
    try:
        firm = db.query(Firm).filter(Firm.id == firm_id).first()
        if not firm:
            return "Unknown Firm", "", []

        websites = db.query(Website).filter(Website.firm_id == firm.id).all()
        links_list = []
        about_texts = []

        for w in websites:
            about_data = w.scraped_data.get("about", {}) if w.scraped_data else {}
            links_data = w.scraped_data.get("links", []) if w.scraped_data else []

            about_texts.append(about_data.get("full_text", ""))
            for link in links_data:
                if isinstance(link, dict):
                    links_list.append(f"{link.get('text','')} → {link.get('url','')}")
                elif isinstance(link, str):
                    links_list.append(link)

        firm_name = re.sub(r"^(www\.)|(\.com)$", "", firm.name, flags=re.IGNORECASE)
        context_text = " ".join(about_texts)
        return firm_name, context_text, links_list
    finally:
        db.close()


# ---------------- Main: Get Answer ----------------
def get_answer_from_db(query: str, firm_id: int, session_id: Optional[str] = None) -> str:
    session_id = session_id or str(uuid.uuid4())

    try:
        # 1️⃣ Embed user query
        query_embedding = embedding_model.encode(query).tolist()

        # 2️⃣ Retrieve top 5 firm-specific docs from vector DB
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5,
            where={"$and": [{"type": "website"}, {"firm_id": str(firm_id)}]},
        )
        docs = results["documents"][0] if results["documents"] else []

        # 3️⃣ Load firm context & links
        firm_name, context_text_from_db, links_list = load_firm_and_links(firm_id)

        # 3a️⃣ Truncate long firm context
        MAX_CHARS = 20000
        if len(context_text_from_db) > MAX_CHARS:
            context_text_from_db = context_text_from_db[:MAX_CHARS] + " ...[truncated]"

        # 4️⃣ Merge retrieved docs + context
        MAX_DOC_CHARS = 5000
        docs = [d[:MAX_DOC_CHARS] for d in docs]
        context_text = " ".join(docs) + "\n\n" + context_text_from_db

        # 5️⃣ Generate prompt (use session memory suggestions)
        is_followup = bool(session_memory.get("previous_suggestions"))
        prompt_text = my_prompt_function(
            firm=firm_name,
            context=context_text,
            question=query,
            is_followup=is_followup,
            Urls= links_list,
        )

        # 6️⃣ LLM response
        response_obj = llm.invoke(prompt_text)
        response_text = response_obj.content

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
            metadatas={
                "type": "chat",
                "role": "assistant",
                "session_id": session_id,
                "firm_id": str(firm_id),
                "timestamp": datetime.now().isoformat()
            },
        )

        # 🔟 Update last selected firm in session memory
        update_session_firm(session_id, firm_id)
        return answer_text

    except Exception as e:
        print(f"[Error in get_answer_from_db]: {e}")
        return "Sorry, I couldn’t retrieve relevant information right now."
