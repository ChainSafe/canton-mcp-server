# Testing DCAP Performance Updates

This guide shows how to verify that the Canton MCP Server is sending DCAP (Distributed Claude Agent Protocol) performance updates.

## What is DCAP?

DCAP broadcasts tool execution metrics (tool name, execution time, success/failure) via UDP for real-time monitoring dashboards. Messages are sent after each tool execution.

## Prerequisites

- Canton MCP Server running in Docker
- Python 3.10+ on your host machine
- UDP port 10191 available

## Method 1: Direct UDP (Recommended for Testing)

### Step 1: Get Your Host IP Address

```bash
# On macOS
ipconfig getifaddr en0

# On Linux
hostname -I | awk '{print $1}'

# On Windows
ipconfig
# Look for "IPv4 Address" under your active network adapter
```

Let's say your IP is `192.168.1.100` (use your actual IP).

### Step 2: Update Docker Configuration

Edit `docker-compose.yml` and update the DCAP environment variables:

```yaml
services:
  canton-mcp-server:
    environment:
      - DCAP_ENABLED=true
      - DCAP_MULTICAST_IP=192.168.1.100  # Your host IP
      - DCAP_PORT=10191
```

Or set via command line:

```bash
DCAP_MULTICAST_IP=192.168.1.100 docker-compose up -d
```

### Step 3: Restart the Server

```bash
docker-compose restart canton-mcp-server
```

### Step 4: Start the DCAP Listener

In a new terminal on your **host machine** (not in Docker):

```bash
python3 test-dcap-listener.py
```

You should see:

```
🎧 Listening for DCAP messages on 0.0.0.0:10191
   Press Ctrl+C to stop
   Waiting for messages...
```

### Step 5: Trigger Tool Calls

The test container is already making calls, or you can manually trigger one:

```bash
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "validate_daml_business_logic",
      "arguments": {
        "businessIntent": "Test DCAP",
        "damlCode": "template Test with owner: Party where signatory owner"
      }
    }
  }'
```

### Step 6: Verify Messages

You should see output like:

```
╔══════════════════════════════════════════════════════════
║ Message #1 at 2025-10-24 18:00:15
║ From: 172.22.0.2:45678
╠══════════════════════════════════════════════════════════
║ Protocol Version: 2
║ Message Type: perf_update
║ Server ID: canton-mcp
║ Tool: validate_daml_business_logic
║ Execution Time: 23ms
║ Success: ✅
║ Arguments: {
║   "businessIntent": "Test DCAP",
║   "damlCode": "template Test with ..."
║ }
╚══════════════════════════════════════════════════════════
```

## Method 2: Using Multicast (Advanced)

### Step 1: Configure Multicast

```yaml
services:
  canton-mcp-server:
    environment:
      - DCAP_ENABLED=true
      - DCAP_MULTICAST_IP=239.255.0.1  # Multicast address
      - DCAP_PORT=10191
```

### Step 2: Start Listener with Multicast

```bash
python3 test-dcap-listener.py --multicast 239.255.0.1
```

## Troubleshooting

### No Messages Received

1. **Check DCAP is enabled:**
   ```bash
   docker-compose logs canton-mcp-server | grep DCAP
   ```
   
   Should show:
   ```
   INFO  | DCAP (Performance Tracking) - ENABLED by default
   ```

2. **Check IP configuration:**
   ```bash
   docker-compose exec canton-mcp-server env | grep DCAP
   ```
   
   Should show:
   ```
   DCAP_ENABLED=true
   DCAP_MULTICAST_IP=192.168.1.100
   DCAP_PORT=10191
   ```

3. **Check server logs for DCAP messages:**
   Enable debug logging to see DCAP messages:
   
   ```bash
   # Add to docker-compose.yml
   environment:
     - LOG_LEVEL=DEBUG
   ```
   
   Then check logs:
   ```bash
   docker-compose logs canton-mcp-server | grep "DCAP"
   ```

4. **Firewall blocking UDP:**
   - Check if firewall is blocking UDP port 10191
   - On macOS: System Preferences → Security & Privacy → Firewall
   - On Linux: `sudo ufw allow 10191/udp`
   - On Windows: Windows Defender Firewall → Inbound Rules

5. **Docker network issues:**
   Try using `host.docker.internal` instead of your IP:
   ```bash
   DCAP_MULTICAST_IP=host.docker.internal docker-compose up -d
   ```

### "DCAP not enabled - no IP configured"

This means `DCAP_MULTICAST_IP` is empty. Set it to your host IP address.

### UDP Packet Size Issues

If you see truncated messages, the UDP packet exceeded 1472 bytes. The server automatically truncates arguments to prevent this.

## Monitoring Live Traffic

Watch for DCAP messages in real-time:

```bash
# Terminal 1: DCAP listener
python3 test-dcap-listener.py

# Terminal 2: Watch test container logs
docker-compose logs -f mcp-tester

# Terminal 3: Watch server logs
docker-compose logs -f canton-mcp-server
```

## Automated Testing

Check if DCAP is working in CI/CD:

```bash
#!/bin/bash
# Start listener in background
python3 test-dcap-listener.py &
LISTENER_PID=$!

# Wait for it to start
sleep 2

# Make test call
curl -X POST http://localhost:7284/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"get_canonical_resource_overview","arguments":{}}}'

# Wait for DCAP message
sleep 2

# Kill listener
kill $LISTENER_PID

# Check if messages were received
# (implement your own verification logic)
```

## DCAP Message Format

Example DCAP v2 message:

```json
{
  "v": 2,                           // Protocol version
  "ts": 1729792815,                 // Unix timestamp
  "t": "perf_update",               // Message type
  "sid": "canton-mcp",              // Server ID
  "tool": "validate_daml_business_logic",
  "exec_ms": 23,                    // Execution time in milliseconds
  "success": true,                  // Success flag
  "ctx": {
    "args": {                       // Anonymized arguments
      "businessIntent": "Test DCAP",
      "damlCode": "template Test with ..."
    }
  }
}
```

With payment tracking (when x402 is enabled):

```json
{
  "v": 2,
  "ts": 1729792815,
  "t": "perf_update",
  "sid": "canton-mcp",
  "tool": "validate_daml_business_logic",
  "exec_ms": 23,
  "success": true,
  "cost_paid": 0.001,               // Cost in currency units
  "currency": "USDC",               // Currency
  "ctx": {
    "args": { ... }
  }
}
```

## Next Steps

Once DCAP is working:

1. **Connect to a Dashboard:** Point `DCAP_MULTICAST_IP` to your monitoring dashboard's UDP endpoint
2. **Production Monitoring:** Use a dedicated DCAP collector service
3. **Metrics Analysis:** Aggregate metrics to track performance trends
4. **Alert on Failures:** Monitor `success: false` messages

## Additional Resources

- DCAP Protocol Specification: https://dcap.dev (if available)
- Canton MCP Server docs: `/README.md`
- Performance monitoring best practices

