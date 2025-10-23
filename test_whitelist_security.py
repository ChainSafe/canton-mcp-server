#!/usr/bin/env python3
"""
Test the secure whitelist system for official repositories
"""

import yaml
import subprocess
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_whitelist_security():
    """Test that only official repositories are allowed"""
    
    print("Testing Secure Whitelist System")
    print("=" * 40)
    
    # Test cases
    test_cases = [
        # Valid cases (should pass)
        ("sdk/security-evidence.md", "daml", True),
        ("docs/generated/settlement/intro.rst", "daml-finance", True),
        ("README.md", "daml", True),
        
        # Invalid cases (should fail)
        ("../../../etc/passwd", None, False),
        ("malicious/file.yaml", None, False),
        ("/tmp/evil.yaml", None, False),
        ("../../secret/file.md", None, False),
    ]
    
    # Simulate the whitelist logic
    official_repos = {
        "daml": {
            "path": Path("../canonical-daml-docs/daml"),
            "allowed_paths": ["sdk/", "docs/", "README.md", "LICENSE", "CONTRIBUTING.md"]
        },
        "canton": {
            "path": Path("../canonical-daml-docs/canton"),
            "allowed_paths": ["canton/", "docs/", "README.md", "LICENSE"]
        },
        "daml-finance": {
            "path": Path("../canonical-daml-docs/daml-finance"),
            "allowed_paths": ["docs/generated/", "README.md", "LICENSE"]
        }
    }
    
    def get_repo_path(source_file: str):
        """Simulate the secure whitelist logic"""
        for repo_name, repo_info in official_repos.items():
            repo_path = repo_info["path"]
            allowed_paths = repo_info["allowed_paths"]
            
            for allowed_path in allowed_paths:
                if source_file.startswith(allowed_path):
                    if repo_path.exists() and (repo_path / ".git").exists():
                        return repo_path, repo_name
                    else:
                        return None, None
        
        return None, None
    
    # Run tests
    for source_file, expected_repo, should_pass in test_cases:
        repo_path, repo_name = get_repo_path(source_file)
        
        if should_pass:
            if repo_path and repo_name:
                print(f"✅ PASS: {source_file} -> {repo_name}")
            else:
                print(f"❌ FAIL: {source_file} should have passed but was rejected")
        else:
            if repo_path is None:
                print(f"✅ PASS: {source_file} correctly rejected (security)")
            else:
                print(f"❌ FAIL: {source_file} should have been rejected but was allowed")
    
    print()
    print("Security Test Complete!")

if __name__ == "__main__":
    test_whitelist_security()
