"""
Semantic search engine for DAML resources using ChromaDB.

This module provides fast, accurate semantic similarity search over ALL DAML resources
(examples, docs, patterns, anti-patterns, tests). ChromaDB finds semantically similar
files based on code structure and content. The LLM then reasons about which files
demonstrate anti-patterns, good practices, or other relevant information.

Architecture:
- ChromaDB: Fast semantic search (finds similar files)
- LLM: Deep reasoning (determines relevance and patterns)
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.warning("ChromaDB not available - install with: pip install chromadb")


class DAMLSemanticSearch:
    """
    Semantic search engine for DAML resources using ChromaDB.
    
    Indexes ALL resources (examples, docs, patterns, anti-patterns, tests) and finds
    semantically similar files for any given code snippet. Does NOT determine what is
    an anti-pattern - that's the LLM's job. This class only provides fast similarity search.
    
    Flow:
    1. Index all ~10,000+ DAML files (one-time, ~5-10 min)
    2. Query with user's code → get top 10 similar files (50ms)
    3. LLM receives similar files → reasons about relevance
    """
    
    def __init__(
        self,
        collection_name: str = "daml_resources",
        persist_directory: Optional[str] = None,
        embedding_function: Optional[Any] = None,
    ):
        """
        Initialize the semantic search engine for ALL DAML resources.
        
        Args:
            collection_name: Name of the ChromaDB collection (default kept for compatibility)
            persist_directory: Directory to persist the database (defaults to .chroma_db)
            embedding_function: Custom embedding function (defaults to sentence-transformers)
        
        Note: Indexes ALL resources, not just anti-patterns. LLM does the reasoning.
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError("ChromaDB is required for semantic search. Install with: pip install chromadb")
        
        self.collection_name = collection_name
        
        # Set up persist directory
        if persist_directory is None:
            persist_directory = str(Path.cwd() / ".chroma_db")
        
        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "DAML semantic search - all resources (examples, docs, patterns)"},
            embedding_function=embedding_function,
        )
        
        logger.info(f"✅ ChromaDB collection '{collection_name}' initialized ({self.collection.count()} items)")
    
    def index_resources(
        self,
        raw_resources: List[Dict[str, Any]],
        force_reindex: bool = False,
    ) -> int:
        """
        Index ALL resources into ChromaDB for semantic search.
        
        Indexes everything: examples, docs, patterns, anti-patterns, tests.
        ChromaDB finds semantically similar files, LLM reasons about relevance.
        
        Uses raw file content directly - no enrichment required.
        ChromaDB's embedding model handles semantic understanding.
        
        Args:
            raw_resources: List of raw resource dictionaries (ALL files, not filtered)
            force_reindex: If True, clear existing index and rebuild from scratch
        
        Returns:
            Number of resources indexed
        """
        # Index ALL resources (not just anti-patterns!)
        # Let ChromaDB find similar files, let LLM reason about relevance
        resources_to_index = []
        for resource in raw_resources:
            # Skip empty files
            content = resource.get("content", "")
            if not content or len(content.strip()) < 10:
                continue
            
            # Skip non-DAML files (e.g., configs, build files)
            file_path = resource.get("file_path", "").lower()
            if file_path.endswith((".md", ".daml", ".scala", ".java", ".hs")):
                resources_to_index.append(resource)
        
        if not resources_to_index:
            logger.warning("No resources found to index")
            return 0
        
        # Check if we need to reindex
        current_count = self.collection.count()
        expected_count = len(resources_to_index)
        
        # Allow small differences (duplicates, failed indexing, etc.)
        # If within 1% or 50 items, consider it up-to-date
        count_diff = abs(current_count - expected_count)
        tolerance = max(50, int(expected_count * 0.01))
        
        if not force_reindex and count_diff <= tolerance:
            logger.info(f"✅ Index up-to-date ({current_count} resources, diff: {count_diff})")
            return current_count
        
        # Clear existing index if forcing reindex
        if force_reindex and current_count > 0:
            logger.info(f"🔄 Clearing existing index ({current_count} items)")
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "DAML semantic search (all resources)"},
            )
        
        # Prepare documents for indexing
        documents = []
        metadatas = []
        ids = []
        
        for resource in resources_to_index:
            # Use RAW content for embedding (no enrichment needed)
            content = resource.get("content", "")
            
            # Sample first 2000 chars for embedding (capture more context)
            # Increased from 1000 to avoid similar imports causing identical embeddings
            searchable_text = content[:2000] if len(content) > 2000 else content
            
            # Fallback to description if no content
            if not searchable_text.strip():
                searchable_text = resource.get("description", "No description available")
            
            # Create unique ID based on file path (more unique than name alone)
            name = resource.get("name", "")
            file_path_val = resource.get("file_path", "")
            
            # Use full file path for ID to ensure uniqueness
            resource_id = file_path_val.replace("/", "-").replace(".", "-") if file_path_val else name.replace(" ", "-")
            
            # Add hash suffix if ID is too short (ensure uniqueness)
            if len(resource_id) < 10:
                import hashlib
                hash_suffix = hashlib.md5(file_path_val.encode()).hexdigest()[:8]
                resource_id = f"{resource_id}-{hash_suffix}"
            
            # Store minimal metadata for retrieval (no synthetic summaries)
            metadata = {
                "name": name,
                "file_path": file_path_val,
                "description": resource.get("description", "")[:500],  # Truncate for storage
            }
            
            documents.append(searchable_text)
            metadatas.append(metadata)
            ids.append(resource_id)
        
        # Index into ChromaDB
        logger.info(f"🔄 Indexing {len(documents)} resources into ChromaDB...")
        
        # ChromaDB has a limit on batch size, so we chunk if needed
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i+batch_size]
            batch_meta = metadatas[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            
            self.collection.add(
                documents=batch_docs,
                metadatas=batch_meta,
                ids=batch_ids,
            )
        
        indexed_count = self.collection.count()
        
        # Diagnostic: Show sample of what was indexed
        if documents:
            sample_doc = documents[0][:150].replace("\n", " ").strip()
            logger.info(f"✅ Indexed {indexed_count} resources into ChromaDB")
            logger.debug(f"Sample indexed content: '{sample_doc}...'")
        else:
            logger.info(f"✅ Indexed {indexed_count} resources into ChromaDB")
        
        return indexed_count
    
    def search_similar_files(
        self,
        code: str,
        top_k: int = 5,
        raw_resources: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for semantically similar files for the given code.
        
        Finds files with similar structure/content to the user's code. Does NOT filter
        for anti-patterns - returns ALL similar files (examples, docs, patterns, etc).
        The LLM then reasons about which are relevant/problematic.
        
        Args:
            code: DAML code to find similar files for
            top_k: Number of most similar files to return (default 5, often 10)
            raw_resources: Optional full resource list to return complete resources
        
        Returns:
            List of resource dictionaries ranked by semantic similarity (cosine distance)
        """
        if self.collection.count() == 0:
            logger.warning("⚠️ No resources indexed - returning empty results")
            return []
        
        # Diagnostic: Log what we're searching for
        import hashlib
        code_hash = hashlib.md5(code.encode()).hexdigest()[:8]
        code_preview = code[:100].replace("\n", " ").strip()
        logger.info(f"🔍 Searching ChromaDB with code (hash: {code_hash}, preview: '{code_preview}...')")
        
        # Query ChromaDB with the code as the search query
        # Note: ChromaDB does NOT cache queries - each call generates new embeddings
        import time
        start_time = time.time()
        results = self.collection.query(
            query_texts=[code],
            n_results=min(top_k, self.collection.count()),
        )
        query_time_ms = (time.time() - start_time) * 1000
        logger.debug(f"ChromaDB query took {query_time_ms:.1f}ms")
        
        # Extract results
        if not results or not results.get("ids") or not results["ids"][0]:
            logger.warning("⚠️ No similar files found")
            return []
        
        result_ids = results["ids"][0]
        result_metadatas = results["metadatas"][0]
        result_distances = results["distances"][0] if "distances" in results else [0.0] * len(result_ids)
        
        # Diagnostic: Log ALL similarity scores to debug "same results" issue
        all_similarities = "\n".join([
            f"  {i+1}. {metadata.get('name', 'unknown')[:40]:<40} similarity={1.0-dist:.3f} distance={dist:.3f}"
            for i, (metadata, dist) in enumerate(zip(result_metadatas, result_distances))
        ])
        logger.info(f"🔍 Found {len(result_ids)} semantically similar files via ChromaDB:\n{all_similarities}")
        
        # If raw_resources provided, return full resources
        if raw_resources:
            relevant_resources = []
            for result_id, metadata, distance in zip(result_ids, result_metadatas, result_distances):
                name = metadata.get("name", "")
                file_path = metadata.get("file_path", "")
                
                # Find full resource by name or file_path
                for resource in raw_resources:
                    resource_name = resource.get("name", "")
                    resource_file_path = resource.get("file_path", "")
                    
                    if (name and resource_name == name) or (file_path and resource_file_path == file_path):
                        # Add similarity score
                        resource_copy = resource.copy()
                        resource_copy["similarity_score"] = 1.0 - distance  # Convert distance to similarity
                        relevant_resources.append(resource_copy)
                        break
            
            return relevant_resources
        else:
            # Return minimal results from metadata (no synthetic summaries)
            return [
                {
                    "name": metadata.get("name", ""),
                    "file_path": metadata.get("file_path", ""),
                    "description": metadata.get("description", ""),
                    "similarity_score": 1.0 - distance,
                }
                for metadata, distance in zip(result_metadatas, result_distances)
            ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the indexed resources (all files, not just anti-patterns)."""
        return {
            "collection_name": self.collection_name,
            "indexed_count": self.collection.count(),
            "available": CHROMADB_AVAILABLE,
        }


def create_semantic_search(
    raw_resources: Optional[List[Dict[str, Any]]] = None,
    force_reindex: bool = False,
) -> Optional[DAMLSemanticSearch]:
    """
    Create and initialize a semantic search engine for ALL DAML resources.
    
    Indexes everything (examples, docs, patterns, anti-patterns, tests) and provides
    fast semantic similarity search. The LLM reasons about which files are relevant.
    
    Args:
        raw_resources: List of ALL raw resources to index (not filtered)
        force_reindex: Force re-indexing even if collection exists
    
    Returns:
        Initialized search engine, or None if ChromaDB unavailable
    """
    if not CHROMADB_AVAILABLE:
        logger.warning("⚠️ ChromaDB not available - semantic search disabled")
        return None
    
    try:
        search_engine = DAMLSemanticSearch()
        
        # Index resources if provided
        if raw_resources:
            search_engine.index_resources(raw_resources, force_reindex=force_reindex)
        
        return search_engine
    
    except Exception as e:
        logger.error(f"❌ Failed to initialize semantic search: {e}")
        return None

