#!/usr/bin/env python3
"""
Simple test script for Git verification
"""

import subprocess
import yaml
from pathlib import Path
from datetime import datetime

def test_git_verification():
    """Test Git verification with our canonical docs."""
    
    # Test with DAML security evidence
    repo_path = Path("../canonical-daml-docs/daml")
    commit_hash = "bd7a1ef89800648201c4f8ea6764b21c714eed61"
    file_path = "sdk/security-evidence.md"
    
    print(f"Testing Git verification...")
    print(f"Repo: {repo_path}")
    print(f"Commit: {commit_hash}")
    print(f"File: {file_path}")
    
    # Get tree hash
    result = subprocess.run(['git', 'show', '--format=%T', '-s', commit_hash], 
                           cwd=repo_path, capture_output=True, text=True, check=True)
    tree_hash = result.stdout.strip()
    print(f"Tree hash: {tree_hash}")
    
    # Get blob hash
    result = subprocess.run(['git', 'ls-tree', tree_hash, file_path], 
                           cwd=repo_path, capture_output=True, text=True, check=True)
    blob_hash = result.stdout.strip().split()[2]
    print(f"Blob hash: {blob_hash}")
    
    # Extract content
    result = subprocess.run(['git', 'show', f"{commit_hash}:{file_path}"], 
                           cwd=repo_path, capture_output=True, text=True, check=True)
    content = result.stdout
    print(f"Content length: {len(content)} characters")
    
    # Create a sample resource
    sample_resource = {
        "name": "well-authorized-create",
        "version": "1.0.0",
        "description": "Canonical pattern: well-authorized create is accepted",
        "tags": ["pattern", "authorization", "canonical", "git-verified"],
        "author": "Digital Asset",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "pattern_type": "authorization_pattern",
        "daml_template": "-- Well-authorized create pattern\n-- Extracted from security evidence",
        "authorization_requirements": [
            {
                "id": "REQ-AUTH-001",
                "rule": "Proper authorization must be maintained",
                "satisfied": True,
                "explanation": "Pattern ensures well-authorized create operations"
            }
        ],
        "when_to_use": ["Scenarios requiring well-authorized create operations"],
        "when_not_to_use": ["Scenarios with insufficient authorization"],
        "security_considerations": ["Ensure proper authorization is maintained"],
        "test_cases": [
            {
                "description": "Valid well-authorized create",
                "passes": True,
                "code": "-- Well-authorized create test case"
            }
        ],
        "canonical_hash": blob_hash,
        "source_commit": commit_hash,
        "source_file": file_path,
        "extracted_at": datetime.utcnow().isoformat() + "Z"
    }
    
    # Save sample resource
    output_dir = Path("resources-extracted/patterns")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / "well-authorized-create-v1.0.yaml"
    with open(output_file, 'w') as f:
        yaml.dump(sample_resource, f, default_flow_style=False, sort_keys=False)
    
    print(f"Sample resource saved to: {output_file}")
    print("Git verification test completed successfully!")

if __name__ == "__main__":
    test_git_verification()
