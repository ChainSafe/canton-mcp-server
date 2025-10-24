"""
Git Verification Utilities

Provides functions for verifying Git blob hashes and extracting content
from canonical repositories with integrity verification.
"""

import hashlib
import subprocess
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class GitVerificationError(Exception):
    """Raised when Git verification fails"""
    pass


def get_git_blob_hash(repo_path: Path, commit_hash: str, file_path: str) -> Optional[str]:
    """
    Get the Git blob hash for a specific file in a commit.
    
    Args:
        repo_path: Path to the Git repository
        commit_hash: Git commit hash
        file_path: Path to the file within the repository
        
    Returns:
        Git blob hash (40-character SHA-1) or None if not found
        
    Raises:
        GitVerificationError: If Git command fails
    """
    try:
        # Get the tree hash for the commit
        result = subprocess.run(
            ["git", "show", "--format=%T", "-s", commit_hash],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        tree_hash = result.stdout.strip()
        
        # Get the blob hash for the specific file
        result = subprocess.run(
            ["git", "ls-tree", tree_hash, file_path],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        
        if not result.stdout.strip():
            return None
            
        # Parse the output: "100644 blob <hash> <file_path>"
        parts = result.stdout.strip().split()
        if len(parts) >= 3 and parts[1] == "blob":
            return parts[2]
        
        return None
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Git command failed: {e}")
        raise GitVerificationError(f"Failed to get blob hash: {e}")


def verify_git_blob(repo_path: Path, commit_hash: str, file_path: str, expected_hash: str) -> bool:
    """
    Verify that a file's content matches the expected Git blob hash.
    
    Args:
        repo_path: Path to the Git repository
        commit_hash: Git commit hash
        file_path: Path to the file within the repository
        expected_hash: Expected Git blob hash
        
    Returns:
        True if verification succeeds, False otherwise
    """
    try:
        # Get the actual blob hash
        actual_hash = get_git_blob_hash(repo_path, commit_hash, file_path)
        
        if actual_hash is None:
            logger.warning(f"File {file_path} not found in commit {commit_hash}")
            return False
            
        # Compare hashes
        if actual_hash == expected_hash:
            logger.debug(f"Git verification successful for {file_path}")
            return True
        else:
            logger.warning(f"Git verification failed for {file_path}: expected {expected_hash}, got {actual_hash}")
            return False
            
    except GitVerificationError:
        return False


def extract_file_content(repo_path: Path, commit_hash: str, file_path: str) -> Optional[str]:
    """
    Extract file content from a specific Git commit.
    
    Args:
        repo_path: Path to the Git repository
        commit_hash: Git commit hash
        file_path: Path to the file within the repository
        
    Returns:
        File content as string or None if not found
        
    Raises:
        GitVerificationError: If Git command fails
    """
    try:
        result = subprocess.run(
            ["git", "show", f"{commit_hash}:{file_path}"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        
        return result.stdout
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to extract file content: {e}")
        raise GitVerificationError(f"Failed to extract content from {file_path}: {e}")


def get_current_commit_hash(repo_path: Path) -> Optional[str]:
    """
    Get the current commit hash of the repository.
    
    Args:
        repo_path: Path to the Git repository
        
    Returns:
        Current commit hash or None if not a Git repository
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        
        return result.stdout.strip()
        
    except subprocess.CalledProcessError:
        return None


def sync_canonical_repos(canonical_docs_path: Path) -> Dict[str, str]:
    """
    Sync canonical documentation repositories to latest commits.
    
    Args:
        canonical_docs_path: Path to directory containing canonical repos
        
    Returns:
        Dictionary mapping repo names to their latest commit hashes
        
    Raises:
        GitVerificationError: If sync fails
    """
    repos = ["daml", "canton", "daml-finance"]
    commit_hashes = {}
    
    for repo_name in repos:
        repo_path = canonical_docs_path / repo_name
        
        if not repo_path.exists():
            logger.warning(f"Repository {repo_name} not found at {repo_path}")
            continue
            
        try:
            # Pull latest changes
            subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get current commit hash
            commit_hash = get_current_commit_hash(repo_path)
            if commit_hash:
                commit_hashes[repo_name] = commit_hash
                logger.info(f"Synced {repo_name} to commit {commit_hash}")
            else:
                logger.error(f"Failed to get commit hash for {repo_name}")
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to sync {repo_name}: {e}")
            raise GitVerificationError(f"Failed to sync repository {repo_name}: {e}")
    
    return commit_hashes


def create_git_verified_resource(
    repo_path: Path,
    commit_hash: str,
    file_path: str,
    resource_type: str,
    extracted_at: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a Git-verified resource with integrity information.
    
    Args:
        repo_path: Path to the Git repository
        commit_hash: Git commit hash
        file_path: Path to the source file
        resource_type: Type of resource (pattern, anti-pattern, rule, doc)
        extracted_at: ISO timestamp when extracted (defaults to now)
        
    Returns:
        Dictionary with Git verification metadata
        
    Raises:
        GitVerificationError: If verification fails
    """
    # Get blob hash
    blob_hash = get_git_blob_hash(repo_path, commit_hash, file_path)
    if blob_hash is None:
        raise GitVerificationError(f"File {file_path} not found in commit {commit_hash}")
    
    # Extract content
    content = extract_file_content(repo_path, commit_hash, file_path)
    if content is None:
        raise GitVerificationError(f"Failed to extract content from {file_path}")
    
    # Set extraction timestamp
    if extracted_at is None:
        extracted_at = datetime.utcnow().isoformat() + "Z"
    
    return {
        "canonical_hash": blob_hash,
        "source_commit": commit_hash,
        "source_file": file_path,
        "extracted_at": extracted_at,
        "content": content,
        "resource_type": resource_type
    }
