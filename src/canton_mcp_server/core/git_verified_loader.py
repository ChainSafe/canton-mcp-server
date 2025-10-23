"""
Simplified Git-Verified Resource Loader

Loads resources with Git integrity verification, eliminating complex schema validation
in favor of cryptographic verification.
"""

import yaml
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from .git_verification import verify_git_blob, GitVerificationError
from .validator import get_validator, SchemaValidationError

logger = logging.getLogger(__name__)


class GitVerifiedResourceLoader:
    """
    Simplified resource loader that uses Git verification for integrity.
    """
    
    def __init__(self, resources_dir: Path, canonical_docs_path: Path):
        """
        Initialize the loader.
        
        Args:
            resources_dir: Directory containing YAML resource files
            canonical_docs_path: Path to canonical documentation repositories
        """
        self.resources_dir = resources_dir
        self.canonical_docs_path = canonical_docs_path
        self.validator = get_validator()
        self._resources: Dict[str, Any] = {}
    
    def load_resource_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Load a single resource file with two-gate validation:
        1. Git verification (authenticity)
        2. Schema validation (documentation quality)
        
        Args:
            file_path: Path to the YAML resource file
            
        Returns:
            Resource dictionary if valid, None if invalid
        """
        try:
            # Load YAML content
            with open(file_path, 'r') as f:
                resource = yaml.safe_load(f)
            
            if not resource:
                logger.warning(f"Empty resource file: {file_path}")
                return None
            
            # GATE 1: Git verification (authenticity)
            if self._has_git_verification_fields(resource):
                if not self._verify_git_integrity(resource):
                    logger.error(f"GATE 1 FAILED - Git verification failed for {file_path}")
                    return None
                logger.debug(f"GATE 1 PASSED - Git verification successful for {file_path}")
            else:
                logger.warning(f"No Git verification fields found in {file_path}")
                return None
            
            # GATE 2: Schema validation (documentation quality)
            try:
                self.validator.validate_resource(resource, file_path)
                logger.debug(f"GATE 2 PASSED - Schema validation successful for {file_path}")
            except SchemaValidationError as e:
                logger.error(f"GATE 2 FAILED - Schema validation failed for {file_path}: {e}")
                return None
            
            logger.info(f"Both gates passed - Successfully loaded resource: {file_path}")
            return resource
            
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing error in {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading resource {file_path}: {e}")
            return None
    
    def _has_git_verification_fields(self, resource: Dict[str, Any]) -> bool:
        """Check if resource has Git verification fields."""
        required_fields = ["canonical_hash", "source_commit", "source_file"]
        return all(field in resource for field in required_fields)
    
    def _verify_git_integrity(self, resource: Dict[str, Any]) -> bool:
        """
        Verify Git integrity of a resource.
        
        Args:
            resource: Resource dictionary with Git verification fields
            
        Returns:
            True if verification succeeds, False otherwise
        """
        canonical_hash = resource["canonical_hash"]
        source_commit = resource["source_commit"]
        source_file = resource["source_file"]
        
        # Determine which repo the file comes from
        repo_path = self._get_repo_path(source_file)
        if not repo_path:
            logger.warning(f"Unknown repository for file: {source_file}")
            return False
        
        # Verify Git blob hash
        return verify_git_blob(repo_path, source_commit, source_file, canonical_hash)
    
    def _get_repo_path(self, source_file: str) -> Optional[Path]:
        """
        Determine which canonical repository a file comes from.
        
        Args:
            source_file: Path to the source file
            
        Returns:
            Path to the repository or None if unknown
        """
        # Simple heuristic based on file path
        if source_file.startswith("sdk/"):
            return self.canonical_docs_path / "daml"
        elif "daml-finance" in source_file or source_file.startswith("docs/generated/"):
            return self.canonical_docs_path / "daml-finance"
        elif source_file.startswith("canton/"):
            return self.canonical_docs_path / "canton"
        else:
            # Default to DAML repo for unknown paths
            return self.canonical_docs_path / "daml"
    
    def load_all_resources(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Load all resources from the resources directory.
        
        Returns:
            Dictionary mapping resource types to lists of resources
        """
        logger.info(f"Loading resources from {self.resources_dir}")
        
        resources = {
            "patterns": [],
            "anti_patterns": [],
            "rules": [],
            "docs": []
        }
        
        # Load resources by type
        for resource_type in resources.keys():
            type_dir = self.resources_dir / resource_type
            if type_dir.exists():
                resources[resource_type] = self._load_resources_from_directory(type_dir)
        
        total_resources = sum(len(resource_list) for resource_list in resources.values())
        logger.info(f"Loaded {total_resources} resources total")
        
        return resources
    
    def _load_resources_from_directory(self, directory: Path) -> List[Dict[str, Any]]:
        """
        Load all resources from a specific directory with two-gate validation.
        
        Args:
            directory: Directory containing resource files
            
        Returns:
            List of loaded resources (only those passing both gates)
        """
        resources = []
        failed_files = []
        
        for file_path in directory.glob("*.yaml"):
            try:
                resource = self.load_resource_file(file_path)
                if resource:
                    resources.append(resource)
                else:
                    failed_files.append(file_path.name)
            except Exception as e:
                logger.error(f"Failed to load {file_path}: {e}")
                failed_files.append(file_path.name)
        
        if failed_files:
            logger.warning(f"Failed to load {len(failed_files)} files from {directory}: {failed_files}")
        
        logger.info(f"Successfully loaded {len(resources)} resources from {directory}")
        return resources
    
    def get_resource_by_name(self, name: str, resource_type: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific resource by name and type.
        
        Args:
            name: Name of the resource
            resource_type: Type of resource (pattern, anti-pattern, rule, doc)
            
        Returns:
            Resource dictionary or None if not found
        """
        all_resources = self.load_all_resources()
        
        if resource_type not in all_resources:
            return None
        
        for resource in all_resources[resource_type]:
            if resource.get("name") == name:
                return resource
        
        return None
    
    def verify_all_resources(self) -> Dict[str, List[str]]:
        """
        Verify integrity of all loaded resources using two-gate validation.
        
        Returns:
            Dictionary mapping resource types to lists of verification errors
        """
        logger.info("Verifying integrity of all resources with two-gate validation...")
        
        verification_results = {
            "patterns": [],
            "anti_patterns": [],
            "rules": [],
            "docs": []
        }
        
        all_resources = self.load_all_resources()
        
        for resource_type, resources in all_resources.items():
            for resource in resources:
                # Check Gate 1: Git verification
                if self._has_git_verification_fields(resource):
                    if not self._verify_git_integrity(resource):
                        error_msg = f"GATE 1 FAILED - Git verification failed for {resource.get('name', 'unknown')}"
                        verification_results[resource_type].append(error_msg)
                        continue
                else:
                    error_msg = f"GATE 1 FAILED - Missing Git verification fields for {resource.get('name', 'unknown')}"
                    verification_results[resource_type].append(error_msg)
                    continue
                
                # Check Gate 2: Schema validation
                try:
                    self.validator.validate_resource(resource, Path(f"dummy/{resource.get('name', 'unknown')}.yaml"))
                except SchemaValidationError as e:
                    error_msg = f"GATE 2 FAILED - Schema validation failed for {resource.get('name', 'unknown')}: {e}"
                    verification_results[resource_type].append(error_msg)
        
        # Log verification results
        total_errors = sum(len(errors) for errors in verification_results.values())
        if total_errors == 0:
            logger.info("All resources passed both gates (Git verification + Schema validation)")
        else:
            logger.warning(f"Two-gate validation found {total_errors} errors")
            for resource_type, errors in verification_results.items():
                if errors:
                    logger.warning(f"  {resource_type}: {len(errors)} errors")
        
        return verification_results
    
    def reload_resources(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Reload all resources (useful for hot-reload scenarios).
        
        Returns:
            Dictionary mapping resource types to lists of resources
        """
        logger.info("Reloading all resources...")
        self._resources.clear()
        return self.load_all_resources()
