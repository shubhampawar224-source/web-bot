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
        Use LLM to generate multiple search query variations
        Expands fuzzy questions into specific searchable terms
        """
        
        prompt = f"""You are a search query optimizer. Given a user question, generate 3-5 different search queries that could help find the answer.

User Question: "{query}"

Generate queries that:
1. Extract key entities and concepts
2. Expand abbreviations and fuzzy terms
3. Include related keywords
4. Use different phrasings

Return ONLY the queries, one per line, no numbering or explanation.

Examples:
User: "hours and operations"
- business hours
- opening hours and closing time
- operating hours and schedule
- office hours contact information
- when are you open

User: "how to contact"
- contact information
- phone number email address
- reach out to us
- customer service contact
- get in touch

Now generate for: "{query}"
"""
        
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=200
            )
            
            queries_text = response.choices[0].message.content.strip()
            queries = [q.strip() for q in queries_text.split('\n') if q.strip()]
            
            # Always include original query as first
            if query not in queries:
                queries.insert(0, query)
            
            return queries[:5]  # Max 5 queries
            
        except Exception as e:
            print(f"Query generation failed: {e}")
            # Fallback: return original query
            return [query]
    
    async def _execute_search(
        self, 
        query: str, 
        firm_id: Optional[str],
        n_results: int
    ) -> List[Dict[str, Any]]:
        """
        Execute vector search using existing vector store
        """
        try:
            where_filter = {"firm_id": str(firm_id)} if firm_id else None
            
            results = self.vector_store.search(
                query_text=query,
                n_results=n_results,
                where=where_filter
            )
            
            # Convert to standardized format
            formatted_results = []
            if results and "documents" in results:
                for idx, doc in enumerate(results["documents"]):
                    formatted_results.append({
                        "content": doc,
                        "metadata": results.get("metadatas", [{}])[idx],
                        "score": results.get("distances", [0])[idx],
                        "query_used": query
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
        LLM evaluates if search results are sufficient to answer the query
        Returns (is_sufficient, confidence_score)
        """
        
        if not results:
            return False, 0.0
        
        # Quick heuristic: if we have results with good scores
        top_score = results[0].get("score", 1.0)
        
        # Lower distance = better match in vector search
        if top_score < 0.5:  # Good match
            return True, 0.9
        elif top_score < 0.8:  # Decent match
            return True, 0.7
        elif len(results) >= 3:  # Multiple results found
            return True, 0.6
        else:
            return False, 0.3
    
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
