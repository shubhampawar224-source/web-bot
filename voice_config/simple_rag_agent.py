"""
Simple Enhanced RAG Agent - Clean and minimal approach with proper prompt engineering
"""

import os
import json
import time
import logging
import re
from typing import List, Dict, Any
from utils.vector_store import FAISSVectorStore
from openai import OpenAI
from dotenv import load_dotenv

# Load environment
load_dotenv(override=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedRAGAgent:
    """Simple enhanced RAG agent with better search and proper response formatting"""
    
    def __init__(self):
        try:
            self.vector_store = FAISSVectorStore()
            total_docs = len(self.vector_store.documents) if self.vector_store.documents else 0
            logger.info(f"RAG Agent ready - {total_docs} documents available")
            
            # Initialize OpenAI client for proper response generation
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                self.client = OpenAI(api_key=openai_key)
                self.use_ai_formatting = True
            else:
                self.client = None
                self.use_ai_formatting = False
                logger.warning("No OpenAI key found, using basic formatting")
                
        except Exception as e:
            logger.error(f"RAG Agent init error: {e}")
            self.vector_store = None
            self.client = None
    
    def search_and_respond(self, query: str) -> str:
        """Main search method with proper response formatting"""
        try:
            if not self.vector_store or not query:
                return "Sorry, I can't search right now. Please try again."
            
            # Search with multiple approaches
            results = self._smart_search(query)
            
            if not results:
                return f"I don't have information about '{query}'. Try asking about legal services, law firms, or contact details."
            
            # Advanced response formatting with AI
            if self.use_ai_formatting:
                return self._generate_ai_response(query, results)
            else:
                return self._format_basic_response(query, results)
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return "I encountered an error. Please try rephrasing your question."
    
    def _smart_search(self, query: str) -> List[Dict[str, Any]]:
        """Enhanced search with keyword expansion"""
        all_results = []
        
        # Direct search
        results1 = self.vector_store.search(query=query, n_results=10)
        all_results.extend(results1)
        
        # Keyword expansion
        keywords = self._get_keywords(query)
        for keyword in keywords[:2]:  # Only top 2
            results2 = self.vector_store.search(query=keyword, n_results=5)
            all_results.extend(results2)
        
        # Remove duplicates and filter
        unique_results = []
        seen_texts = set()
        
        for result in all_results:
            text = result.get('text', '')[:100]  # First 100 chars for comparison
            if text not in seen_texts and result.get('score', 0) > 0.2:
                seen_texts.add(text)
                unique_results.append(result)
        
        # Sort by score
        unique_results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return unique_results[:5]  # Top 5 results
    
    def _get_keywords(self, query: str) -> List[str]:
        """Simple keyword expansion"""
        keywords = []
        q = query.lower()
        
        if 'law' in q or 'legal' in q:
            keywords.extend(['legal services', 'attorneys', 'law firm'])
        if 'service' in q or 'help' in q:
            keywords.extend(['services', 'practice areas'])
        if 'about' in q or 'who' in q:
            keywords.extend(['about us', 'company'])
        if 'contact' in q:
            keywords.extend(['contact', 'email','phone', 'address'])
            
        return keywords
    
    def _generate_ai_response(self, query: str, results: List[Dict[str, Any]]) -> str:
        """Generate proper AI response using OpenAI"""
        try:
            # Clean and prepare context from search results
            context_parts = []
            for result in results[:3]:  # Top 3 results
                text = self._clean_content(result.get('text', ''))
                if text and len(text.strip()) > 30:
                    context_parts.append(text)
            
            if not context_parts:
                return "I found some information but couldn't process it properly. Please try rephrasing your question."
            
            context = "\n\n".join(context_parts)
            
            # Create proper prompt for voice response
            prompt = f"""You are a helpful voice assistant. Based on the provided context, answer the user's question in a natural, conversational way suitable for voice output.

IMPORTANT GUIDELINES:
- Provide a direct, helpful answer
- Use natural, conversational language 
- Keep response concise but informative (under 200 words)
- DO NOT mention URLs, website links, or technical details
- DO NOT say "according to the context" or "based on the provided information"
- Speak as if you naturally know this information
- If the context doesn't fully answer the question, provide what information is available

User Question: {query}

Context Information:
{context}

Voice Response:"""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"AI response generation error: {e}")
            return self._format_basic_response(query, results)
    
    def _clean_content(self, text: str) -> str:
        """Clean content by removing URLs and unwanted elements"""
        if not text:
            return ""
        
        # Remove URLs
        text = re.sub(r'http[s]?://\S+', '', text)
        text = re.sub(r'www\.\S+', '', text)
        
        # Remove email addresses
        text = re.sub(r'\S+@\S+\.\S+', '', text)
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        
        # Remove technical markers and brackets
        text = re.sub(r'\[[^\]]+\]', '', text)
        text = re.sub(r'\([^)]*http[^)]*\)', '', text)  # Remove parentheses with URLs
        
        # Clean up extra whitespace
        text = ' '.join(text.split())
        
        # Remove very short fragments
        if len(text.strip()) < 20:
            return ""
        
        return text.strip()
    
    def _format_basic_response(self, query: str, results: List[Dict[str, Any]]) -> str:
        """Basic response formatting fallback"""
        texts = []
        for result in results[:2]:  # Top 2 results
            text = self._clean_content(result.get('text', ''))
            if text:
                texts.append(text[:300])  # Limit length
        
        if not texts:
            return "I found some information but couldn't format it properly."
        
        if len(texts) == 1:
            return f"Based on my knowledge, {texts[0]}"
        else:
            return f"Here's what I can tell you: {texts[0]} Additionally, {texts[1]}"
    
    def _format_response(self, query: str, results: List[Dict[str, Any]]) -> str:
        """Legacy method - now uses _format_basic_response"""
        return self._format_basic_response(query, results)
    
    def get_stats(self) -> Dict[str, Any]:
        """Simple stats"""
        if not self.vector_store:
            return {"error": "Not available"}
        
        total_docs = len(self.vector_store.documents) if self.vector_store.documents else 0
        total_vectors = self.vector_store.index.ntotal if self.vector_store.index else 0
        
        return {
            "documents": total_docs,
            "vectors": total_vectors,
            "status": "active" if total_docs > 0 else "empty"
        }

# Simple utility functions
def quick_search(query: str) -> str:
    """Quick search utility function"""
    agent = EnhancedRAGAgent()
    return agent.search_and_respond(query)