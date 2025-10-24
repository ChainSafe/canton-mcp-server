#!/usr/bin/env python3
"""
Direct test of file scanning from cloned repos
"""

import os
import subprocess
from pathlib import Path

def test_file_scanning():
    """Test scanning cloned repositories for documentation files"""
    
    print("Testing File Scanning from Cloned Repositories")
    print("=" * 50)
    
    # Test paths
    canonical_docs_path = Path("../canonical-daml-docs")
    
    print(f"Canonical docs path: {canonical_docs_path}")
    print(f"Path exists: {canonical_docs_path.exists()}")
    print()
    
    if not canonical_docs_path.exists():
        print("❌ Canonical docs path not found")
        return
    
    # Check each repository
    repos = {
        "daml": canonical_docs_path / "daml",
        "canton": canonical_docs_path / "canton",
        "daml-finance": canonical_docs_path / "daml-finance"
    }
    
    doc_extensions = {".md", ".rst", ".txt", ".daml", ".yaml", ".yml"}
    
    total_files = 0
    
    for repo_name, repo_path in repos.items():
        print(f"Scanning {repo_name} repository...")
        print(f"  Path: {repo_path}")
        print(f"  Exists: {repo_path.exists()}")
        
        if not repo_path.exists():
            print(f"  ❌ Repository not found")
            continue
        
        # Get current commit hash
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            commit_hash = result.stdout.strip()
            print(f"  Commit: {commit_hash[:8]}...")
        except subprocess.CalledProcessError as e:
            print(f"  ❌ Could not get commit hash: {e}")
            continue
        
        # Scan for documentation files
        doc_files = []
        try:
            for file_path in repo_path.rglob("*"):
                if file_path.is_file():
                    file_ext = file_path.suffix.lower()
                    if file_ext in doc_extensions:
                        relative_path = file_path.relative_to(repo_path)
                        doc_files.append(str(relative_path))
            
            print(f"  Found {len(doc_files)} documentation files")
            
            # Show first few files
            for file_path in doc_files[:5]:
                print(f"    - {file_path}")
            if len(doc_files) > 5:
                print(f"    ... and {len(doc_files) - 5} more")
            
            total_files += len(doc_files)
            
        except Exception as e:
            print(f"  ❌ Error scanning repository: {e}")
        
        print()
    
    print(f"Total documentation files found: {total_files}")
    
    if total_files > 0:
        print("✅ File scanning test successful!")
        print("   Ready to serve real canonical documentation files")
    else:
        print("❌ No documentation files found")
        print("   Check if repositories are properly cloned")

if __name__ == "__main__":
    test_file_scanning()
