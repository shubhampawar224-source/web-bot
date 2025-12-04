import asyncio
import io
import os
import re
import json
import base64
import time
import uuid
from typing import List, Dict, Any
from fastapi import WebSocket
from collections import defaultdict
from dotenv import load_dotenv
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain.memory import ConversationSummaryBufferMemory
from langchain.agents import create_sql_agent, AgentType
from sqlalchemy import inspect
from voice_config.prompt_manager import voice_rag_prompt
from voice_config.simple_rag_agent import EnhancedRAGAgent

# ========================================
# ENVIRONMENT
# ========================================
load_dotenv(override=True)
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
# Use the main application database that contains firms, websites, and pages data
db_uri = os.getenv("DATABASE_URL", "sqlite:///./kitkool_bot.db")

if not OPENAI_KEY:
    raise RuntimeError("Please set OPENAI_API_KEY in .env")

# ========================================
# DYNAMIC SCHEMA HANDLER
# ========================================
def get_allowed_columns(db: SQLDatabase):
    """Auto-detect table names and their columns dynamically."""
    try:
        inspector = inspect(db._engine)
        schema_summary = {}

        for table_name in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns(table_name)]
            schema_summary[table_name] = columns

        return schema_summary
    except Exception as e:
        print(f"⚠️ Schema introspection failed: {e}")
        return {}


def summarize_schema(db: SQLDatabase, max_cols=8):
    """Generate a compact schema summary for prompts (avoids large schema dumps)."""
    inspector = inspect(db._engine)
    summaries = []
    for table in inspector.get_table_names():
        cols = [c["name"] for c in inspector.get_columns(table)]
        if len(cols) > max_cols:
            cols = cols[:max_cols] + ["..."]
        summaries.append(f"{table}({', '.join(cols)})")
    return "; ".join(summaries)


# ========================================
# MEMORY MANAGER
# ========================================
class MemoryManager:
    """Manages session-based memory with expiration."""
    def __init__(self, expiry_seconds: int = 1800):
        self.memories = defaultdict(
            lambda: {
                "memory": ConversationSummaryBufferMemory(
                    llm=ChatOpenAI(model="gpt-4o-mini", temperature=0),
                    max_token_limit=1000
                ),
                "last_access": time.time()
            }
        )
        self.expiry_seconds = expiry_seconds

    def get_memory(self, session_id: str):
        self.cleanup()
        self.memories[session_id]["last_access"] = time.time()
        return self.memories[session_id]["memory"]

    def cleanup(self):
        now = time.time()
        expired = [sid for sid, data in self.memories.items()
                   if now - data["last_access"] > self.expiry_seconds]
        for sid in expired:
            del self.memories[sid]

# ========================================
# VOICE ASSISTANT CLASS
# ========================================

class VoiceAssistant:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_KEY)
        self.memory_manager = MemoryManager()
        
        # Initialize Enhanced RAG Agent for advanced vector search
        try:
            self.rag_agent = EnhancedRAGAgent()
            print("[VoiceAssistant] Enhanced RAG Agent initialized successfully")
        except Exception as e:
            print(f"[VoiceAssistant] Warning: Could not initialize RAG Agent: {e}")
            self.rag_agent = None

        # --- Database setup ---
        self.db = SQLDatabase.from_uri(
            db_uri,
            sample_rows_in_table_info=3,  # Show more examples including JSON data
            max_string_length=2000  # Allow longer strings to show full JSON structures
        )
        self.llm = ChatOpenAI(
            model="gpt-4o-mini", 
            temperature=0,
            request_timeout=15,  # 15 second timeout for LLM calls
            max_retries=1  # Reduce retries for faster failure
        )

        # --- Dynamic schema mapping ---
        allowed_columns = get_allowed_columns(self.db)
        schema_summary = summarize_schema(self.db)

        # --- Toolkit with dynamic schema ---
        self.toolkit = SQLDatabaseToolkit(
            db=self.db,
            llm=self.llm,
            allowed_columns=allowed_columns
        )

        # --- Custom prompt with actual schema summary ---
        self.prompt = voice_rag_prompt(schema_summary)

        # --- SQL Agent with optimization ---
        self.voice_agent = create_sql_agent(
            llm=self.llm,
            toolkit=self.toolkit,
            verbose=True,  # Enable verbose to see what agent is doing
            handle_parsing_errors=True,
            agent_type=AgentType.OPENAI_FUNCTIONS,
            prompt=self.prompt,
            max_iterations=8,  # Increase for deeper search
            max_execution_time=20,  # Increase timeout for thorough search
            early_stopping_method="generate"  # Stop early if answer found
        )

    # -------------------------
    # WebSocket Handling
    # -------------------------
    SILENCE_TIMEOUT = 10  # seconds

    async def handle_ws(self, ws: WebSocket):
        await ws.accept()
        session_id = str(uuid.uuid4())
        ws.session_id = session_id
        await ws.send_json({"info": "Session created", "session_id": session_id})

        silence_task = asyncio.create_task(self.silence_watchdog(ws))

        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data)

                # Stop connection
                if msg.get("stop"):
                    silence_task.cancel()
                    await ws.close()
                    break

                # Handle audio
                audio_b64 = msg.get("audio")
                if audio_b64:
                    audio_bytes = base64.b64decode(audio_b64)
                    silence_task.cancel()
                    silence_task = asyncio.create_task(self.silence_watchdog(ws))
                    await self.process_audio(ws, audio_bytes, ws.session_id)

        except Exception as e:
            print(f"WebSocket error: {e}")
            await ws.close()
            silence_task.cancel()

    async def silence_watchdog(self, ws: WebSocket):
        try:
            await asyncio.sleep(self.SILENCE_TIMEOUT)
            # Check if WebSocket is still connected before sending timeout message
            if ws.client_state.name == "CONNECTED":
                try:
                    await ws.send_json({"bot_text": "No input detected. Ending the session.", "audio": ""})
                    await ws.close()
                except Exception as e:
                    print(f"Error sending timeout message: {e}")
                    # Try to close anyway
                    try:
                        await ws.close()
                    except:
                        pass
        except asyncio.CancelledError:
            pass

    # -------------------------
    # Audio -> Text -> Agent
    # -------------------------
    async def process_audio(self, ws: WebSocket, audio_bytes: bytes, session_id: str):
        # Check if WebSocket is still connected
        if ws.client_state.name != "CONNECTED":
            print("WebSocket disconnected during audio processing")
            return None
            
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "input.wav"

        try:
            stt_resp = self.client.audio.transcriptions.create(
                model="whisper-1", file=audio_file
            )
            user_text = stt_resp.text.strip()
        except Exception as e:
            print(f"STT Error: {e}")
            await self.safe_send(ws, "Sorry, I couldn't understand you clearly.")
            return None

        if not user_text:
            return None

        print(f"🧠 User said: {user_text}")

        if any(kw in user_text.lower() for kw in ["bye","thanks", "exit", "stop", "thanks"]):
            await self.safe_send(ws, "Goodbye! Have a great day!", user_text)
            return "exit"

        bot_text = await self.ask_agent(session_id, user_text)
        await self.safe_send(ws, bot_text, user_text)
        return None

    # -------------------------
    # Agent Processing
    # -------------------------
    async def ask_agent(self, session_id: str, user_text: str) -> str:
        try:
            memory = self.memory_manager.get_memory(session_id)
            memory.chat_memory.add_user_message(user_text)

            # Use Enhanced RAG Agent for intelligent search
            if self.rag_agent:
                print(f"🔍 Using Enhanced RAG Agent for query: {user_text}")
                start_time = time.time()
                
                try:
                    # Use Enhanced RAG Agent's intelligent search
                    response = await asyncio.to_thread(
                        self.rag_agent.search_and_respond, user_text
                    )
                    
                    elapsed = time.time() - start_time
                    print(f"✅ Enhanced RAG search completed in {elapsed:.2f}s")
                    
                    if response and len(response.strip()) > 10:
                        memory.chat_memory.add_ai_message(response)
                        return response
                    else:
                        print("⚠️ Enhanced RAG returned empty response")
                        
                except Exception as rag_error:
                    print(f"❌ Enhanced RAG error: {rag_error}")
                    
            # Fallback response
            bot_text = "I'm having trouble accessing my knowledge base right now. Could you try rephrasing your question or ask something else?"
            
            memory.chat_memory.add_ai_message(bot_text)
            return bot_text

        except asyncio.TimeoutError:
            print(f"⏰ Agentic search timeout")
            return "I'm taking longer than usual to search. Please try your question again, perhaps with different keywords."
        except Exception as e:
            print(f"❌ Agentic search system error: {e}")
            return "I'm experiencing some technical difficulties. Please try your question again in a moment."
    
    async def _perform_agentic_search(self, query: str) -> str:
        """
        Agentic search approach - uses multiple search strategies
        """
        try:
            # Strategy 1: Direct query search
            print(f"🎯 Strategy 1: Direct search for '{query}'")
            direct_results = self.rag_agent.vector_store.search(query=query, n_results=8)
            
            # Strategy 2: Keyword expansion search
            keywords = self._extract_keywords(query)
            keyword_results = []
            if keywords:
                print(f"🔑 Strategy 2: Keyword search for {keywords}")
                for keyword in keywords:
                    kw_results = self.rag_agent.vector_store.search(query=keyword, n_results=5)
                    keyword_results.extend(kw_results)
            
            # Strategy 3: Context-based search (if previous memory exists)
            context_results = []
            if hasattr(self, 'memory_manager'):
                # Add context-aware search logic here if needed
                pass
            
            # Combine and deduplicate results
            all_results = direct_results + keyword_results + context_results
            unique_results = self._deduplicate_results(all_results)
            
            print(f"📊 Combined {len(unique_results)} unique results from agentic search")
            
            if not unique_results:
                return self._get_no_results_agentic_response(query)
            
            # Agentic response generation using LLM
            response = await self._generate_agentic_response(query, unique_results)
            return response
            
        except Exception as e:
            print(f"❌ Error in agentic search: {e}")
            return "I encountered an error during my search process. Please try rephrasing your question."
    
    def _extract_keywords(self, query: str) -> List[str]:
        """Extract key terms from query for expanded search"""
        import re
        
        # Remove common stop words
        stop_words = {'the', 'is', 'are', 'what', 'how', 'can', 'do', 'you', 'tell', 'me', 'about', 'find', 'search'}
        
        # Extract words (simple approach)
        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [word for word in words if len(word) > 3 and word not in stop_words]
        
        return keywords[:3]  # Limit to 3 most relevant keywords
    
    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        """Remove duplicate results based on text similarity"""
        if not results:
            return []
        
        unique_results = []
        seen_texts = set()
        
        for result in results:
            text = result.get('text', '').strip()
            if text and text not in seen_texts and len(text) > 20:
                # Check for near-duplicate text
                is_duplicate = False
                for seen_text in seen_texts:
                    if self._texts_similar(text, seen_text):
                        is_duplicate = True
                        break
                
                if not is_duplicate:
                    unique_results.append(result)
                    seen_texts.add(text)
        
        # Sort by score (descending)
        unique_results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return unique_results[:5]  # Top 5 unique results
    
    def _texts_similar(self, text1: str, text2: str) -> bool:
        """Check if two texts are too similar (simple approach)"""
        if not text1 or not text2:
            return False
        
        # Simple similarity check - if one text is contained in another
        shorter = text1 if len(text1) < len(text2) else text2
        longer = text2 if shorter == text1 else text1
        
        if len(shorter) > 50 and shorter in longer:
            return True
        
        return False
    
    async def _generate_agentic_response(self, query: str, results: List[Dict]) -> str:
        """
        Generate intelligent response using LLM with search results
        """
        try:
            if not results:
                return self._get_no_results_agentic_response(query)
            
            # Prepare context from results
            context_parts = []
            for i, result in enumerate(results[:4], 1):  # Top 4 results
                text = result.get('text', '').strip()
                score = result.get('score', 0)
                metadata = result.get('metadata', {})
                source = metadata.get('url', 'Unknown source')
                
                if text:
                    # Clean and truncate text
                    clean_text = text[:300] + "..." if len(text) > 300 else text
                    context_parts.append(f"[Context {i}] (Score: {score:.2f})\n{clean_text}")
            
            context = "\n\n".join(context_parts)
            
            # Generate response using existing LLM
            prompt = f"""You are a helpful voice assistant. Use the provided context to answer the user's question naturally and conversationally.

User Question: {query}

Available Context:
{context}

Instructions:
- Provide a natural, conversational response suitable for voice interaction
- Use information from the context to answer comprehensively
- If context is limited, acknowledge it but provide what you can
- Keep the response between 2-4 sentences for voice clarity
- Be helpful and informative
- Don't mention technical terms like "database", "search results", or "context"

Response:"""

            # Use existing LLM for response generation
            result = await asyncio.to_thread(
                self.llm.invoke, prompt
            )
            
            response_text = result.content if hasattr(result, 'content') else str(result)
            
            # Clean up response
            response_text = self.clean_response(response_text, query)
            
            if not response_text or len(response_text.strip()) < 10:
                return self._get_fallback_agentic_response(query, results)
            
            return response_text
            
        except Exception as e:
            print(f"❌ Error generating agentic response: {e}")
            return self._get_fallback_agentic_response(query, results)
    
    def _get_no_results_agentic_response(self, query: str) -> str:
        """Intelligent no-results response"""
        return f"I searched thoroughly for information about '{query}' but couldn't find relevant details in my knowledge base. Could you try asking about this topic in a different way, or perhaps ask about something related?"
    
    def _get_fallback_agentic_response(self, query: str, results: List[Dict]) -> str:
        """Fallback response when LLM generation fails"""
        if not results:
            return self._get_no_results_agentic_response(query)
        
        # Simple concatenation as fallback
        text_parts = []
        for result in results[:2]:
            text = result.get('text', '').strip()
            if text:
                clean_text = text[:200] + "..." if len(text) > 200 else text
                text_parts.append(clean_text)
        
        if text_parts:
            combined = " ".join(text_parts)
            return f"Based on my knowledge, {combined}"
        else:
            return self._get_no_results_agentic_response(query)
    
    def clean_response(self, text: str, user_text: str) -> str:
        """Basic cleanup for voice output - main filtering done by prompt"""
        if not text:
            return ""
            
        # Remove any remaining user query echo
        text = text.replace(user_text, "").strip()
        
        # Basic cleanup only
        text = re.sub(r'\s+', ' ', text)  # Multiple spaces to single space
        text = text.strip()
        
        # Ensure response ends properly
        if text and not text.endswith(('?', '.', '!', ':')):
            text += "."
            
        return text

    # -------------------------
    # Text-to-speech + Send
    # -------------------------
    async def safe_send(self, ws: WebSocket, text: str, user_text: str = None):
        try:
            # Check if WebSocket is still open
            if ws.client_state.name != "CONNECTED":
                print(f"WebSocket not connected, state: {ws.client_state.name}")
                return
                
            tts = self.client.audio.speech.create(
                model="tts-1", voice="alloy", input=text
            )
            audio_stream = io.BytesIO(tts.read())
            audio_b64 = base64.b64encode(audio_stream.getvalue()).decode()

            # Double-check before sending
            if ws.client_state.name == "CONNECTED":
                response_data = {"bot_text": text, "audio": audio_b64}
                if user_text:
                    response_data["user_text"] = user_text
                await ws.send_json(response_data)
            else:
                print("WebSocket closed before sending audio response")
                
        except Exception as e:
            print(f"TTS/Send Error: {e}")
            # Only try to send error message if WebSocket is still connected
            try:
                if ws.client_state.name == "CONNECTED":
                    await ws.send_json({"bot_text": "I couldn't speak the response.", "audio": ""})
            except Exception as send_error:
                print(f"Failed to send error message: {send_error}")
