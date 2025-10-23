"""
GitHub-Verified Resource Loader

Loads resources with GitHub API verification, eliminating the need for local Git repositories
while maintaining full cryptographic verification.
"""

import yaml
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from .github_verification import get_github_verifier, verify_github_blob
from .resources.validator import get_validator, SchemaValidationError

logger = logging.getLogger(__name__)


class GitHubVerifiedResourceLoader:
    """
    Resource loader that uses GitHub API for Git verification.
    
    This eliminates the need for local Git repositories while maintaining
    full cryptographic verification of canonical resources.
    """
    
    def __init__(self, resources_dir: Path):
        """
        Initialize the GitHub-verified resource loader.
        
        Args:
            resources_dir: Directory containing YAML resource files
        """
        self.resources_dir = resources_dir
        self.validator = get_validator()
        self.github_verifier = get_github_verifier()
        self._resources: Dict[str, Any] = {}
        
        # Validate GitHub API access on initialization
        if not self.github_verifier.validate_official_repos():
            logger.warning("Some official repositories failed GitHub API validation")
    
    def load_resource_file(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Load a single resource file with GitHub API verification.
        
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
            
            # GATE 1: GitHub API verification (authenticity)
            if self._has_git_verification_fields(resource):
                if not self._verify_github_integrity(resource):
                    logger.error(f"GATE 1 FAILED - GitHub API verification failed for {file_path}")
                    return None
                logger.debug(f"GATE 1 PASSED - GitHub API verification successful for {file_path}")
            else:
                logger.warning(f"No Git verification fields found in {file_path}")
                return None
            
            # GATE 2: Documentation content validation (file type filtering)
            if not self._validate_documentation_file_type(resource):
                logger.error(f"GATE 2 FAILED - Not a documentation file: {file_path}")
                return None
            logger.debug(f"GATE 2 PASSED - Documentation file type validation successful for {file_path}")
            
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
    
    def _get_resource_type_from_path(self, file_path: Path) -> str:
        """Determine resource type from file path."""
        # Extract the parent directory name (e.g., "patterns" from "resources/patterns/file.yaml")
        parent_dir = file_path.parent.name
        
        # Map directory names to resource types
        if parent_dir == "patterns":
            return "pattern"
        elif parent_dir == "anti_patterns":
            return "anti_pattern"
        elif parent_dir == "rules":
            return "rule"
        elif parent_dir == "docs":
            return "doc"
        else:
            # Default fallback
            return "pattern"
    
    def _validate_documentation_file_type(self, resource: Dict[str, Any]) -> bool:
        """
        Validate that the resource comes from a documentation file type.
        
        This filters out build files, templates, and non-documentation content
        by checking the source file extension.
        
        Args:
            resource: Resource dictionary with source_file field
            
        Returns:
            True if file type indicates documentation content, False otherwise
        """
        source_file = resource.get("source_file", "")
        
        # Documentation file extensions (actual content)
        doc_extensions = {
            ".md",      # Markdown files
            ".rst",     # reStructuredText files  
            ".txt",     # Plain text files
            ".yaml",    # YAML documentation
            ".yml",     # YAML documentation
            ".json",    # JSON documentation
        }
        
        # Build/template file extensions (filter out)
        build_extensions = {
            ".py",      # Python scripts (Sphinx, build tools)
            ".js",      # JavaScript files
            ".css",     # Stylesheets
            ".html",    # Generated HTML
            ".conf",    # Configuration files
            ".ini",     # Configuration files
            ".toml",    # Configuration files
            ".lock",    # Lock files
            ".log",     # Log files
        }
        
        # Get file extension
        file_ext = Path(source_file).suffix.lower()
        
        # Check if it's a documentation file
        if file_ext in doc_extensions:
            logger.debug(f"File type validation PASSED: {source_file} (extension: {file_ext})")
            return True
        
        # Check if it's a build file (reject)
        if file_ext in build_extensions:
            logger.debug(f"File type validation FAILED: {source_file} (build file: {file_ext})")
            return False
        
        # Special cases for files without extensions
        if not file_ext:
            filename = Path(source_file).name.lower()
            
            # Documentation files without extensions
            if filename in {"readme", "license", "changelog", "contributing", "authors"}:
                logger.debug(f"File type validation PASSED: {source_file} (documentation file)")
                return True
            
            # Build files without extensions
            if filename in {"makefile", "dockerfile", "docker-compose", "sphinx", "conf"}:
                logger.debug(f"File type validation FAILED: {source_file} (build file)")
                return False
        
        # Default: allow files without clear build indicators
        logger.debug(f"File type validation PASSED: {source_file} (unknown extension, allowing)")
        return True
    
    def _verify_github_integrity(self, resource: Dict[str, Any]) -> bool:
        """
        Verify GitHub API integrity of a resource.
        
        Args:
            resource: Resource dictionary with Git verification fields
            
        Returns:
            True if verification succeeds, False otherwise
        """
        canonical_hash = resource["canonical_hash"]
        source_commit = resource["source_commit"]
        source_file = resource["source_file"]
        
        # Verify using GitHub API
        return verify_github_blob(source_file, source_commit, canonical_hash)
    
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
        logger.info(f"Loaded {total_resources} GitHub-verified resources total")
        
        return resources
    
    def _load_resources_from_directory(self, directory: Path) -> List[Dict[str, Any]]:
        """
        Load all resources from a specific directory with GitHub API verification.
        
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
        Verify integrity of all loaded resources using GitHub API.
        
        Returns:
            Dictionary mapping resource types to lists of verification errors
        """
        logger.info("Verifying integrity of all resources with GitHub API verification...")
        
        verification_results = {
            "patterns": [],
            "anti_patterns": [],
            "rules": [],
            "docs": []
        }
        
        all_resources = self.load_all_resources()
        
        for resource_type, resources in all_resources.items():
            for resource in resources:
                # Check Gate 1: GitHub API verification
                if self._has_git_verification_fields(resource):
                    if not self._verify_github_integrity(resource):
                        error_msg = f"GATE 1 FAILED - GitHub API verification failed for {resource.get('name', 'unknown')}"
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
            logger.info("All resources passed both gates (GitHub API verification + Schema validation)")
        else:
            logger.warning(f"GitHub API verification found {total_errors} errors")
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
