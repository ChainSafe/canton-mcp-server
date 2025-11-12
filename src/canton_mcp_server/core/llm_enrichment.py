"""
LLM-Based Resource Enrichment Engine

Uses Claude Haiku 3.5 to enrich canonical resource metadata for better search relevance.
Implements incremental caching based on Git blob hashes to avoid re-enriching unchanged files.
"""

import json
import logging
import os
import time
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from ..env import get_env, get_env_bool, get_env_int

logger = logging.getLogger(__name__)


@dataclass
class EnrichedMetadata:
    """Enriched metadata for a resource."""
    enriched_at: str
    summary: str
    keywords: List[str]
    use_cases: List[str]
    security_level: str
    complexity_level: str
    domain_concepts: List[str]


class LLMEnrichmentEngine:
    """
    LLM-based enrichment engine for canonical resources.
    
    Features:
    - Incremental updates (only enrich new/changed files)
    - Crash-safe batch processing
    - Persistent cache based on Git blob hashes
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the LLM enrichment engine.
        
        Args:
            cache_dir: Directory for enrichment cache (default: ~/.canton-mcp)
        """
        self.enabled = get_env_bool("ENABLE_LLM_ENRICHMENT", False)
        self.model = get_env("LLM_ENRICHMENT_MODEL", "claude-3-5-haiku-20241022")
        self.batch_size = get_env_int("LLM_ENRICHMENT_BATCH_SIZE", 20)
        self.max_tokens = get_env_int("LLM_ENRICHMENT_MAX_TOKENS", 500)
        
        # Cache directory
        if cache_dir is None:
            cache_dir = Path.home() / ".canton-mcp"
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "enrichment-cache.json"
        
        # Initialize Anthropic client if enabled
        self.client = None
        if self.enabled:
            api_key = get_env("ANTHROPIC_API_KEY", "")
            if not api_key:
                logger.warning("ENABLE_LLM_ENRICHMENT=true but ANTHROPIC_API_KEY not set. Disabling enrichment.")
                self.enabled = False
            elif Anthropic is None:
                logger.warning("anthropic package not installed. Run: pip install anthropic>=0.34.0")
                self.enabled = False
            else:
                try:
                    self.client = Anthropic(api_key=api_key)
                    logger.info(f"✅ LLM enrichment enabled (model: {self.model})")
                except Exception as e:
                    logger.error(f"Failed to initialize Anthropic client: {e}")
                    self.enabled = False
        
        # Load cache
        self._cache: Dict[str, Any] = self._load_cache()
    
    def _load_cache(self) -> Dict[str, Any]:
        """Load enrichment cache from disk."""
        if not self.cache_file.exists():
            return {
                "cache_version": "1.0",
                "last_updated": None,
                "repos": {},
                "enrichments": {}
            }
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
            
            # Validate cache version
            if cache.get("cache_version") != "1.0":
                logger.warning("Cache version mismatch, starting fresh")
                return {
                    "cache_version": "1.0",
                    "last_updated": None,
                    "repos": {},
                    "enrichments": {}
                }
            
            logger.info(f"Loaded enrichment cache: {len(cache.get('enrichments', {}))} enrichments")
            return cache
        except Exception as e:
            logger.error(f"Failed to load enrichment cache: {e}")
            return {
                "cache_version": "1.0",
                "last_updated": None,
                "repos": {},
                "enrichments": {}
            }
    
    def _save_cache(self) -> None:
        """Save enrichment cache to disk."""
        try:
            self._cache["last_updated"] = datetime.utcnow().isoformat() + "Z"
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2)
            logger.debug(f"Saved enrichment cache: {len(self._cache.get('enrichments', {}))} enrichments")
        except Exception as e:
            logger.error(f"Failed to save enrichment cache: {e}")
    
    def enrich_resources(
        self,
        resources: List[Dict[str, Any]],
        commit_hashes: Dict[str, str],
        force_all: bool = False
    ) -> Dict[str, EnrichedMetadata]:
        """
        Enrich resources incrementally.
        
        Args:
            resources: Raw resources from DirectFileResourceLoader
            commit_hashes: Current commit hashes for each repo
            force_all: Force re-enrichment of all files
            
        Returns:
            Dictionary mapping blob hash to enriched metadata
        """
        if not self.enabled:
            logger.debug("LLM enrichment disabled")
            return {}
        
        if not self.client:
            logger.warning("LLM client not available")
            return {}
        
        # Update repo commit hashes
        self._cache["repos"] = {
            repo: {
                "commit": commit_hashes.get(repo, ""),
                "last_enriched": datetime.utcnow().isoformat() + "Z"
            }
            for repo in ["daml", "canton", "daml-finance"]
        }
        
        # Identify files needing enrichment
        files_to_enrich = self._identify_files_to_enrich(resources, force_all)
        
        if not files_to_enrich:
            logger.info("No new files to enrich")
            return self._get_all_enrichments()
        
        logger.info(f"Enriching {len(files_to_enrich)} files (batch size: {self.batch_size})...")
        
        # Process in batches
        total_batches = (len(files_to_enrich) + self.batch_size - 1) // self.batch_size
        enriched_count = 0
        
        api_error_count = 0
        for batch_idx, batch in enumerate(self._batch(files_to_enrich, self.batch_size), 1):
            logger.info(f"Batch {batch_idx}/{total_batches}: Enriching {len(batch)} files...")
            
            try:
                enrichments = self._enrich_batch(batch)
                enriched_count += len(enrichments)
                
                # Update cache after each batch (crash-safe)
                self._cache["enrichments"].update(enrichments)
                self._save_cache()
                
                logger.info(f"✅ Enriched {enriched_count}/{len(files_to_enrich)} files")
                
                # Reset API error count on success
                api_error_count = 0
                
                # Rate limiting: small delay between batches
                if batch_idx < total_batches:
                    time.sleep(0.5)
                    
            except Exception as e:
                error_msg = str(e)
                # Check for API credit/authentication errors
                if "credit balance" in error_msg.lower() or "401" in error_msg or "403" in error_msg:
                    logger.error(f"❌ API credit/authentication error: {e}")
                    logger.error(f"Stopping enrichment. {enriched_count} files enriched successfully.")
                    logger.error(f"Remaining files: {len(files_to_enrich) - enriched_count}")
                    break
                
                api_error_count += 1
                logger.error(f"Failed to enrich batch {batch_idx}: {e}")
                
                # Stop if too many consecutive API errors (might be rate limiting or credit issue)
                if api_error_count >= 3:
                    logger.warning(f"Too many consecutive errors ({api_error_count}). Stopping enrichment.")
                    logger.warning(f"Successfully enriched: {enriched_count}/{len(files_to_enrich)} files")
                    break
                
                continue
        
        remaining = len(files_to_enrich) - enriched_count
        if remaining > 0:
            logger.warning(f"⚠️  Enrichment incomplete: {enriched_count}/{len(files_to_enrich)} files enriched ({remaining} remaining)")
            logger.info(f"💡 Run 'enrich --new' again to continue with remaining files")
        else:
            logger.info(f"✅ Enrichment complete: {enriched_count} files enriched")
        return self._get_all_enrichments()
    
    def _identify_files_to_enrich(
        self,
        resources: List[Dict[str, Any]],
        force_all: bool
    ) -> List[Dict[str, Any]]:
        """Identify files that need enrichment."""
        files_to_enrich = []
        enrichments = self._cache.get("enrichments", {})
        
        for resource in resources:
            blob_hash = resource.get("canonical_hash", "")
            if not blob_hash:
                continue
            
            # Skip if already enriched (unless forcing)
            if not force_all and blob_hash in enrichments:
                continue
            
            files_to_enrich.append(resource)
        
        return files_to_enrich
    
    def _batch(self, items: List[Any], batch_size: int):
        """Yield batches of items."""
        for i in range(0, len(items), batch_size):
            yield items[i:i + batch_size]
    
    def _enrich_batch(self, batch: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Enrich a batch of resources."""
        enrichments = {}
        
        for resource in batch:
            try:
                enriched = self._enrich_single_resource(resource)
                if enriched:
                    blob_hash = resource.get("canonical_hash", "")
                    enrichments[blob_hash] = asdict(enriched)
            except Exception as e:
                error_msg = str(e)
                # Re-raise API credit/auth errors to stop batch processing
                if "credit balance" in error_msg.lower() or "400" in error_msg or "401" in error_msg or "403" in error_msg:
                    raise  # Propagate to batch handler
                # For other errors, log and continue
                logger.warning(f"Failed to enrich {resource.get('name', 'unknown')}: {e}")
                continue
        
        return enrichments
    
    def _enrich_single_resource(self, resource: Dict[str, Any]) -> Optional[EnrichedMetadata]:
        """Enrich a single resource using Claude Haiku."""
        file_path = resource.get("file_path", "")
        content = resource.get("content", "")
        
        # Sample first 2000 chars for prompt
        content_sample = content[:2000]
        
        prompt = f"""Analyze this DAML documentation and extract structured metadata for search optimization.

File: {file_path}
Content (first 2000 chars):
{content_sample}

Extract:
1. **Summary** (1-2 sentences describing what this resource teaches/shows)
2. **Keywords** (10-15 technical/business terms relevant to this content)
3. **Use Cases** (from: asset_management, financial_instruments, governance, identity_management, supply_chain, basic_templates)
4. **Security Level** (basic/enhanced/enterprise)
5. **Complexity Level** (beginner/intermediate/advanced)
6. **Domain Concepts** (business/technical concepts like "hedge fund", "collateral posting", "portfolio rebalancing")

Return as JSON with these exact keys: summary, keywords, use_cases, security_level, complexity_level, domain_concepts"""

        try:
            # Skip very short or empty files
            if len(content.strip()) < 10:
                logger.debug(f"Skipping very short file: {file_path} ({len(content)} chars)")
                return None
            
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
            except Exception as api_error:
                # Re-raise API errors (credit, auth, etc.) so batch handler can stop
                error_msg = str(api_error)
                if "credit balance" in error_msg.lower() or "400" in error_msg or "401" in error_msg or "403" in error_msg:
                    raise  # Re-raise to stop batch processing
                # For other errors, log and return None
                logger.warning(f"API error for {file_path}: {api_error}")
                return None
            
            # Check if response has content
            if not response.content or len(response.content) == 0:
                logger.warning(f"Empty LLM response for {file_path}")
                return None
            
            # Parse JSON response
            response_text = response.content[0].text.strip()
            
            if not response_text:
                logger.warning(f"Empty response text for {file_path}")
                return None
            
            # Extract JSON from response (handle markdown code blocks)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            if not response_text:
                logger.warning(f"No JSON found in response for {file_path}")
                return None
            
            # Try to extract just the first JSON object (handle extra text after JSON)
            try:
                # Find the first { and try to parse from there
                start_idx = response_text.find('{')
                if start_idx == -1:
                    logger.warning(f"No JSON object found in response for {file_path}")
                    return None
                
                # Try to find the matching closing brace
                brace_count = 0
                end_idx = start_idx
                for i in range(start_idx, len(response_text)):
                    if response_text[i] == '{':
                        brace_count += 1
                    elif response_text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
                
                # Extract just the JSON object
                json_text = response_text[start_idx:end_idx]
                metadata = json.loads(json_text)
            except (json.JSONDecodeError, ValueError) as e:
                # Fallback: try parsing the whole thing
                try:
                    metadata = json.loads(response_text)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse JSON for {file_path}: {e}")
                    return None
            
            # Validate and create enriched metadata
            return EnrichedMetadata(
                enriched_at=datetime.utcnow().isoformat() + "Z",
                summary=metadata.get("summary", ""),
                keywords=metadata.get("keywords", []),
                use_cases=metadata.get("use_cases", []),
                security_level=metadata.get("security_level", "basic"),
                complexity_level=metadata.get("complexity_level", "beginner"),
                domain_concepts=metadata.get("domain_concepts", [])
            )
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response for {file_path}: {e} (response length: {len(response_text) if 'response_text' in locals() else 0})")
            return None
        except Exception as e:
            logger.warning(f"Failed to enrich {file_path}: {e}")
            return None
    
    def get_enrichment(self, blob_hash: str) -> Optional[EnrichedMetadata]:
        """Get enriched metadata for a resource by blob hash."""
        enrichments = self._cache.get("enrichments", {})
        enriched_data = enrichments.get(blob_hash)
        
        if not enriched_data:
            return None
        
        try:
            return EnrichedMetadata(**enriched_data)
        except Exception as e:
            logger.warning(f"Failed to parse enrichment for {blob_hash}: {e}")
            return None
    
    def _get_all_enrichments(self) -> Dict[str, EnrichedMetadata]:
        """Get all enrichments as EnrichedMetadata objects."""
        enrichments = {}
        for blob_hash, enriched_data in self._cache.get("enrichments", {}).items():
            try:
                enrichments[blob_hash] = EnrichedMetadata(**enriched_data)
            except Exception:
                continue
        return enrichments
    
    def get_cache_status(self) -> Dict[str, Any]:
        """Get enrichment cache status."""
        enrichments = self._cache.get("enrichments", {})
        repos = self._cache.get("repos", {})
        
        return {
            "enabled": self.enabled,
            "total_enrichments": len(enrichments),
            "last_updated": self._cache.get("last_updated"),
            "repos": repos,
            "cache_file": str(self.cache_file)
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Get enrichment statistics."""
        enrichments = self._cache.get("enrichments", {})
        
        # Count by use case
        use_case_counts = {}
        security_level_counts = {}
        complexity_level_counts = {}
        
        for enriched_data in enrichments.values():
            use_cases = enriched_data.get("use_cases", [])
            for use_case in use_cases:
                use_case_counts[use_case] = use_case_counts.get(use_case, 0) + 1
            
            security_level = enriched_data.get("security_level", "basic")
            security_level_counts[security_level] = security_level_counts.get(security_level, 0) + 1
            
            complexity_level = enriched_data.get("complexity_level", "beginner")
            complexity_level_counts[complexity_level] = complexity_level_counts.get(complexity_level, 0) + 1
        
        return {
            "total_enrichments": len(enrichments),
            "use_case_distribution": use_case_counts,
            "security_level_distribution": security_level_counts,
            "complexity_level_distribution": complexity_level_counts
        }

