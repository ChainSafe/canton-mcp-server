#!/usr/bin/env python3
"""
DCAP UDP Listener - Test Tool

Listens for DCAP performance update messages on UDP port 10191.
Use this to verify that the Canton MCP Server is sending DCAP messages.
"""

import json
import socket
import sys
from datetime import datetime


def listen_for_dcap(port=10191, multicast_group=None):
    """
    Listen for DCAP messages on UDP port.
    
    Args:
        port: UDP port to listen on (default: 10191)
        multicast_group: Optional multicast group IP (e.g., "239.255.0.1")
    """
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    # Bind to the port
    if multicast_group:
        # For multicast, bind to the multicast group
        sock.bind((multicast_group, port))
        # Join multicast group
        mreq = socket.inet_aton(multicast_group) + socket.inet_aton('0.0.0.0')
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        print(f"🎧 Listening for DCAP multicast messages on {multicast_group}:{port}")
    else:
        # For direct UDP, bind to all interfaces
        sock.bind(('0.0.0.0', port))
        print(f"🎧 Listening for DCAP messages on 0.0.0.0:{port}")
    
    print("   Press Ctrl+C to stop")
    print("   Waiting for messages...\n")
    
    message_count = 0
    
    try:
        while True:
            # Receive data
            data, addr = sock.recvfrom(2048)
            message_count += 1
            
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            try:
                # Parse JSON message
                message = json.loads(data.decode('utf-8'))
                
                # Pretty print the message
                print(f"╔══════════════════════════════════════════════════════════")
                print(f"║ Message #{message_count} at {timestamp}")
                print(f"║ From: {addr[0]}:{addr[1]}")
                print(f"╠══════════════════════════════════════════════════════════")
                print(f"║ Protocol Version: {message.get('v', 'N/A')}")
                print(f"║ Message Type: {message.get('t', 'N/A')}")
                print(f"║ Server ID: {message.get('sid', 'N/A')}")
                print(f"║ Tool: {message.get('tool', 'N/A')}")
                print(f"║ Execution Time: {message.get('exec_ms', 'N/A')}ms")
                print(f"║ Success: {'✅' if message.get('success') else '❌'}")
                
                if message.get('cost_paid'):
                    print(f"║ Cost: {message.get('cost_paid')} {message.get('currency', 'USDC')}")
                
                if message.get('ctx', {}).get('args'):
                    print(f"║ Arguments: {json.dumps(message['ctx']['args'], indent=2)}")
                
                print(f"╚══════════════════════════════════════════════════════════\n")
                
            except json.JSONDecodeError:
                print(f"⚠️  Received non-JSON data from {addr}: {data[:100]}")
            except Exception as e:
                print(f"⚠️  Error parsing message: {e}")
                print(f"   Raw data: {data[:200]}")
    
    except KeyboardInterrupt:
        print(f"\n\n✅ Received {message_count} DCAP message(s)")
        print("   Shutting down listener...")
        sock.close()
        sys.exit(0)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Listen for DCAP performance updates")
    parser.add_argument(
        "-p", "--port",
        type=int,
        default=10191,
        help="UDP port to listen on (default: 10191)"
    )
    parser.add_argument(
        "-m", "--multicast",
        type=str,
        help="Multicast group IP (e.g., 239.255.0.1)"
    )
    
    args = parser.parse_args()
    
    listen_for_dcap(port=args.port, multicast_group=args.multicast)

