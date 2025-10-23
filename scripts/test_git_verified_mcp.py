#!/usr/bin/env python3
"""
Git-Verified MCP Resource CLI

Test and interact with Git-verified MCP resources
"""

import argparse
import json
import sys
from pathlib import Path

def test_resources_list():
    """Test the resources/list endpoint"""
    print("Testing resources/list endpoint...")
    
    try:
        # Import the handler
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        from canton_mcp_server.handlers.resource_handler import handle_resources_list
        
        # Call the handler
        result = handle_resources_list()
        
        print(f"✅ Found {len(result.resources)} Git-verified resources:")
        print()
        
        for resource in result.resources:
            print(f"URI: {resource.uri}")
            print(f"Name: {resource.name}")
            print(f"Description: {resource.description}")
            
            if hasattr(resource, '_meta') and resource._meta:
                meta = resource._meta
                print(f"Git Hash: {meta.get('canonical_hash', 'unknown')}")
                print(f"Source Commit: {meta.get('source_commit', 'unknown')}")
                print(f"Source File: {meta.get('source_file', 'unknown')}")
                print(f"Extracted At: {meta.get('extracted_at', 'unknown')}")
                print(f"Git Verified: {meta.get('git_verified', False)}")
            
            print("-" * 40)
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing resources/list: {e}")
        return False

def test_resources_read(uri: str):
    """Test the resources/read endpoint"""
    print(f"Testing resources/read endpoint with URI: {uri}")
    
    try:
        # Import the handler
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        from canton_mcp_server.handlers.resource_handler import handle_resources_read
        
        # Call the handler
        result = handle_resources_read(uri)
        
        print(f"✅ Successfully read resource: {uri}")
        print()
        
        # Parse and display content
        content = json.loads(result.contents[0].text)
        
        print("Resource Content:")
        print(json.dumps(content, indent=2))
        
        return True
        
    except ValueError as e:
        print(f"❌ Resource not found: {e}")
        return False
    except Exception as e:
        print(f"❌ Error testing resources/read: {e}")
        return False

def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Test Git-verified MCP resource endpoints"
    )
    
    parser.add_argument(
        "command",
        choices=["list", "read"],
        help="MCP command to test"
    )
    
    parser.add_argument(
        "--uri",
        help="Resource URI for read command (e.g., canton://patterns/well-authorized-create)"
    )
    
    args = parser.parse_args()
    
    print("Git-Verified MCP Resource CLI")
    print("=" * 30)
    print()
    
    if args.command == "list":
        success = test_resources_list()
    elif args.command == "read":
        if not args.uri:
            print("❌ Error: --uri required for read command")
            sys.exit(1)
        success = test_resources_read(args.uri)
    
    if success:
        print()
        print("🎉 Test completed successfully!")
    else:
        print()
        print("❌ Test failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
