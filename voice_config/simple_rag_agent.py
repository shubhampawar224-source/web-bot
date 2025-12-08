# enhanced_rag_agent.py
"""
Optimized Enhanced RAG Agent (strict context-only)
- top-3 FAISS results
- dedup + short clean
- builds compact context
- calls gpt-4o-mini for final voice-friendly answer
"""

import os
import re
import logging
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv(override=True)
logger = logging.getLogger("EnhancedRAGAgent")
logging_level = os.getenv("LOG_LEVEL", "INFO")
logger.setLevel(logging_level)

try:
    from utils.vector_store import FAISSVectorStore
except Exception as e:
    logger.error("Could not import FAISSVectorStore: %s", e)
    FAISSVectorStore = None

# OpenAI sync client for agent-level calls
try:
    from openai import OpenAI
    OPENAI_KEY = os.getenv("OPENAI_API_KEY")
    openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
except Exception as e:
    logger.warning("OpenAI client not available: %s", e)
    openai_client = None


class EnhancedRAGAgent:
    def __init__(self):
        try:
            if FAISSVectorStore is None:
                raise RuntimeError("FAISSVectorStore not available")
            self.store = FAISSVectorStore()
            self.indexed_docs = len(self.store.documents) if getattr(self.store, "documents", None) else 0
            logger.info(f"EnhancedRAGAgent ready - {self.indexed_docs} documents")
        except Exception as e:
            logger.error("RAG init error: %s", e)
            self.store = None

        self.llm_model = os.getenv("RAG_LLM_MODEL", "gpt-4o-mini")
        self.max_context_chars = 1000  # cap context length sent to LLM

    # Public entry
    def search_and_respond(self, query: str) -> str:
        if not query or not self.store:
            return "Sorry, my knowledge base is unavailable right now."

        # 1) fast search
        chunks = self._fast_search(query)

        if not chunks:
            return f"I couldn't find information about '{query}'. Could you try rephrasing the question?"

        # 2) build strict context
        context = self._build_context(chunks)

        # 3) generate strict response using LLM (only context)
        resp = self._generate_strict_response(query, context)
        return resp

    # top-3 fast search + dedupe
    def _fast_search(self, query: str) -> List[Dict[str, Any]]:
        try:
            raw = self.store.search(query=query, n_results=8)
        except Exception as e:
            logger.error("Vector search failed: %s", e)
            return []

        unique = []
        seen_short = set()
        for r in raw:
            text = (r.get("text") or "").strip()
            score = float(r.get("score", 0.0) or 0.0)
            if not text or len(text) < 30 or score <= 0:
                continue

            short = re.sub(r'\s+', ' ', text)[:120]
            key = short.lower()
            # simple near-duplicate detection
            if any(key in s or s in key for s in seen_short):
                continue
            seen_short.add(key)
            unique.append({"text": text, "score": score, "meta": r.get("metadata", {})})

            if len(unique) >= 10:
                break

        unique.sort(key=lambda x: x["score"], reverse=True)
        return unique[:3]

    def _build_context(self, chunks: List[Dict[str, Any]]) -> str:
        parts = []
        for i, c in enumerate(chunks, 1):
            clean = self._clean_text(c["text"])
            if not clean:
                continue
            # limit chunk size so entire context stays small
            parts.append(f"[Doc {i}] {clean[:400]}")
        ctx = "\n\n".join(parts)
        # final trim
        if len(ctx) > self.max_context_chars:
            ctx = ctx[: self.max_context_chars]
        return ctx.strip()

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        t = re.sub(r'http\S+', '', text)
        t = re.sub(r'\S+@\S+\.\S+', '', t)
        t = re.sub(r'<[^>]+>', '', t)
        t = re.sub(r'\[[^\]]*\]', '', t)
        t = re.sub(r'\s+', ' ', t).strip()
        return t

    def _generate_strict_response(self, query: str, context: str) -> str:
        """
        Use LLM and ensure it only uses context. Add guardrails in prompt.
        """
        if not openai_client:
            # fallback to basic assembly
            parts = context.split("\n\n")
            if parts:
                return parts[0][:400]
            return "I have some related information but cannot generate a detailed answer right now."

        prompt = f"""
You are a voice assistant. Answer the user's question using ONLY the provided context below.
Strict rules:
- Do NOT add any information not present in the context.
- Do NOT guess, hallucinate, or invent facts.
- If the context doesn't contain a direct answer, ask the user for clarification or suggest related queries.
- Keep the answer short and conversational, suitable for spoken output (2-3 sentences).

User question:
{query}

CONTEXT (use only this):
{context}

Voice assistant reply:
"""
        try:
            response = openai_client.chat.completions.create(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=220
            )
            text = ""
            # support different response shapes
            if hasattr(response, "choices") and response.choices:
                c0 = response.choices[0]
                if hasattr(c0, "message") and getattr(c0.message, "content", None):
                    text = c0.message.content
                elif getattr(c0, "text", None):
                    text = c0.text
            elif isinstance(response, dict):
                # fallback dict parsing
                choices = response.get("choices", [])
                if choices:
                    text = choices[0].get("message", {}).get("content", "") or choices[0].get("text", "")
            text = (text or "").strip()
            # If model returns something suspiciously out-of-context, fallback
            if not text:
                return "I couldn't find a concise answer in my knowledge base. Could you rephrase?"
            return text
        except Exception as e:
            logger.exception("LLM call failed: %s", e)
            # fallback simple formatting
            parts = context.split("\n\n")
            if parts:
                return parts[0][:400]
            return "I could not generate an answer at the moment."
