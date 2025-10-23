"""
GitHub API Verification Client

Provides Git blob hash verification using GitHub API instead of local Git repositories.
Eliminates the need for local clones while maintaining cryptographic verification.
"""

import requests
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class GitHubRepo:
    """GitHub repository configuration."""
    owner: str
    repo: str
    display_name: str


class GitHubAPIVerifier:
    """
    Verifies Git blob hashes using GitHub API.
    
    This eliminates the need for local Git repositories while maintaining
    full cryptographic verification of canonical resources.
    """
    
    def __init__(self):
        """Initialize the GitHub API verifier."""
        self.base_url = "https://api.github.com"
        self.session = requests.Session()
        
        # Official repositories configuration
        self.official_repos = {
            "daml": GitHubRepo("digital-asset", "daml", "DAML"),
            "canton": GitHubRepo("DACH-NY", "canton", "Canton"),
            "daml-finance": GitHubRepo("digital-asset", "daml-finance", "DAML Finance")
        }
        
        # Set user agent for GitHub API
        self.session.headers.update({
            "User-Agent": "Canton-MCP-Server/1.0",
            "Accept": "application/vnd.github.v3+json"
        })
    
    def get_repo_for_file(self, source_file: str) -> Optional[GitHubRepo]:
        """
        Determine which official repository a file comes from.
        
        Args:
            source_file: Path to the source file
            
        Returns:
            GitHubRepo if file is from an official repo, None otherwise
        """
        # Map file paths to repositories
        if source_file.startswith("sdk/") or source_file.startswith("docs/"):
            return self.official_repos["daml"]
        elif "daml-finance" in source_file or source_file.startswith("docs/generated/"):
            return self.official_repos["daml-finance"]
        elif source_file.startswith("canton/"):
            return self.official_repos["canton"]
        
        # Default to DAML repo for unknown paths
        return self.official_repos["daml"]
    
    def verify_blob_hash(self, source_file: str, commit_hash: str, expected_hash: str) -> bool:
        """
        Verify Git blob hash using GitHub API.
        
        Args:
            source_file: Path to the file in the repository
            commit_hash: Git commit hash
            expected_hash: Expected blob hash
            
        Returns:
            True if verification succeeds, False otherwise
        """
        try:
            # Get repository info
            repo = self.get_repo_for_file(source_file)
            if not repo:
                logger.error(f"No official repository found for file: {source_file}")
                return False
            
            # Fetch file content from specific commit
            url = f"{self.base_url}/repos/{repo.owner}/{repo.repo}/contents/{source_file}"
            params = {"ref": commit_hash}
            
            logger.debug(f"Fetching file from GitHub API: {url} (commit: {commit_hash})")
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 404:
                logger.error(f"File not found in GitHub: {source_file} at commit {commit_hash}")
                return False
            
            if response.status_code != 200:
                logger.error(f"GitHub API error: {response.status_code} - {response.text}")
                return False
            
            # Parse response
            file_data = response.json()
            actual_hash = file_data.get("sha")
            
            if not actual_hash:
                logger.error(f"No SHA hash in GitHub API response for {source_file}")
                return False
            
            # Verify hash
            is_valid = (actual_hash == expected_hash)
            
            if is_valid:
                logger.debug(f"✅ GitHub API verification passed for {source_file}")
                logger.debug(f"   Expected: {expected_hash}")
                logger.debug(f"   Actual:   {actual_hash}")
            else:
                logger.error(f"❌ GitHub API verification failed for {source_file}")
                logger.error(f"   Expected: {expected_hash}")
                logger.error(f"   Actual:   {actual_hash}")
            
            return is_valid
            
        except requests.RequestException as e:
            logger.error(f"GitHub API request failed for {source_file}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error verifying {source_file}: {e}")
            return False
    
    def get_file_content(self, source_file: str, commit_hash: str) -> Optional[str]:
        """
        Get file content from GitHub API.
        
        Args:
            source_file: Path to the file in the repository
            commit_hash: Git commit hash
            
        Returns:
            File content as string, or None if failed
        """
        try:
            repo = self.get_repo_for_file(source_file)
            if not repo:
                return None
            
            url = f"{self.base_url}/repos/{repo.owner}/{repo.repo}/contents/{source_file}"
            params = {"ref": commit_hash}
            
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch file content: {response.status_code}")
                return None
            
            file_data = response.json()
            content = file_data.get("content", "")
            
            # GitHub API returns base64-encoded content
            import base64
            try:
                decoded_content = base64.b64decode(content).decode('utf-8')
                return decoded_content
            except Exception as e:
                logger.error(f"Failed to decode base64 content: {e}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching file content: {e}")
            return None
    
    def validate_official_repos(self) -> bool:
        """
        Validate that all official repositories are accessible via GitHub API.
        
        Returns:
            True if all repos are accessible, False otherwise
        """
        logger.info("Validating official repositories via GitHub API...")
        
        all_valid = True
        
        for repo_name, repo in self.official_repos.items():
            try:
                # Test API access by fetching repository info
                url = f"{self.base_url}/repos/{repo.owner}/{repo.repo}"
                response = self.session.get(url, timeout=10)
                
                if response.status_code == 200:
                    repo_data = response.json()
                    logger.info(f"✅ Official repo {repo_name} accessible: {repo.display_name}")
                    logger.debug(f"   URL: {repo_data.get('html_url', 'unknown')}")
                    logger.debug(f"   Default branch: {repo_data.get('default_branch', 'unknown')}")
                else:
                    logger.error(f"❌ Official repo {repo_name} not accessible: {response.status_code}")
                    all_valid = False
                    
            except Exception as e:
                logger.error(f"❌ Error validating repo {repo_name}: {e}")
                all_valid = False
        
        if all_valid:
            logger.info("All official repositories validated successfully via GitHub API")
        else:
            logger.error("Some official repositories failed validation")
        
        return all_valid


# Global instance
_github_verifier: Optional[GitHubAPIVerifier] = None


def get_github_verifier() -> GitHubAPIVerifier:
    """Get or create the global GitHub API verifier."""
    global _github_verifier
    
    if _github_verifier is None:
        _github_verifier = GitHubAPIVerifier()
    
    return _github_verifier


def verify_github_blob(source_file: str, commit_hash: str, expected_hash: str) -> bool:
    """
    Verify Git blob hash using GitHub API.
    
    Args:
        source_file: Path to the file in the repository
        commit_hash: Git commit hash
        expected_hash: Expected blob hash
        
    Returns:
        True if verification succeeds, False otherwise
    """
    verifier = get_github_verifier()
    return verifier.verify_blob_hash(source_file, commit_hash, expected_hash)
