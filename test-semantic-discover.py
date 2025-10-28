#!/usr/bin/env python3
"""
Quick test script for DCAP semantic_discover broadcasting.

This script directly calls the broadcast_all_tools function to verify
the implementation works correctly without starting the full server.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Set minimal required env vars for testing
os.environ["DCAP_ENABLED"] = "true"
os.environ["DCAP_MULTICAST_IP"] = "127.0.0.1"  # Localhost for testing
os.environ["DCAP_PORT"] = "10191"
os.environ["DCAP_SERVER_ID"] = "canton-mcp-test"
os.environ["DCAP_SERVER_URL"] = "http://localhost:7284/mcp"

def main():
    print("=" * 60)
    print("DCAP semantic_discover Broadcasting Test")
    print("=" * 60)
    
    # Import after setting env vars
    from canton_mcp_server.core.dcap import broadcast_all_tools, is_dcap_enabled
    from canton_mcp_server.payment_handler import PaymentHandler
    
    print(f"\n✓ DCAP enabled: {is_dcap_enabled()}")
    print(f"✓ Target: {os.environ['DCAP_MULTICAST_IP']}:{os.environ['DCAP_PORT']}")
    print(f"✓ Server URL: {os.environ['DCAP_SERVER_URL']}")
    print(f"✓ Server ID: {os.environ['DCAP_SERVER_ID']}")
    
    # Initialize payment handler (disabled for test)
    payment_handler = PaymentHandler()
    
    print("\n" + "-" * 60)
    print("Broadcasting all tools...")
    print("-" * 60 + "\n")
    
    # Broadcast all tools
    broadcast_all_tools(
        server_url=os.environ["DCAP_SERVER_URL"],
        payment_handler=payment_handler
    )
    
    print("\n" + "=" * 60)
    print("Test complete!")
    print("=" * 60)
    print("\nTo listen for these messages, run:")
    print("  python test-dcap-listener.py")
    print("\nOr check the relay WebSocket:")
    print("  wscat -c ws://159.89.110.236:10191/raw")

if __name__ == "__main__":
    main()

