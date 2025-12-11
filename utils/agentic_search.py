import asyncio
from typing import List, Dict, Any, Optional

class AgenticSearchAgent:
    def __init__(self, vector_store, model: str = "gpt-4o"):
        self.vector_store = vector_store
        self.model = model

    async def search(self, query: str, firm_id: Optional[str] = None, n_results: int = 5) -> Dict[str, Any]:
        """
        Optimized High-Speed Search (<4s latency goal).
        """
        where_filter = {"firm_id": str(firm_id)} if firm_id else None
        
        # 1. Determine Search Strategies
        query_lower = query.lower()
        tasks = []

        # Strategy A: Standard Semantic Search (Always run)
        tasks.append(self._run_async_search(query, n_results, where_filter, "standard"))

        # Strategy B: Keyword Fallback (Dynamic Extraction)
        # Static keywords ('hours', 'contact') hata diye, ab dynamic hai
        keywords = " ".join([w for w in query.split() if len(w) > 4]) # Sirf bade words
        if keywords and keywords != query:
             tasks.append(self._run_async_search(keywords, 3, where_filter, "keyword_dynamic"))

        # 2. Execute all searches in PARALLEL
        search_results_list = await asyncio.gather(*tasks)

        # 3. Merge & Deduplicate
        final_results = self._merge_results(search_results_list)

        return {
            "final_results": final_results[:n_results],
            "confidence": 1.0 if final_results else 0.0,
            "total_queries_tried": len(tasks)
        }

    async def _run_async_search(self, query_str: str, n_results: int, where: dict, strategy: str):
        """Runs blocking vector store calls in a separate thread."""
        loop = asyncio.get_event_loop()
        try:
            # FIX: Adapting to different Vector Store signatures (query vs query_text)
            def safe_search():
                try:
                    # Try 'query' first (Common in FAISS/Custom wrappers)
                    return self.vector_store.search(query=query_str, n_results=n_results, where=where)
                except TypeError:
                    try:
                        # Try 'query_text' (Common in Chroma wrappers)
                        return self.vector_store.search(query_text=query_str, n_results=n_results, where=where)
                    except TypeError:
                        # Fallback: Positional Argument (Native FAISS often uses this)
                        # Assuming signature: search(query, k, filter)
                        return self.vector_store.search(query_str, n_results, where)

            results = await loop.run_in_executor(None, safe_search)
            return self._format_search_response(results, query_str, strategy)
            
        except Exception as e:
            print(f"⚠️ Search warning for {strategy}: {e}")
            return []

    def _format_search_response(self, results, query, strategy):
        """Standardizes vector store output"""
        formatted = []
        
        # Handle cases where result is None or empty
        if not results:
            return []

        # Adapting to different result formats (Chroma vs FAISS)
        documents = []
        metadatas = []
        distances = []

        if isinstance(results, dict):
            # ChromaDB Format
            if "documents" in results:
                documents = results["documents"]
                metadatas = results.get("metadatas", [])
                distances = results.get("distances", [])
        elif isinstance(results, list):
            # List of Documents Format (LangChain/FAISS)
            # Assuming list of objects with page_content and metadata
            for doc in results:
                if hasattr(doc, 'page_content'):
                    documents.append(doc.page_content)
                    metadatas.append(getattr(doc, 'metadata', {}))
                    distances.append(0.0) # Score might not be available directly
                else:
                    # Raw tuple or dict handling
                    documents.append(str(doc))
                    metadatas.append({})

        # Flatten list of lists (if batch format used)
        if documents and isinstance(documents[0], list):
            documents = documents[0]
            metadatas = metadatas[0] if metadatas else []
            distances = distances[0] if distances else []

        for i, doc in enumerate(documents):
            if doc:
                formatted.append({
                    "content": doc,
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "score": distances[i] if i < len(distances) else 0,
                    "search_strategy": strategy,
                    "query_used": query
                })
        return formatted

    def _merge_results(self, results_list: List[List[Dict]]) -> List[Dict]:
        """Merge and deduplicate results"""
        seen = set()
        merged = []
        all_res = [item for sublist in results_list for item in sublist]
        # Sort by score (assuming smaller is better, e.g. distance)
        all_res.sort(key=lambda x: x['score'])
        
        for res in all_res:
            # Create hash of content (first 50 chars)
            content_sig = res['content'][:50].strip()
            if content_sig and content_sig not in seen:
                seen.add(content_sig)
                merged.append(res)
        return merged