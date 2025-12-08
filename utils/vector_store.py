# utils/vector_store.py

import os
import pickle
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime

# ---------------- FAISS Setup ----------------
PERSIST_DIR = "rag_db_faiss"
os.makedirs(PERSIST_DIR, exist_ok=True)

# File paths for persisting FAISS data
INDEX_FILE = os.path.join(PERSIST_DIR, "faiss_index.bin")
METADATA_FILE = os.path.join(PERSIST_DIR, "metadata.json")
DOCUMENTS_FILE = os.path.join(PERSIST_DIR, "documents.json")

# ---------------- Embedding Model ----------------
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
EMBEDDING_DIM = 384  # Dimension for paraphrase-multilingual-MiniLM-L12-v2

class FAISSVectorStore:
    def __init__(self):
        self.index = None
        self.metadata = {}  # id -> metadata mapping
        self.documents = {}  # id -> document text mapping
        self.id_to_index = {}  # document_id -> faiss_index mapping
        self.index_to_id = {}  # faiss_index -> document_id mapping
        self.next_index = 0
        
        self.load_or_create_index()
    
    def load_or_create_index(self):
        """Load existing FAISS index or create a new one"""
        try:
            if os.path.exists(INDEX_FILE) and os.path.exists(METADATA_FILE) and os.path.exists(DOCUMENTS_FILE):
                # Load existing index
                self.index = faiss.read_index(INDEX_FILE)
                
                # Load metadata
                with open(METADATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    raw_metadata = data.get('metadata', {})
                    
                    # Expand optimized metadata
                    self.metadata = self._expand_optimized_metadata(raw_metadata)
                    
                    self.id_to_index = data.get('id_to_index', {})
                    self.index_to_id = data.get('index_to_id', {})
                    self.next_index = data.get('next_index', 0)
                
                # Load documents
                with open(DOCUMENTS_FILE, 'r', encoding='utf-8') as f:
                    self.documents = json.load(f)
                
                print(f"[FAISSVectorStore] Loaded existing index with {self.index.ntotal} vectors")
            else:
                # Create new index
                self.index = faiss.IndexFlatIP(EMBEDDING_DIM)  # Inner product for similarity
                print(f"[FAISSVectorStore] Created new FAISS index")
                
        except Exception as e:
            print(f"[FAISSVectorStore] Error loading index: {e}")
            # Create new index if loading fails
            self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
            self.metadata = {}
            self.documents = {}
            self.id_to_index = {}
            self.index_to_id = {}
            self.next_index = 0
    
    def save_index(self):
        """Save FAISS index and metadata to disk with automatic deduplication"""
        try:
            # Save FAISS index
            faiss.write_index(self.index, INDEX_FILE)
            
            # Optimize metadata before saving
            optimized_metadata = self._optimize_metadata_for_storage()
            
            # Save metadata and mappings
            metadata_data = {
                'metadata': optimized_metadata,
                'id_to_index': self.id_to_index,
                'index_to_id': self.index_to_id,
                'next_index': self.next_index
            }
            with open(METADATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(metadata_data, f, ensure_ascii=False)
            
            # Save documents
            with open(DOCUMENTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.documents, f, ensure_ascii=False)
                
            print(f"[FAISSVectorStore] Saved optimized index with {self.index.ntotal} vectors")
            
        except Exception as e:
            print(f"[FAISSVectorStore] Error saving index: {e}")
    
    def _optimize_metadata_for_storage(self):
        """Create storage-optimized metadata that reduces duplication"""
        if not self.metadata:
            return {}
        
        # Group metadata by URL to find patterns, filter out corrupted entries
        url_groups = {}
        for doc_id, meta in self.metadata.items():
            # Skip corrupted metadata entries
            if not isinstance(meta, dict):
                print(f"[WARNING] Skipping corrupted metadata in storage optimization: {doc_id}")
                continue
                
            url = meta.get('url', 'unknown')
            if url not in url_groups:
                url_groups[url] = []
            url_groups[url].append((doc_id, meta))
        
        # Check if we can use references for common metadata
        optimized = {}
        url_templates = {}
        
        for url, doc_list in url_groups.items():
            if len(doc_list) > 1:  # Multiple chunks from same URL
                # Use first document as template
                template = doc_list[0][1]
                template_key = f"_template_{url.replace('://', '_').replace('/', '_').replace('.', '_')}"
                url_templates[template_key] = template
                
                # Reference the template for all chunks
                for doc_id, meta in doc_list:
                    # Safety check before comparison
                    if not isinstance(meta, dict) or not isinstance(template, dict):
                        optimized[doc_id] = meta  # Store as-is if corrupted
                        continue
                        
                    # Check if metadata is identical to template
                    if meta == template:
                        optimized[doc_id] = f"@ref:{template_key}"
                    else:
                        # Store differences only
                        diff = {k: v for k, v in meta.items() if template.get(k) != v}
                        if diff:
                            optimized[doc_id] = {**diff, "_ref": template_key}
                        else:
                            optimized[doc_id] = f"@ref:{template_key}"
            else:
                # Single chunk, store normally
                optimized[doc_list[0][0]] = doc_list[0][1]
        
        # Add templates to the optimized metadata
        optimized.update(url_templates)
        
        # Calculate savings
        original_size = len(json.dumps(self.metadata).encode('utf-8'))
        optimized_size = len(json.dumps(optimized).encode('utf-8'))
        
        if original_size > optimized_size:
            reduction = ((original_size - optimized_size) / original_size) * 100
            print(f"[FAISSVectorStore] Metadata optimized: {reduction:.1f}% reduction ({original_size:,} → {optimized_size:,} bytes)")
        
        return optimized
    
    def _expand_optimized_metadata(self, raw_metadata):
        """Expand optimized metadata back to full format"""
        if not raw_metadata:
            return {}
        
        # Find templates (keys starting with _template_)
        templates = {k: v for k, v in raw_metadata.items() if k.startswith('_template_')}
        
        # Expand references
        expanded = {}
        for doc_id, meta_value in raw_metadata.items():
            if doc_id.startswith('_template_'):
                continue  # Skip templates
            
            if isinstance(meta_value, str) and meta_value.startswith('@ref:'):
                # Direct reference to template
                template_key = meta_value[5:]  # Remove '@ref:' prefix
                if template_key in templates:
                    expanded[doc_id] = templates[template_key].copy()
            elif isinstance(meta_value, dict) and '_ref' in meta_value:
                # Partial reference with differences
                template_key = meta_value['_ref']
                if template_key in templates:
                    expanded_meta = templates[template_key].copy()
                    # Apply differences
                    for k, v in meta_value.items():
                        if k != '_ref':
                            expanded_meta[k] = v
                    expanded[doc_id] = expanded_meta
            else:
                # Regular metadata
                expanded[doc_id] = meta_value
        
        return expanded
    
    def add_documents(self, texts: List[str], metadatas: List[Dict[str, Any]], ids: Optional[List[str]] = None):
        """Add documents to the FAISS index"""
        if not texts:
            return
        
        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in texts]
        
        # Generate embeddings
        embeddings = embedding_model.encode(texts)
        
        # Normalize embeddings for cosine similarity
        faiss.normalize_L2(embeddings)
        
        # Add to FAISS index
        self.index.add(embeddings)
        
        # Update mappings and metadata
        for i, (text, metadata, doc_id) in enumerate(zip(texts, metadatas, ids)):
            faiss_idx = self.next_index + i
            
            self.id_to_index[doc_id] = faiss_idx
            self.index_to_id[str(faiss_idx)] = doc_id
            self.metadata[doc_id] = metadata
            self.documents[doc_id] = text
        
        self.next_index += len(texts)
        
        # Save to disk
        self.save_index()
        
        print(f"[FAISSVectorStore] Added {len(texts)} documents. Total: {self.index.ntotal}")
    
    def _matches_complex_filter(self, metadata: Dict[str, Any], filter_metadata: Dict[str, Any]) -> bool:
        """Handle complex metadata filtering including $and and $in operators"""
        if not filter_metadata:
            return True
        
        # Safety check: ensure metadata is a dictionary
        if not isinstance(metadata, dict):
            return False
            
        # Handle $and operator
        if "$and" in filter_metadata:
            conditions = filter_metadata["$and"]
            for condition in conditions:
                if not self._matches_complex_filter(metadata, condition):
                    return False
            return True
        
        # Handle regular key-value pairs
        for key, value in filter_metadata.items():
            if key.startswith("$"):
                continue  # Skip operator keys
                
            if isinstance(value, dict) and "$in" in value:
                # Handle $in operator
                if metadata.get(key) not in value["$in"]:
                    return False
            else:
                # Simple equality check
                if metadata.get(key) != value:
                    return False
        
        return True

    def search(self, query: str, n_results: int = 10, filter_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search for similar documents"""
        if self.index.ntotal == 0:
            return []
        
        # Generate query embedding
        query_embedding = embedding_model.encode([query])
        faiss.normalize_L2(query_embedding)
        
        # Search in FAISS
        scores, indices = self.index.search(query_embedding, min(n_results * 2, self.index.ntotal))  # Get more results for filtering
        
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:  # Invalid index
                continue
                
            doc_id = self.index_to_id.get(str(idx))
            if not doc_id:
                continue
            
            metadata = self.metadata.get(doc_id, {})
            document = self.documents.get(doc_id, "")
            
            # Safety check: ensure metadata is a dictionary
            if not isinstance(metadata, dict):
                print(f"[WARNING] Corrupted metadata for doc {doc_id}: {repr(metadata)}, skipping...")
                continue
            
            # Apply metadata filter if provided
            if filter_metadata:
                if not self._matches_complex_filter(metadata, filter_metadata):
                    continue
            
            results.append({
                "text": document,
                "metadata": metadata,
                "id": doc_id,
                "score": float(score)
            })
            
            if len(results) >= n_results:
                break
        
        return results
    
    def delete_by_ids(self, ids: List[str]) -> int:
        """Delete documents by their IDs"""
        if not ids:
            return 0
        
        deleted_count = 0
        indices_to_remove = []
        
        for doc_id in ids:
            if doc_id in self.id_to_index:
                faiss_idx = self.id_to_index[doc_id]
                indices_to_remove.append(faiss_idx)
                
                # Remove from mappings
                del self.id_to_index[doc_id]
                del self.index_to_id[str(faiss_idx)]
                del self.metadata[doc_id]
                del self.documents[doc_id]
                deleted_count += 1
        
        if indices_to_remove:
            # FAISS doesn't support direct deletion, so we need to rebuild the index
            self._rebuild_index_without_indices(indices_to_remove)
            self.save_index()
        
        print(f"[FAISSVectorStore] Deleted {deleted_count} documents")
        return deleted_count
    
    def delete_by_metadata(self, filter_metadata: Dict[str, Any]) -> int:
        """Delete documents that match metadata filter"""
        ids_to_delete = []
        
        for doc_id, metadata in self.metadata.items():
            if all(metadata.get(k) == v for k, v in filter_metadata.items()):
                ids_to_delete.append(doc_id)
        
        return self.delete_by_ids(ids_to_delete)
    
    def _rebuild_index_without_indices(self, indices_to_remove: List[int]):
        """Rebuild FAISS index without specified indices"""
        if not indices_to_remove:
            return
        
        # Get all vectors except the ones to remove
        all_vectors = []
        new_id_to_index = {}
        new_index_to_id = {}
        new_next_index = 0
        
        for old_idx in range(self.index.ntotal):
            if old_idx not in indices_to_remove:
                # Get the vector
                vector = self.index.reconstruct(old_idx)
                all_vectors.append(vector)
                
                # Update mappings
                doc_id = self.index_to_id.get(str(old_idx))
                if doc_id:
                    new_id_to_index[doc_id] = new_next_index
                    new_index_to_id[str(new_next_index)] = doc_id
                    new_next_index += 1
        
        # Create new index
        if all_vectors:
            vectors_array = np.array(all_vectors)
            self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
            self.index.add(vectors_array)
        else:
            self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
        
        # Update mappings
        self.id_to_index = new_id_to_index
        self.index_to_id = new_index_to_id
        self.next_index = new_next_index
    
    def get_documents_by_metadata(self, filter_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Get documents that match metadata filter"""
        matched_ids = []
        matched_documents = []
        matched_metadatas = []
        
        for doc_id, metadata in self.metadata.items():
            if all(metadata.get(k) == v for k, v in filter_metadata.items()):
                matched_ids.append(doc_id)
                matched_documents.append(self.documents.get(doc_id, ""))
                matched_metadatas.append(metadata)
        
        return {
            "ids": matched_ids,
            "documents": matched_documents,
            "metadatas": matched_metadatas
        }

    def query(self, query_embeddings: List[List[float]] = None, query_texts: List[str] = None, 
              n_results: int = 10, where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        ChromaDB-compatible query method for backward compatibility
        """
        if query_texts:
            query = query_texts[0]  # Use first query text
        elif query_embeddings:
            # Convert embedding back to text (this is a limitation, but for compatibility)
            query = ""  # We'll search with empty query, filtered by metadata
        else:
            return {"documents": [[]], "metadatas": [[]], "ids": [[]]}
        
        results = self.search(query=query, n_results=n_results, filter_metadata=where)
        
        # Convert to ChromaDB format
        documents = []
        metadatas = []
        ids = []
        
        for result in results:
            documents.append(result["text"])
            metadatas.append(result["metadata"])
            ids.append(result["id"])
        
        return {
            "documents": [documents],
            "metadatas": [metadatas],
            "ids": [ids]
        }
    
    def get(self, ids: Optional[List[str]] = None, where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        ChromaDB-compatible get method for backward compatibility
        """
        if ids:
            # Get specific documents by IDs
            documents = []
            metadatas = []
            result_ids = []
            
            for doc_id in ids:
                if doc_id in self.documents:
                    documents.append(self.documents[doc_id])
                    metadatas.append(self.metadata[doc_id])
                    result_ids.append(doc_id)
            
            return {
                "documents": documents,
                "metadatas": metadatas,
                "ids": result_ids
            }
        
        elif where:
            # Get documents by metadata filter
            return self.get_documents_by_metadata(where)
        
        else:
            # Get all documents
            return {
                "documents": list(self.documents.values()),
                "metadatas": list(self.metadata.values()),
                "ids": list(self.documents.keys())
            }

    def add(self, ids: List[str], embeddings: List[List[float]], documents: List[str], metadatas: List[Dict[str, Any]]):
        """
        ChromaDB-compatible add method for backward compatibility
        """
        self.add_documents(texts=documents, metadatas=metadatas, ids=ids)

    def delete(self, ids: List[str]):
        """
        ChromaDB-compatible delete method for backward compatibility
        """
        self.delete_by_ids(ids)

# Global instance
vector_store = FAISSVectorStore()

# ---------------- Helper: Chunk Text ----------------
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50):
    """
    Splits long text into overlapping chunks for vector embedding.
    """
    words = text.split()
    chunks = []
    for i in range(0, len(words), chunk_size - overlap):
        chunk = " ".join(words[i:i + chunk_size])
        chunks.append(chunk)
    return chunks

# ---------------- Helper: Add Document (Optimized) ----------------
def add_text_chunks_to_collection(chunks, metadata: dict):
    """
    Takes text chunks and metadata → stores in FAISS vector store.
    Optimized version that avoids duplicating metadata for chunks from the same URL.
    """
    if not chunks:
        print(f"[VectorStore] No chunks to add for {metadata.get('url')}")
        return
    
    batch_size = 50  # Process in batches to avoid memory issues
    total_chunks = len(chunks)
    
    # Extract common metadata that will be identical for all chunks
    url = metadata.get('url', 'unknown')
    common_metadata = {
        'type': metadata.get('type'),
        'url': url,
        'firm_name': metadata.get('firm_name'),
        'user_id': metadata.get('user_id'),
        'user_email': metadata.get('user_email'),
        'description': metadata.get('description'),
        'request_id': metadata.get('request_id')
    }
    
    for batch_start in range(0, total_chunks, batch_size):
        batch_end = min(batch_start + batch_size, total_chunks)
        batch_chunks = chunks[batch_start:batch_end]
        
        # Prepare batch data with minimal metadata
        batch_ids = []
        batch_metadatas = []
        
        for i, chunk in enumerate(batch_chunks):
            chunk_index = batch_start + i
            doc_id = f"{url}_chunk_{chunk_index}"
            batch_ids.append(doc_id)
            
            # Use the common metadata for all chunks (no duplication)
            batch_metadatas.append(common_metadata.copy())
        
        # Add batch to vector store
        vector_store.add_documents(
            texts=batch_chunks,
            metadatas=batch_metadatas,
            ids=batch_ids
        )
        
        print(f"[VectorStore] Added batch {batch_start + 1}-{batch_end} of {total_chunks} chunks for {url}")

    print(f"[VectorStore] Completed adding {total_chunks} chunks for {url}")
    print(f"[VectorStore] Metadata optimization: Single template used for all {total_chunks} chunks")
# ---------------- Helper: Delete Documents by URL ----------------
def delete_documents_by_url(url: str):
    """
    Delete all documents/chunks from FAISS vector store for a specific URL.
    
    Args:
        url (str): The URL to delete documents for
    
    Returns:
        int: Number of documents deleted
    """
    try:
        deleted_count = vector_store.delete_by_metadata({"url": url})
        print(f"[VectorStore] Deleted {deleted_count} documents for URL: {url}")
        return deleted_count
            
    except Exception as e:
        print(f"[VectorStore] Error deleting documents for URL {url}: {e}")
        return 0

def delete_documents_by_ids(doc_ids: list):
    """
    Delete specific documents from FAISS vector store by their IDs.
    
    Args:
        doc_ids (list): List of document IDs to delete
    
    Returns:
        int: Number of documents deleted
    """
    try:
        deleted_count = vector_store.delete_by_ids(doc_ids)
        print(f"[VectorStore] Deleted {deleted_count} documents by IDs")
        return deleted_count
    except Exception as e:
        print(f"[VectorStore] Error deleting documents by IDs: {e}")
        return 0

def get_all_documents_by_url(url: str):
    """
    Get all document IDs and metadata for a specific URL.
    
    Args:
        url (str): The URL to search for
    
    Returns:
        dict: Documents data including IDs, documents, and metadata
    """
    try:
        results = vector_store.get_documents_by_metadata({"url": url})
        return results
    except Exception as e:
        print(f"[VectorStore] Error getting documents for URL {url}: {e}")
        return {"ids": [], "documents": [], "metadatas": []}

# Legacy compatibility - for direct collection access
collection = vector_store
