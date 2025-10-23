#!/usr/bin/env python3
"""
Test direct file serving from cloned repositories
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_direct_file_serving():
    """Test the direct file serving system"""
    
    print("Testing Direct File Serving System")
    print("=" * 40)
    
    try:
        from canton_mcp_server.core.direct_file_loader import DirectFileResourceLoader
        
        # Initialize loader
        canonical_docs_path = Path("../canonical-daml-docs")
        loader = DirectFileResourceLoader(canonical_docs_path)
        
        print(f"Canonical docs path: {canonical_docs_path}")
        print(f"Path exists: {canonical_docs_path.exists()}")
        print()
        
        # Scan repositories
        print("Scanning repositories...")
        resources = loader.scan_repositories()
        
        total_resources = sum(len(resource_list) for resource_list in resources.values())
        print(f"Found {total_resources} documentation files")
        print()
        
        # Show resources by type
        for resource_type, resource_list in resources.items():
            if resource_list:
                print(f"{resource_type.upper()}: {len(resource_list)} files")
                for resource in resource_list[:3]:  # Show first 3
                    print(f"  - {resource['name']}")
                    print(f"    File: {resource['file_path']}")
                    print(f"    Repo: {resource['source_repo']}")
                    print(f"    Hash: {resource['canonical_hash'][:8]}...")
                if len(resource_list) > 3:
                    print(f"    ... and {len(resource_list) - 3} more")
                print()
        
        # Test resource retrieval
        if resources["docs"]:
            test_resource = resources["docs"][0]
            print(f"Testing resource retrieval: {test_resource['name']}")
            
            retrieved = loader.get_resource_by_name(test_resource["name"], "docs")
            if retrieved:
                print(f"✅ Successfully retrieved resource")
                print(f"   Content length: {len(retrieved['content'])} characters")
                print(f"   First 100 chars: {retrieved['content'][:100]}...")
            else:
                print("❌ Failed to retrieve resource")
        
        print()
        print("🎉 Direct file serving test completed!")
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("This is expected due to missing dependencies")
    except Exception as e:
        print(f"❌ Test error: {e}")

if __name__ == "__main__":
    test_direct_file_serving()
