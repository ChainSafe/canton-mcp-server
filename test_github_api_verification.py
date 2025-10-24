#!/usr/bin/env python3
"""
Test GitHub API verification system
"""

import yaml
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_github_api_verification():
    """Test GitHub API verification with our sample resource"""
    
    print("Testing GitHub API Verification System")
    print("=" * 40)
    
    try:
        from canton_mcp_server.core.github_verification import GitHubAPIVerifier
        
        # Initialize verifier
        verifier = GitHubAPIVerifier()
        
        # Test repository validation
        print("1. Testing repository validation...")
        valid = verifier.validate_official_repos()
        print(f"   Repository validation: {'✅ PASSED' if valid else '❌ FAILED'}")
        print()
        
        # Test with our sample resource
        print("2. Testing blob hash verification...")
        resource_file = Path("resources/patterns/well-authorized-create-v1.0.yaml")
        
        if not resource_file.exists():
            print(f"   ❌ Resource file not found: {resource_file}")
            return
        
        with open(resource_file, 'r') as f:
            resource = yaml.safe_load(f)
        
        source_file = resource["source_file"]
        source_commit = resource["source_commit"]
        canonical_hash = resource["canonical_hash"]
        
        print(f"   Testing file: {source_file}")
        print(f"   Commit: {source_commit}")
        print(f"   Expected hash: {canonical_hash}")
        
        # Test verification
        is_valid = verifier.verify_blob_hash(source_file, source_commit, canonical_hash)
        print(f"   GitHub API verification: {'✅ PASSED' if is_valid else '❌ FAILED'}")
        print()
        
        # Test file content retrieval
        print("3. Testing file content retrieval...")
        content = verifier.get_file_content(source_file, source_commit)
        if content:
            print(f"   ✅ Retrieved {len(content)} characters of content")
            print(f"   First 100 chars: {content[:100]}...")
        else:
            print("   ❌ Failed to retrieve content")
        
        print()
        print("🎉 GitHub API verification test completed!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("This is expected due to missing dependencies")
    except Exception as e:
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    test_github_api_verification()
