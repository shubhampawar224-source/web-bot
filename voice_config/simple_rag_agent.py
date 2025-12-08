# enhanced_rag_agent.py

import os
import json
import time
import logging
import re
from typing import List, Dict, Any
from utils.vector_store import FAISSVectorStore
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(override=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedRAGAgent:
    """Optimized RAG Agent (Fast, Accurate, Noise-Free)"""

    def __init__(self):
        try:
            self.vector_store = FAISSVectorStore()
            total_docs = len(self.vector_store.documents) if self.vector_store.documents else 0
            logger.info(f"RAG Ready - {total_docs} documents indexed")

            key = os.getenv("OPENAI_API_KEY")
            self.client = OpenAI(api_key=key) if key else None
            self.use_ai_formatting = bool(key)

        except Exception as e:
            logger.error(f"RAG Init Failed: {e}")
            self.vector_store = None
            self.client = None
            self.use_ai_formatting = False

    # ----------------------------------------------------
    # MAIN ENTRY POINT
    # ----------------------------------------------------
    def search_and_respond(self, query: str) -> str:
        try:
            if not self.vector_store:
                return "I cannot access my knowledge base at the moment."

            results = self._smart_search(query)

            if not results:
                return f"I couldn't find information about '{query}'. Try rephrasing the question."

            if self.use_ai_formatting:
                return self._generate_ai_response(query, results)
            else:
                return self._format_basic_response(query, results)

        except Exception as e:
            logger.error(f"RAG Error: {e}")
            return "Something went wrong. Please try again."

    # ----------------------------------------------------
    # SMART SEARCH (Optimized)
    # ----------------------------------------------------
    def _smart_search(self, query: str):
        all_results = []

        # Direct fast lookup
        direct = self.vector_store.search(query=query, n_results=7)
        all_results.extend(direct)

        # Keyword expansion (2 best keywords only)
        for kw in self._extract_keywords(query)[:2]:
            all_results.extend(self.vector_store.search(kw, n_results=4))

        # Remove duplicates using short-window matching
        unique = []
        seen = []

        for r in all_results:
            text = r.get("text", "").strip()
            if len(text) < 40:
                continue

            short_slice = text[:60]
            if any(short_slice in s or s in short_slice for s in seen):
                continue

            seen.append(short_slice)
            unique.append(r)

        # Highest confidence first
        unique.sort(key=lambda x: x.get("score", 0), reverse=True)

        return unique[:3]  # Top 3 → best for accuracy & speed

    # ----------------------------------------------------
    # Smart keyword extraction
    # ----------------------------------------------------
    def _extract_keywords(self, query: str):
        q = query.lower()
        keys = []

        if "law" in q or "legal" in q:
            keys.append("legal services")
            keys.append("law firm overview")

        if "contact" in q or "email" in q or "phone" in q:
            keys.append("contact information")

        if "about" in q or "who" in q:
            keys.append("about the firm")

        return keys

    # ----------------------------------------------------
    # AI FORMATTED RESPONSE
    # ----------------------------------------------------
    def _generate_ai_response(self, query, results):
        try:
            context = "\n\n".join(
                self._clean(r.get("text", ""))[:400]
                for r in results if r.get("text")
            )

            prompt = f"""
                Answer the user's question using ONLY the context below.
                Do NOT add any outside knowledge.
                Do NOT mention that you're using context.
                Keep the reply short (3–4 sentences), natural, and conversational.

                User Question:
                {query}

                Context:
                {context}

                Voice Assistant Reply:
                """

            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=180
            )

            return resp.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"AI formatting error: {e}")
            return self._format_basic_response(query, results)

    # ----------------------------------------------------
    # CLEAN CONTENT
    # ----------------------------------------------------
    def _clean(self, text: str):
        if not text:
            return ""

        text = re.sub(r"http[^ ]+", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\S+@\S+\.\S+", "", text)
        text = re.sub(r"\[[^\]]*\]", "", text)
        text = re.sub(r"\s+", " ", text)

        return text.strip()

    # ----------------------------------------------------
    # BASIC RESPONSE (fallback)
    # ----------------------------------------------------
    def _format_basic_response(self, query, results):
        parts = [self._clean(r.get("text", ""))[:250] for r in results if r.get("text")]

        if not parts:
            return "I found related data but couldn't format it."

        if len(parts) == 1:
            return parts[0]

        return f"{parts[0]} Additionally, {parts[1]}."
