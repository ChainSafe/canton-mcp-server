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
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

def _default_persist_dir() -> str:
    """Stable persist directory that doesn't change with CWD."""
    from ..env import get_env
    return get_env("CHROMA_PERSIST_DIR", str(Path.home() / ".canton-mcp" / "chroma_db"))


def _get_embedding_function():
    """Return an embedding function based on the EMBEDDING_DEVICE env var.

    - "cuda": SentenceTransformerEmbeddingFunction on GPU (~55x faster on T4)
    - "cpu" (default): ONNXMiniLM_L6_V2 on CPU

    Note: ONNX and SentenceTransformer produce numerically different embeddings,
    so switching backends triggers an automatic re-index of the ChromaDB collection.
    """
    from ..env import get_env
    device = get_env("EMBEDDING_DEVICE", "cpu").lower()
    if device == "cuda":
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            test_tensor = torch.zeros(1, device="cuda")
            logger.info(f"CUDA verified: {gpu_name}, {torch.cuda.memory_allocated()/1024/1024:.1f}MB allocated")
            del test_tensor
        else:
            logger.warning("EMBEDDING_DEVICE=cuda but CUDA unavailable, falling back to CPU ONNX")
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
            return ONNXMiniLM_L6_V2(preferred_providers=["CPUExecutionProvider"])

        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        logger.info("Using SentenceTransformer embeddings on CUDA GPU")
        return SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2", device="cuda")
    else:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
        logger.info("Using ONNX MiniLM embeddings on CPU")
        return ONNXMiniLM_L6_V2(preferred_providers=["CPUExecutionProvider"])


def _get_embedding_backend_label() -> str:
    """Return a label identifying the current embedding backend."""
    from ..env import get_env
    device = get_env("EMBEDDING_DEVICE", "cpu").lower()
    return "st-cuda" if device == "cuda" else "onnx-cpu"

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

        # Set up persist directory (stable absolute path, not CWD-relative)
        if persist_directory is None:
            persist_directory = _default_persist_dir()

        Path(persist_directory).mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client with persistence
        self.client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            )
        )

        # Resolve embedding function: explicit arg > env-var-based default
        if embedding_function is None:
            embedding_function = _get_embedding_function()
        self._embedding_function = embedding_function
        self._backend_label = _get_embedding_backend_label()

        # Check if an existing collection uses a different embedding backend.
        # ChromaDB rejects get_or_create_collection when the persisted embedding
        # function differs from the new one, so we must delete first.
        try:
            existing = self.client.get_collection(name=collection_name)
            stored_backend = existing.metadata.get("embedding_backend", "")
            if stored_backend and stored_backend != self._backend_label:
                logger.warning(
                    f"Embedding backend changed: {stored_backend} → {self._backend_label}. "
                    f"Deleting old collection ({existing.count()} items) for re-index."
                )
                self.client.delete_collection(collection_name)
        except Exception:
            pass  # Collection doesn't exist yet — that's fine

        # Get or create collection with the current embedding function
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={
                "description": "DAML semantic search - all resources (examples, docs, patterns)",
                "embedding_backend": self._backend_label,
            },
            embedding_function=self._embedding_function,
        )

        logger.info(
            f"✅ ChromaDB collection '{collection_name}' initialized "
            f"({self.collection.count()} items, backend: {self._backend_label})"
        )
    
    def _get_commit_hash_fingerprint(self, raw_resources: List[Dict[str, Any]]) -> str:
        """
        Compute a fingerprint from the source commit hashes in the resource list.
        This lets us detect when the repos have changed without counting documents.
        """
        commits = {}
        for r in raw_resources:
            repo = r.get("source_repo", "")
            commit = r.get("source_commit", "")
            if repo and commit:
                commits[repo] = commit
        fingerprint = json.dumps(commits, sort_keys=True)
        return hashlib.sha1(fingerprint.encode()).hexdigest()[:16]

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
        
        current_count = self.collection.count()
        expected_count = len(resources_to_index)

        if not force_reindex:
            # Primary check: commit-hash fingerprint stored in collection metadata
            new_fingerprint = self._get_commit_hash_fingerprint(resources_to_index)
            stored_fingerprint = self.collection.metadata.get("commit_fingerprint", "")
            
            if stored_fingerprint and stored_fingerprint == new_fingerprint and current_count > 0:
                logger.info(
                    f"✅ Index up-to-date (commit fingerprint match, {current_count} resources)"
                )
                return current_count

            # Fallback: count-based check (handles first run after path migration)
            count_diff = abs(current_count - expected_count)
            tolerance = max(50, int(expected_count * 0.01))
            if count_diff <= tolerance and current_count > 0:
                logger.info(f"✅ Index up-to-date ({current_count} resources, diff: {count_diff})")
                return current_count

        # Clear existing index before reindexing
        if current_count > 0:
            logger.info(f"🔄 Clearing existing index ({current_count} items)")
            self.client.delete_collection(self.collection_name)
            new_fingerprint = self._get_commit_hash_fingerprint(resources_to_index)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={
                    "description": "DAML semantic search (all resources)",
                    "commit_fingerprint": new_fingerprint,
                    "embedding_backend": self._backend_label,
                },
                embedding_function=self._embedding_function,
            )
        elif not force_reindex:
            # Collection is empty (fresh start) — set fingerprint now so we can skip next time
            new_fingerprint = self._get_commit_hash_fingerprint(resources_to_index)
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={
                    "description": "DAML semantic search (all resources)",
                    "commit_fingerprint": new_fingerprint,
                    "embedding_backend": self._backend_label,
                },
                embedding_function=self._embedding_function,
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
            
            # Create unique ID based on repo + file path
            name = resource.get("name", "")
            file_path_val = resource.get("file_path", "")
            source_repo = resource.get("source_repo", "unknown")
            
            # Include repo name to ensure uniqueness across repos
            if file_path_val:
                resource_id = f"{source_repo}-{file_path_val}".replace("/", "-").replace(".", "-")
            else:
                resource_id = name.replace(" ", "-")
            
            # Add hash suffix if ID is too short (ensure uniqueness)
            if len(resource_id) < 10:
                import hashlib
                hash_suffix = hashlib.md5(f"{source_repo}{file_path_val}".encode()).hexdigest()[:8]
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
        
        from ..env import get_env

        # Build O(1) lookup keyed on (source_repo, file_path) — file_path alone is
        # not unique across repos (e.g. README.md exists in all three).
        if raw_resources:
            lookup = {
                (r.get("source_repo", ""), r.get("file_path", "")): r
                for r in raw_resources
            }
            relevant_resources = []
            for metadata, distance in zip(result_metadatas, result_distances):
                key = (metadata.get("source_repo", ""), metadata.get("file_path", ""))
                resource = lookup.get(key)
                if resource:
                    resource_copy = resource.copy()
                    resource_copy["similarity_score"] = 1.0 - distance
                    relevant_resources.append(resource_copy)
        else:
            relevant_resources = [
                {
                    "name": metadata.get("name", ""),
                    "file_path": metadata.get("file_path", ""),
                    "description": metadata.get("description", ""),
                    "source_repo": metadata.get("source_repo", ""),
                    "similarity_score": 1.0 - distance,
                }
                for metadata, distance in zip(result_metadatas, result_distances)
            ]

        # Filter results below minimum similarity threshold
        min_score = float(get_env("MIN_SIMILARITY_THRESHOLD", "0.3"))
        relevant_resources = [r for r in relevant_resources if r.get("similarity_score", 0) >= min_score]

        # Re-read file content from disk so LLM receives actual code, not empty strings
        try:
            canonical_docs = Path(get_env("CANONICAL_DOCS_PATH", "../../canonical-daml-docs"))
        except Exception:
            canonical_docs = Path("../../canonical-daml-docs")

        for r in relevant_resources:
            source_repo = r.get("source_repo", "")
            file_path = r.get("file_path", "")
            if source_repo and file_path:
                abs_path = canonical_docs / source_repo / file_path
                try:
                    r["content"] = abs_path.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as e:
                    logger.debug("Failed to read content from %s: %s", abs_path, e)
                    r["content"] = ""
            else:
                r["content"] = ""

        return relevant_resources
    
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

