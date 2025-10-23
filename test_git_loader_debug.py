#!/usr/bin/env python3
"""
Test Git-verified loader directly
"""

import yaml
import subprocess
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_git_loader():
    """Test the Git-verified loader functionality"""
    
    print("Testing Git-Verified Loader")
    print("=" * 30)
    
    # Test paths
    resources_dir = Path("resources")
    canonical_docs_path = Path("../canonical-daml-docs")
    
    print(f"Resources dir: {resources_dir}")
    print(f"Canonical docs: {canonical_docs_path}")
    print()
    
    # Check if resources exist
    if not resources_dir.exists():
        print("❌ Resources directory not found")
        return
    
    # Check each resource type
    resource_types = ["patterns", "anti_patterns", "rules", "docs"]
    
    for resource_type in resource_types:
        type_dir = resources_dir / resource_type
        if type_dir.exists():
            print(f"📁 {resource_type}/ directory exists")
            
            # List files
            yaml_files = list(type_dir.glob("*.yaml"))
            print(f"   Found {len(yaml_files)} YAML files:")
            
            for yaml_file in yaml_files:
                print(f"   - {yaml_file.name}")
                
                # Check if it has Git verification fields
                try:
                    with open(yaml_file, 'r') as f:
                        resource = yaml.safe_load(f)
                    
                    has_git_fields = all(field in resource for field in ["canonical_hash", "source_commit", "source_file"])
                    print(f"     Git fields: {'✅' if has_git_fields else '❌'}")
                    
                    if has_git_fields:
                        print(f"     Hash: {resource.get('canonical_hash', 'unknown')}")
                        print(f"     Commit: {resource.get('source_commit', 'unknown')}")
                        print(f"     File: {resource.get('source_file', 'unknown')}")
                        
                        # Test Git verification
                        source_file = resource["source_file"]
                        source_commit = resource["source_commit"]
                        canonical_hash = resource["canonical_hash"]
                        
                        # Determine repo path
                        if source_file.startswith("sdk/"):
                            repo_path = canonical_docs_path / "daml"
                        elif source_file.startswith("docs/generated/"):
                            repo_path = canonical_docs_path / "daml-finance"
                        else:
                            repo_path = canonical_docs_path / "daml"
                        
                        if repo_path.exists():
                            print(f"     Repo path: {repo_path} ✅")
                            
                            # Test Git verification
                            try:
                                # Get tree hash
                                result = subprocess.run(['git', 'show', '--format=%T', '-s', source_commit], 
                                                       cwd=repo_path, capture_output=True, text=True, check=True)
                                tree_hash = result.stdout.strip()
                                
                                # Get blob hash
                                result = subprocess.run(['git', 'ls-tree', tree_hash, source_file], 
                                                       cwd=repo_path, capture_output=True, text=True, check=True)
                                actual_hash = result.stdout.strip().split()[2]
                                
                                if actual_hash == canonical_hash:
                                    print(f"     Git verification: ✅ PASSED")
                                else:
                                    print(f"     Git verification: ❌ FAILED (expected {canonical_hash}, got {actual_hash})")
                                    
                            except Exception as e:
                                print(f"     Git verification: ❌ ERROR - {e}")
                        else:
                            print(f"     Repo path: {repo_path} ❌ NOT FOUND")
                    
                except Exception as e:
                    print(f"     Error reading file: {e}")
                
                print()
        else:
            print(f"📁 {resource_type}/ directory not found")

if __name__ == "__main__":
    test_git_loader()
