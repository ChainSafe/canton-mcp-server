#!/usr/bin/env python3
"""
Direct test of GitHub API verification
"""

import requests
import yaml
from pathlib import Path

def test_github_api_direct():
    """Test GitHub API directly without importing the full module"""
    
    print("Testing GitHub API Direct Access")
    print("=" * 35)
    
    # Load our sample resource
    resource_file = Path("resources/patterns/well-authorized-create-v1.0.yaml")
    
    if not resource_file.exists():
        print(f"❌ Resource file not found: {resource_file}")
        return
    
    with open(resource_file, 'r') as f:
        resource = yaml.safe_load(f)
    
    source_file = resource["source_file"]
    source_commit = resource["source_commit"]
    canonical_hash = resource["canonical_hash"]
    
    print(f"Testing file: {source_file}")
    print(f"Commit: {source_commit}")
    print(f"Expected hash: {canonical_hash}")
    print()
    
    # Test GitHub API access
    print("1. Testing GitHub API access...")
    
    # Determine repository
    if source_file.startswith("sdk/"):
        owner = "digital-asset"
        repo = "daml"
    else:
        owner = "digital-asset"
        repo = "daml"
    
    print(f"   Repository: {owner}/{repo}")
    
    # Fetch file content from GitHub API
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{source_file}"
    params = {"ref": source_commit}
    
    print(f"   URL: {url}")
    print(f"   Params: {params}")
    
    try:
        response = requests.get(url, params=params, timeout=30)
        print(f"   Status code: {response.status_code}")
        
        if response.status_code == 200:
            file_data = response.json()
            actual_hash = file_data.get("sha")
            
            print(f"   ✅ GitHub API access successful")
            print(f"   Actual hash: {actual_hash}")
            print(f"   Expected hash: {canonical_hash}")
            
            if actual_hash == canonical_hash:
                print(f"   ✅ Hash verification PASSED")
            else:
                print(f"   ❌ Hash verification FAILED")
                
            # Test content retrieval
            content = file_data.get("content", "")
            if content:
                import base64
                try:
                    decoded_content = base64.b64decode(content).decode('utf-8')
                    print(f"   ✅ Content retrieved: {len(decoded_content)} characters")
                    print(f"   First 100 chars: {decoded_content[:100]}...")
                except Exception as e:
                    print(f"   ❌ Content decode error: {e}")
            
        else:
            print(f"   ❌ GitHub API error: {response.status_code}")
            print(f"   Response: {response.text}")
            
    except Exception as e:
        print(f"   ❌ Request error: {e}")
    
    print()
    print("🎉 GitHub API direct test completed!")

if __name__ == "__main__":
    test_github_api_direct()
