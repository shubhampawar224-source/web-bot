"""
Agentic RAG Search - Intelligent multi-step search with query refinement
Converts traditional RAG to agentic approach with iterative search strategies
"""

import os
from typing import List, Dict, Any, Optional
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class AgenticSearchAgent:
    """
    Intelligent search agent that:
    1. Analyzes user query and generates multiple search variations
    2. Performs iterative searches with different strategies
    3. Evaluates results quality and decides if re-search needed
    4. Synthesizes final answer from multiple search results
    """
    
    def __init__(self, vector_store, model: str = "gpt-4.1-preview"):
        self.vector_store = vector_store
        self.model = model
        self.max_iterations = 3
        self.min_confidence_score = 0.6
    
    async def search(
        self, 
        query: str, 
        firm_id: Optional[str] = None,
        n_results: int = 5
    ) -> Dict[str, Any]:
        """
        Agentic search with multi-step refinement
        
        Returns:
        {
            "final_results": [...],
            "search_iterations": [...],
            "confidence": 0.8,
            "strategy_used": "multi_query"
        }
        """
        
        search_history = []
        all_results = []
        
        # Step 1: Generate multiple search queries from user question
        search_queries = await self._generate_search_queries(query, firm_id)
        
        # Step 2: Execute searches iteratively
        for iteration, search_query in enumerate(search_queries):
            if iteration >= self.max_iterations:
                break
                
            # Perform vector search
            results = await self._execute_search(
                search_query, 
                firm_id, 
                n_results
            )
            
            search_history.append({
                "iteration": iteration + 1,
                "query": search_query,
                "results_found": len(results),
                "top_score": results[0].get("score", 0) if results else 0
            })
            
            all_results.extend(results)
            
            # Step 3: Evaluate if results are sufficient
            is_sufficient, confidence = await self._evaluate_results(
                query, 
                results
            )
            
            if is_sufficient and confidence >= self.min_confidence_score:
                break
        
        # Step 4: Deduplicate and rank results
        final_results = self._deduplicate_results(all_results)
        
        return {
            "final_results": final_results[:n_results],
            "search_iterations": search_history,
            "confidence": confidence,
            "total_queries_tried": len(search_queries),
            "strategy_used": "agentic_multi_query"
        }
    
    async def _generate_search_queries(
        self, 
        query: str, 
        firm_id: Optional[str]
    ) -> List[str]:
        """
        Dynamic query generation using LLM - handles any domain/topic automatically
        No need for static patterns, scales to any business type
        """
        
        # Enhanced prompt for better query expansion
        prompt = f"""You are an intelligent search query expander. Your job is to generate multiple search variations that will help find relevant information for the user's question.

User Question: "{query}"

Analyze the question and generate 5-7 search queries that:
1. Use different terminology and synonyms
2. Break down complex concepts into simpler terms  
3. Include related business/service terms
4. Cover formal and informal language
5. Account for how information might actually be stored on websites

IMPORTANT: Think about WHERE this information would typically appear:
- Contact pages, footer sections, about pages
- Service descriptions, FAQ sections
- Business information, hours pages

Examples:

User: "hours of operation"
- business hours
- opening closing times
- office hours schedule
- when are you open
- store hours
- operating schedule
- contact hours
- business schedule

User: "how much does it cost"
- pricing information
- fees and costs
- service rates
- consultation fees
- price list
- cost of services
- billing rates
- fee structure

User: "what services do you offer"
- services provided
- what we do
- our offerings
- practice areas
- service list
- business services
- specialties
- areas of expertise

User: "location and address"
- office location
- where are you located
- business address
- directions to office
- contact address
- office address
- find us

Generate for: "{query}"

Return ONLY the search queries, one per line, no explanations or numbering."""
        
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=300
            )
            
            queries_text = response.choices[0].message.content.strip()
            queries = [q.strip() for q in queries_text.split('\n') if q.strip() and not q.startswith('-')]
            
            # Clean queries (remove any numbering or bullet points)
            clean_queries = []
            for q in queries:
                cleaned = q.strip()
                # Remove numbering like "1.", "2)", etc.
                cleaned = re.sub(r'^\d+[\.\)]\s*', '', cleaned)
                # Remove bullet points
                cleaned = re.sub(r'^[-•*]\s*', '', cleaned)
                if cleaned and len(cleaned) > 3:
                    clean_queries.append(cleaned)
            
            # Always include original query as first
            if query not in clean_queries:
                clean_queries.insert(0, query)
            
            # Return max 7 queries for comprehensive coverage
            return clean_queries[:7]
            
        except Exception as e:
            print(f"Query generation failed: {e}")
            # Smart fallback based on query analysis
            return self._generate_fallback_queries(query)
    
    def _generate_fallback_queries(self, query: str) -> List[str]:
        """
        Smart fallback when LLM query generation fails
        Uses linguistic patterns to generate alternatives
        """
        import re
        
        base_queries = [query]
        query_lower = query.lower()
        
        # Common question patterns and their expansions
        patterns = {
            # Hours/timing related
            r'hour|time|open|close|schedule': [
                'business hours', 'contact hours', 'office schedule', 'operating times'
            ],
            # Cost/pricing related  
            r'cost|price|fee|charge|rate': [
                'pricing information', 'service fees', 'consultation cost', 'rates'
            ],
            # Services related
            r'service|offer|do|provide|help': [
                'services offered', 'what we do', 'our services', 'how we help'
            ],
            # Contact related
            r'contact|reach|call|phone|email': [
                'contact information', 'get in touch', 'reach us', 'contact details'
            ],
            # Location related
            r'where|location|address|find': [
                'office location', 'business address', 'where to find us', 'directions'
            ],
            # Process/procedure related
            r'how|process|procedure|steps': [
                'how it works', 'process steps', 'procedure', 'what to expect'
            ]
        }
        
        # Apply pattern matching
        for pattern, expansions in patterns.items():
            if re.search(pattern, query_lower):
                base_queries.extend(expansions[:3])  # Add top 3 expansions
                break
        
        # Add keyword-based variations
        keywords = [word for word in query.split() if len(word) > 3]
        if keywords:
            base_queries.append(' '.join(keywords))  # Just keywords
            base_queries.append(f"{keywords[0]} information")  # Main keyword + info
        
        return list(dict.fromkeys(base_queries))[:5]  # Remove duplicates, max 5
    
    async def _execute_search(
        self, 
        query: str, 
        firm_id: Optional[str],
        n_results: int
    ) -> List[Dict[str, Any]]:
        """
        Execute vector search using existing vector store
        Enhanced with multiple search strategies for deeper results
        """
        try:
            where_filter = {"firm_id": str(firm_id)} if firm_id else None
            
            # Strategy 1: Standard search
            results = self.vector_store.search(
                query_text=query,
                n_results=n_results,
                where=where_filter
            )
            
            formatted_results = []
            if results and "documents" in results:
                for idx, doc in enumerate(results["documents"]):
                    score = results.get("distances", [0])[idx] if results.get("distances") else 0
                    formatted_results.append({
                        "content": doc,
                        "metadata": results.get("metadatas", [{}])[idx],
                        "score": score,
                        "query_used": query,
                        "search_strategy": "standard"
                    })
            
            # Strategy 2: If few results, try broader search with individual keywords
            if len(formatted_results) < 3:
                keywords = query.split()
                for keyword in keywords:
                    if len(keyword) > 2:  # Skip very short words
                        keyword_results = self.vector_store.search(
                            query_text=keyword,
                            n_results=3,
                            where=where_filter
                        )
                        
                        if keyword_results and "documents" in keyword_results:
                            for idx, doc in enumerate(keyword_results["documents"]):
                                score = keyword_results.get("distances", [0.9])[idx]
                                # Add penalty for keyword-only search
                                score = score + 0.2  
                                formatted_results.append({
                                    "content": doc,
                                    "metadata": keyword_results.get("metadatas", [{}])[idx],
                                    "score": score,
                                    "query_used": keyword,
                                    "search_strategy": "keyword_expansion"
                                })
            
            # Strategy 3: For hours queries, try footer-specific search
            hours_keywords = ['hours', 'open', 'close', 'operation', 'schedule']
            if any(kw in query.lower() for kw in hours_keywords):
                footer_query = "footer contact hours phone address"
                footer_results = self.vector_store.search(
                    query_text=footer_query,
                    n_results=5,
                    where=where_filter
                )
                
                if footer_results and "documents" in footer_results:
                    for idx, doc in enumerate(footer_results["documents"]):
                        score = footer_results.get("distances", [0.8])[idx]
                        formatted_results.append({
                            "content": doc,
                            "metadata": footer_results.get("metadatas", [{}])[idx],
                            "score": score,
                            "query_used": footer_query,
                            "search_strategy": "footer_targeted"
                        })
            
            return formatted_results
            
        except Exception as e:
            print(f"Search execution failed: {e}")
            return []
    
    async def _evaluate_results(
        self, 
        original_query: str, 
        results: List[Dict[str, Any]]
    ) -> tuple[bool, float]:
        """
        Enhanced evaluation with content-aware scoring
        Returns (is_sufficient, confidence_score)
        """
        
        if not results:
            return False, 0.0
        
        # Content-based evaluation
        query_lower = original_query.lower()
        hours_keywords = ['hours', 'open', 'close', 'operation', 'schedule', 'timing']
        contact_keywords = ['contact', 'phone', 'email', 'address', 'call']
        
        is_hours_query = any(kw in query_lower for kw in hours_keywords)
        is_contact_query = any(kw in query_lower for kw in contact_keywords)
        
        # Check content quality
        content_scores = []
        for result in results[:5]:  # Check top 5 results
            content = result.get("content", "").lower()
            score = result.get("score", 1.0)
            
            content_quality = 0.0
            
            if is_hours_query:
                # Look for time patterns and schedule indicators
                time_patterns = ['am', 'pm', 'monday', 'tuesday', 'wednesday', 
                               'thursday', 'friday', 'saturday', 'sunday',
                               ':', '9', '10', '11', '12', 'open', 'close']
                matches = sum(1 for pattern in time_patterns if pattern in content)
                content_quality = min(matches / 10.0, 1.0)  # Normalize
                
                # Bonus for footer content
                if '[footer info]' in content or '[contact]' in content:
                    content_quality += 0.3
                    
            elif is_contact_query:
                # Look for contact information patterns
                contact_patterns = ['phone', 'email', '@', 'contact', 'call',
                                  'address', 'location', 'reach', 'get in touch']
                matches = sum(1 for pattern in contact_patterns if pattern in content)
                content_quality = min(matches / 8.0, 1.0)  # Normalize
                
            else:
                # General content evaluation
                query_words = query_lower.split()
                matches = sum(1 for word in query_words if word in content and len(word) > 2)
                content_quality = min(matches / len(query_words), 1.0) if query_words else 0.0
            
            # Combined score: vector similarity + content quality
            vector_score = max(0, 1.0 - score)  # Convert distance to similarity
            combined_score = (vector_score * 0.6) + (content_quality * 0.4)
            content_scores.append(combined_score)
        
        # Overall evaluation
        if not content_scores:
            return False, 0.0
            
        avg_score = sum(content_scores) / len(content_scores)
        max_score = max(content_scores)
        
        # Dynamic thresholds based on query type
        if is_hours_query or is_contact_query:
            sufficient_threshold = 0.4  # Lower threshold for specific queries
            confidence_threshold = 0.3
        else:
            sufficient_threshold = 0.6
            confidence_threshold = 0.5
        
        is_sufficient = (max_score >= sufficient_threshold and 
                        len([s for s in content_scores if s > confidence_threshold]) >= 2)
        
        confidence = min(avg_score + (max_score * 0.3), 1.0)
        
        return is_sufficient, confidence
    
    def _deduplicate_results(
        self, 
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Remove duplicate results based on content similarity
        """
        seen_contents = set()
        unique_results = []
        
        for result in results:
            content = result.get("content", "")
            # Simple deduplication: first 100 chars as fingerprint
            fingerprint = content[:100].strip()
            
            if fingerprint and fingerprint not in seen_contents:
                seen_contents.add(fingerprint)
                unique_results.append(result)
        
        # Sort by score (lower is better for distance metrics)
        unique_results.sort(key=lambda x: x.get("score", 999))
        
        return unique_results
    
    async def synthesize_answer(
        self,
        query: str,
        search_result: Dict[str, Any],
        system_prompt: str
    ) -> str:
        """
        Generate final answer using agentic search results
        """
        
        results = search_result["final_results"]
        confidence = search_result["confidence"]
        
        if not results:
            return "I couldn't find relevant information to answer your question. Could you please rephrase or provide more details?"
        
        # Combine all result contents
        context_parts = []
        for idx, result in enumerate(results[:5], 1):
            content = result.get("content", "")
            context_parts.append(f"[Source {idx}]\n{content}")
        
        context = "\n\n".join(context_parts)
        
        # Add search metadata to prompt
        search_info = f"""
Search Confidence: {confidence:.1%}
Queries Tried: {search_result['total_queries_tried']}
Results Found: {len(results)}
"""
        
        user_message = f"""{search_info}

Context from knowledge base:
{context}

User Question: {query}

Please provide a helpful answer based on the context above."""
        
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-preview",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=1000
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            print(f"Answer synthesis failed: {e}")
            return "I encountered an error generating the response. Please try again."


# Convenience function for easy integration
async def agentic_search_and_answer(
    query: str,
    vector_store,
    firm_id: Optional[str] = None,
    system_prompt: str = "You are a helpful AI assistant.",
    n_results: int = 5
) -> Dict[str, Any]:
    """
    One-shot agentic search + answer generation
    
    Returns:
    {
        "answer": "...",
        "search_details": {...},
        "confidence": 0.8
    }
    """
    
    agent = AgenticSearchAgent(vector_store)
    
    # Perform agentic search
    search_result = await agent.search(query, firm_id, n_results)
    
    # Generate answer
    answer = await agent.synthesize_answer(query, search_result, system_prompt)
    
    return {
        "answer": answer,
        "search_details": search_result,
        "confidence": search_result["confidence"],
        "sources_used": len(search_result["final_results"])
    }
