"""
Direct File Resource Loader

Scans cloned canonical repositories and serves documentation files directly
with Git verification, eliminating the need for YAML conversion.

Features:
- Disk caching with commit-hash-based invalidation
- Hot-reload support with git pull detection
"""

import os
import subprocess
import logging
import json
import time
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .github_verification import get_github_verifier

logger = logging.getLogger(__name__)


class CanonicalRepoFileHandler(FileSystemEventHandler):
    """Handles file system events for canonical repository hot-reloading"""
    
    def __init__(self, loader: 'DirectFileResourceLoader'):
        self.loader = loader
        self.last_check = 0
        self.check_delay = 2.0  # Debounce git pulls by 2 seconds
    
    def on_any_event(self, event):
        """Handle any file system event in canonical repos"""
        if event.is_directory:
            return
        
        # Skip .git directory events
        if ".git" in str(event.src_path):
            return
        
        # Debounce rapid changes (like git pull with many files)
        current_time = time.time()
        if current_time - self.last_check < self.check_delay:
            return
        
        self.last_check = current_time
        
        logger.info(f"Canonical repo file changed: {event.src_path}")
        
        # Check if commit hashes changed
        try:
            self.loader._check_and_reload_on_commit_change()
        except Exception as e:
            logger.error(f"Failed to check for commit changes: {e}")


class DirectFileResourceLoader:
    """
    Loads documentation files directly from cloned canonical repositories.
    
    Features:
    - Disk caching with commit-hash-based invalidation
    - Hot-reload support for git pull detection
    - Git verification of all files
    """
    
    def __init__(self, canonical_docs_path: Path, enable_hot_reload: bool = False):
        """
        Initialize the direct file loader.
        
        Args:
            canonical_docs_path: Path to cloned canonical documentation repositories
            enable_hot_reload: Enable hot-reload file watching
        """
        self.canonical_docs_path = canonical_docs_path
        self.github_verifier = get_github_verifier()
        self.enable_hot_reload = enable_hot_reload
        
        # Official repositories
        self.repos = {
            "daml": canonical_docs_path / "daml",
            "canton": canonical_docs_path / "canton", 
            "daml-finance": canonical_docs_path / "daml-finance"
        }
        
        # In-memory cache for scanned resources
        self._cached_resources: Dict[str, List[Dict[str, Any]]] = {}
        self._cache_timestamp: Optional[datetime] = None
        self._current_commit_hashes: Dict[str, str] = {}
        
        # Hot-reload file watcher
        self.observer: Optional[Observer] = None
        
        # Disk cache directory
        self.cache_dir = Path.home() / ".canton-mcp"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Allowed documentation file extensions
        self.doc_extensions = {
            ".md",      # Markdown files
            ".rst",     # reStructuredText files
            ".txt",     # Plain text files
            ".daml",    # DAML files
            ".yaml",    # YAML files
            ".yml",     # YAML files
        }
        
        # Build/template file extensions (filter out)
        self.build_extensions = {
            ".py", ".js", ".css", ".html", ".conf", ".ini", ".toml", ".lock", ".log"
        }
        
        # Binary file extensions (filter out)
        self.binary_extensions = {
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",  # Images
            ".pdf", ".zip", ".tar", ".gz", ".rar",            # Archives
            ".exe", ".dll", ".so", ".dylib",                   # Binaries
            ".dar", ".jar", ".war", ".ear",                    # Java archives
            ".class", ".o", ".obj", ".a",                      # Compiled files
        }
    
    def scan_repositories(self, force_refresh: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scan all cloned repositories for documentation files.
        
        Tries to load from disk cache first, falls back to full scan.
        
        Args:
            force_refresh: If True, bypass all caches and rescan all repositories
        
        Returns:
            Dictionary mapping resource types to lists of file resources
        """
        # Return in-memory cache if available and not forcing refresh
        if not force_refresh and self._cached_resources and self._cache_timestamp:
            logger.debug("Returning in-memory cached repository scan results")
            return self._cached_resources
        
        # Get current commit hashes
        commit_hashes = self._get_all_commit_hashes()
        self._current_commit_hashes = commit_hashes
        
        # Try to load from disk cache (unless forcing refresh)
        if not force_refresh:
            cached_resources = self._load_from_disk_cache(commit_hashes)
            if cached_resources is not None:
                logger.info(f"Loaded {sum(len(r) for r in cached_resources.values())} resources from disk cache")
                self._cached_resources = cached_resources
                self._cache_timestamp = datetime.utcnow()
                
                # Start hot-reload watcher if enabled
                if self.enable_hot_reload:
                    self._start_file_watcher()
                
                return cached_resources
        
        # No cache available or forced refresh - do full scan
        logger.info("Scanning cloned repositories for documentation files...")
        
        resources = {
            "patterns": [],
            "anti_patterns": [],
            "rules": [],
            "docs": []
        }
        
        for repo_name, repo_path in self.repos.items():
            if not repo_path.exists():
                logger.warning(f"Repository not found: {repo_path}")
                continue
            
            logger.info(f"Scanning repository: {repo_name}")
            repo_resources = self._scan_repository(repo_path, repo_name)
            
            # Categorize resources by type
            for resource in repo_resources:
                resource_type = self._categorize_resource(resource)
                resources[resource_type].append(resource)
        
        total_resources = sum(len(resource_list) for resource_list in resources.values())
        logger.info(f"Found {total_resources} documentation files across all repositories")
        
        # Save to both in-memory and disk cache
        self._cached_resources = resources
        self._cache_timestamp = datetime.utcnow()
        self._save_to_disk_cache(resources, commit_hashes)
        
        # Trigger LLM enrichment if enabled (non-blocking, runs in background)
        self._trigger_enrichment_if_enabled(resources, commit_hashes)
        
        # Start hot-reload watcher if enabled
        if self.enable_hot_reload:
            self._start_file_watcher()
        
        return resources
    
    def _scan_repository(self, repo_path: Path, repo_name: str) -> List[Dict[str, Any]]:
        """
        Scan a single repository for documentation files.
        
        Args:
            repo_path: Path to the repository
            repo_name: Name of the repository
            
        Returns:
            List of file resources found in the repository
        """
        resources = []
        
        try:
            # Get current commit hash
            commit_hash = self._get_current_commit_hash(repo_path)
            if not commit_hash:
                logger.error(f"Could not get commit hash for {repo_name}")
                return resources
            
            # Scan for documentation files (skip .git directory)
            for file_path in repo_path.rglob("*"):
                # Skip .git directory and its contents
                if ".git" in file_path.parts:
                    continue
                    
                if file_path.is_file() and self._is_documentation_file(file_path):
                    resource = self._create_file_resource(file_path, repo_path, repo_name, commit_hash)
                    if resource:
                        resources.append(resource)
            
            logger.info(f"Found {len(resources)} documentation files in {repo_name}")
            
        except Exception as e:
            logger.error(f"Error scanning repository {repo_name}: {e}")
        
        return resources
    
    def _is_documentation_file(self, file_path: Path) -> bool:
        """
        Check if a file is a documentation file based on extension and path.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if file appears to be documentation, False otherwise
        """
        # Check file extension
        file_ext = file_path.suffix.lower()
        
        # Allow documentation extensions
        if file_ext in self.doc_extensions:
            return True
        
        # Reject build file extensions
        if file_ext in self.build_extensions:
            return False
        
        # Reject binary file extensions
        if file_ext in self.binary_extensions:
            return False
        
        # Special cases for files without extensions
        if not file_ext:
            filename = file_path.name.lower()
            
            # Documentation files without extensions
            if filename in {"readme", "license", "changelog", "contributing", "authors"}:
                return True
            
            # Build files without extensions
            if filename in {"makefile", "dockerfile", "docker-compose", "sphinx", "conf"}:
                return False
        
        # Default: allow files without clear build indicators
        return True
    
    def _create_file_resource(self, file_path: Path, repo_path: Path, repo_name: str, commit_hash: str) -> Optional[Dict[str, Any]]:
        """
        Create a resource dictionary for a documentation file.
        
        Args:
            file_path: Path to the file
            repo_path: Path to the repository root
            repo_name: Name of the repository
            commit_hash: Current commit hash
            
        Returns:
            Resource dictionary or None if creation failed
        """
        try:
            # Get relative path from repo root
            relative_path = file_path.relative_to(repo_path)
            relative_path_str = str(relative_path)
            
            # Get Git blob hash for verification
            blob_hash = self._get_git_blob_hash(repo_path, commit_hash, relative_path_str)
            if not blob_hash:
                logger.warning(f"Could not get blob hash for {relative_path_str}")
                return None
            
            # Read file content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                logger.warning(f"Could not read file as UTF-8: {relative_path_str}")
                return None
            
            # Create resource
            resource = {
                "name": self._generate_resource_name(file_path, repo_name),
                "version": "1.0.0",
                "description": f"Canonical documentation from {repo_name}: {relative_path_str}",
                "tags": [repo_name, "canonical", "documentation", "git-verified"],
                "author": "Digital Asset",
                "created_at": datetime.utcnow().isoformat() + "Z",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "content": content,
                "file_path": relative_path_str,
                "file_extension": file_path.suffix.lower(),
                "canonical_hash": blob_hash,
                "source_commit": commit_hash,
                "source_file": relative_path_str,
                "source_repo": repo_name,
                "extracted_at": datetime.utcnow().isoformat() + "Z"
            }
            
            return resource
            
        except Exception as e:
            logger.error(f"Error creating resource for {file_path}: {e}")
            return None
    
    def _generate_resource_name(self, file_path: Path, repo_name: str) -> str:
        """Generate a resource name from file path and repo name."""
        # Remove extension and convert to resource name
        name = file_path.stem.lower()
        name = name.replace("_", "-").replace(" ", "-")
        return f"{repo_name}-{name}"
    
    def _categorize_resource(self, resource: Dict[str, Any]) -> str:
        """
        Categorize a resource by type based on file path and content.
        
        Args:
            resource: Resource dictionary
            
        Returns:
            Resource type (patterns, anti_patterns, rules, docs)
        """
        file_path = resource.get("file_path", "").lower()
        
        # Categorize based on file path patterns
        if any(pattern in file_path for pattern in ["pattern", "example", "template"]):
            return "patterns"
        elif any(pattern in file_path for pattern in ["anti-pattern", "bad", "wrong", "avoid"]):
            return "anti_patterns"
        elif any(pattern in file_path for pattern in ["rule", "policy", "guideline"]):
            return "rules"
        else:
            return "docs"
    
    def _get_current_commit_hash(self, repo_path: Path) -> Optional[str]:
        """Get the current commit hash for a repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get commit hash: {e}")
            return None
    
    def _get_git_blob_hash(self, repo_path: Path, commit_hash: str, file_path: str) -> Optional[str]:
        """Get the Git blob hash for a specific file at a given commit."""
        try:
            # Get tree hash
            result = subprocess.run(
                ["git", "show", "--format=%T", "-s", commit_hash],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            tree_hash = result.stdout.strip()
            
            # Get blob hash
            result = subprocess.run(
                ["git", "ls-tree", tree_hash, file_path],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            if result.stdout.strip():
                blob_hash = result.stdout.strip().split()[2]
                return blob_hash
            
            return None
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get blob hash for {file_path}: {e}")
            return None
    
    def get_resource_by_name(self, name: str, resource_type: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific resource by name and type.
        
        Args:
            name: Name of the resource
            resource_type: Type of resource
            
        Returns:
            Resource dictionary or None if not found
        """
        all_resources = self.scan_repositories()
        
        if resource_type not in all_resources:
            return None
        
        for resource in all_resources[resource_type]:
            if resource.get("name") == name:
                return resource
        
        return None
    
    def verify_all_resources(self) -> Dict[str, List[str]]:
        """
        Verify integrity of all resources using Git verification.
        
        Returns:
            Dictionary mapping resource types to lists of verification errors
        """
        logger.info("Verifying integrity of all direct file resources...")
        
        verification_results = {
            "patterns": [],
            "anti_patterns": [],
            "rules": [],
            "docs": []
        }
        
        all_resources = self.scan_repositories()
        
        for resource_type, resources in all_resources.items():
            for resource in resources:
                # Verify Git integrity using GitHub API
                source_file = resource.get("source_file")
                source_commit = resource.get("source_commit")
                canonical_hash = resource.get("canonical_hash")
                
                if source_file and source_commit and canonical_hash:
                    if not self.github_verifier.verify_blob_hash(source_file, source_commit, canonical_hash):
                        error_msg = f"Git verification failed for {resource.get('name', 'unknown')}"
                        verification_results[resource_type].append(error_msg)
        
        # Log verification results
        total_errors = sum(len(errors) for errors in verification_results.values())
        if total_errors == 0:
            logger.info("All direct file resources passed Git verification")
        else:
            logger.warning(f"Git verification found {total_errors} errors")
        
        return verification_results
    
    def _get_all_commit_hashes(self) -> Dict[str, str]:
        """Get current commit hashes for all repositories."""
        commit_hashes = {}
        
        for repo_name, repo_path in self.repos.items():
            if repo_path.exists():
                commit_hash = self._get_current_commit_hash(repo_path)
                if commit_hash:
                    commit_hashes[repo_name] = commit_hash
        
        return commit_hashes
    
    def _get_cache_filename(self, commit_hashes: Dict[str, str]) -> str:
        """Generate cache filename based on commit hashes."""
        # Sort for consistency
        hash_parts = [f"{repo}-{commit_hashes.get(repo, 'none')[:8]}" 
                     for repo in sorted(self.repos.keys())]
        return f"resource-cache-{'-'.join(hash_parts)}.json"
    
    def _load_from_disk_cache(self, commit_hashes: Dict[str, str]) -> Optional[Dict[str, List[Dict[str, Any]]]]:
        """
        Load resources from disk cache if available.
        
        Args:
            commit_hashes: Current commit hashes to match against
            
        Returns:
            Cached resources or None if cache miss
        """
        cache_file = self.cache_dir / self._get_cache_filename(commit_hashes)
        
        if not cache_file.exists():
            logger.debug(f"No disk cache found at {cache_file}")
            return None
        
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # Verify commit hashes match
            cached_hashes = cache_data.get("commit_hashes", {})
            if cached_hashes != commit_hashes:
                logger.warning("Cache commit hashes don't match, invalidating cache")
                return None
            
            logger.info(f"✅ Loaded from disk cache: {cache_file.name}")
            return cache_data.get("resources", {})
            
        except Exception as e:
            logger.error(f"Failed to load disk cache: {e}")
            return None
    
    def _save_to_disk_cache(self, resources: Dict[str, List[Dict[str, Any]]], commit_hashes: Dict[str, str]) -> None:
        """
        Save resources to disk cache.
        
        Args:
            resources: Resources to cache
            commit_hashes: Current commit hashes
        """
        cache_file = self.cache_dir / self._get_cache_filename(commit_hashes)
        
        try:
            cache_data = {
                "commit_hashes": commit_hashes,
                "cached_at": datetime.utcnow().isoformat() + "Z",
                "resources": resources
            }
            
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
            
            logger.info(f"💾 Saved to disk cache: {cache_file.name}")
            
            # Clean up old cache files
            self._cleanup_old_caches(cache_file)
            
        except Exception as e:
            logger.error(f"Failed to save disk cache: {e}")
    
    def _cleanup_old_caches(self, current_cache: Path) -> None:
        """Remove old cache files, keeping only the current one."""
        try:
            for cache_file in self.cache_dir.glob("resource-cache-*.json"):
                if cache_file != current_cache:
                    cache_file.unlink()
                    logger.debug(f"Removed old cache file: {cache_file.name}")
        except Exception as e:
            logger.error(f"Failed to cleanup old caches: {e}")
    
    def _start_file_watcher(self) -> None:
        """Start file system watcher for hot-reload."""
        if self.observer is not None:
            return  # Already started
        
        try:
            self.observer = Observer()
            event_handler = CanonicalRepoFileHandler(self)
            
            # Watch all canonical repositories
            for repo_name, repo_path in self.repos.items():
                if repo_path.exists():
                    self.observer.schedule(event_handler, str(repo_path), recursive=True)
                    logger.debug(f"Watching {repo_name} for changes")
            
            self.observer.start()
            logger.info("🔥 Started hot-reload watcher for canonical repositories")
            
        except Exception as e:
            logger.error(f"Failed to start file watcher: {e}")
            self.observer = None
    
    def stop_file_watcher(self) -> None:
        """Stop the file system watcher."""
        if self.observer is not None:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            logger.info("Stopped hot-reload watcher")
    
    def _check_and_reload_on_commit_change(self) -> None:
        """Check if commits changed and reload if necessary."""
        # Get current commit hashes
        new_commit_hashes = self._get_all_commit_hashes()
        
        # Compare with stored hashes
        if new_commit_hashes != self._current_commit_hashes:
            changed_repos = []
            for repo_name in self.repos.keys():
                old_hash = self._current_commit_hashes.get(repo_name, "")
                new_hash = new_commit_hashes.get(repo_name, "")
                if old_hash != new_hash:
                    changed_repos.append(f"{repo_name}({old_hash[:8]}→{new_hash[:8]})")
            
            logger.info(f"📦 Commit hashes changed: {', '.join(changed_repos)}")
            logger.info("🔄 Reloading canonical resources...")
            
            # Clear caches and rescan
            self._cached_resources = {}
            self._cache_timestamp = None
            
            # Rescan repositories (will save new cache)
            self.scan_repositories(force_refresh=True)
            
            logger.info("✅ Resources reloaded after git pull")
    
    def get_structured_resources(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get resources structured by use case and complexity.
        
        Returns:
            Dictionary mapping use cases to structured resources
        """
        from .structured_ingestion import StructuredIngestionEngine
        from .llm_enrichment import LLMEnrichmentEngine
        
        # Get raw resources
        raw_resources = self.get_all_resources()
        
        # Initialize enrichment engine if enabled
        enrichment_engine = None
        try:
            from ..env import get_env_bool
            if get_env_bool("ENABLE_LLM_ENRICHMENT", False):
                enrichment_engine = LLMEnrichmentEngine()
        except Exception:
            pass
        
        # Structure them (with enrichment if available)
        ingestion_engine = StructuredIngestionEngine(enrichment_engine=enrichment_engine)
        structured_resources = ingestion_engine.ingest_resources(raw_resources)
        
        # Convert StructuredResource objects to dictionaries for JSON serialization
        result = {}
        for use_case, resources in structured_resources.items():
            result[use_case] = []
            for resource in resources:
                result[use_case].append({
                    "name": resource.name,
                    "file_path": resource.file_path,
                    "content": resource.content,
                    "file_type": resource.file_type,
                    "use_cases": resource.use_cases,
                    "security_level": resource.security_level.value,
                    "complexity_level": resource.complexity_level.value,
                    "keywords": resource.keywords,
                    "related_patterns": resource.related_patterns,
                    "canonical_hash": resource.canonical_hash,
                    "source_repo": resource.source_repo,
                    "source_commit": resource.source_commit,
                    "summary": resource.summary,
                    "domain_concepts": resource.domain_concepts
                })
        
        return result
    
    def _trigger_enrichment_if_enabled(
        self,
        resources: Dict[str, List[Dict[str, Any]]],
        commit_hashes: Dict[str, str]
    ) -> None:
        """
        Trigger LLM enrichment if enabled (non-blocking).
        
        Args:
            resources: Scanned resources
            commit_hashes: Current commit hashes
        """
        try:
            from ..env import get_env_bool
            if not get_env_bool("ENABLE_LLM_ENRICHMENT", False):
                return
            
            # Import here to avoid circular dependency
            from .llm_enrichment import LLMEnrichmentEngine
            
            enrichment_engine = LLMEnrichmentEngine()
            if not enrichment_engine.enabled:
                return
            
            # Get all resources as flat list
            all_resources = []
            for resource_list in resources.values():
                all_resources.extend(resource_list)
            
            # Trigger enrichment in background (non-blocking)
            # Only enrich new files (not force_all)
            logger.info("Triggering LLM enrichment for new/changed files...")
            enrichment_engine.enrich_resources(all_resources, commit_hashes, force_all=False)
            
        except Exception as e:
            logger.warning(f"Failed to trigger enrichment: {e}")
    
    def get_all_resources(self) -> List[Dict[str, Any]]:
        """
        Get all resources as a flat list.
        
        Returns:
            List of all resource dictionaries
        """
        all_resources = []
        structured_resources = self.scan_repositories()
        
        for resource_type, resources in structured_resources.items():
            all_resources.extend(resources)
        
        return all_resources
