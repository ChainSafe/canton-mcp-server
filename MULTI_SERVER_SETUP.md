# Multi-Server MCP Setup

This guide explains the multi-server Canton MCP setup for load distribution and DCAP monitoring.

## Overview

The Docker setup now includes **3 independent MCP server instances**, each with:
- Unique **DCAP Server ID** for tracking in monitoring dashboards
- Separate **port** for independent access
- Shared **code base** (hot-reload applies to all)
- Individual **DCAP performance metrics**

## Server Configuration

| Server | Container Name | Port | DCAP Server ID | DCAP Server Name |
|--------|---------------|------|----------------|------------------|
| Server 1 | `canton-mcp-server` | 7284 | `canton-mcp-1` | Canton MCP Server 1 |
| Server 2 | `canton-mcp-server-2` | 7285 | `canton-mcp-2` | Canton MCP Server 2 |
| Server 3 | `canton-mcp-server-3` | 7286 | `canton-mcp-3` | Canton MCP Server 3 |

## Usage

### Start All Servers

```bash
docker-compose up -d
```

This starts:
- 3 MCP server instances
- 1 test container (randomly calls all 3 servers)

### Access Individual Servers

```bash
# Server 1
curl http://localhost:7284/health

# Server 2
curl http://localhost:7285/health

# Server 3
curl http://localhost:7286/health
```

### Start Specific Servers Only

```bash
# Start only server 1
docker-compose up -d canton-mcp-server

# Start servers 1 and 2
docker-compose up -d canton-mcp-server canton-mcp-server-2

# Start all servers but not the tester
docker-compose up -d canton-mcp-server canton-mcp-server-2 canton-mcp-server-3
```

### Stop Specific Servers

```bash
# Stop server 2
docker-compose stop canton-mcp-server-2

# Restart server 3
docker-compose restart canton-mcp-server-3
```

## DCAP Monitoring

Each server sends performance updates with its unique server ID to `159.89.110.236:10191`.

### DCAP Message Format

Server 1 sends:
```json
{
  "v": 2,
  "sid": "canton-mcp-1",
  "tool": "validate_daml_business_logic",
  "exec_ms": 23,
  "success": true,
  ...
}
```

Server 2 sends:
```json
{
  "v": 2,
  "sid": "canton-mcp-2",
  "tool": "debug_authorization_failure",
  "exec_ms": 15,
  "success": true,
  ...
}
```

### Benefits for Monitoring

- **Per-server metrics**: Track performance of each instance separately
- **Load distribution**: See which server handles more requests
- **Failure isolation**: Identify if one server has issues
- **Performance comparison**: Compare exec times across servers

## Test Container Load Distribution

The `mcp-tester` container randomly distributes calls across all 3 servers:

```bash
# View which servers are being called
docker-compose logs -f mcp-tester
```

Example output:
```
[#1] Calling canton-mcp-server → suggest_authorization_pattern
   ✅ Tool executed successfully
[#2] Calling canton-mcp-server-3 → debug_authorization_failure
   ✅ Tool executed successfully
[#3] Calling canton-mcp-server-2 → validate_daml_business_logic
   ✅ Tool executed successfully
```

## Scaling Configuration

### Add More Servers

To add a 4th server, edit `docker-compose.yml`:

```yaml
  canton-mcp-server-4:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: canton-mcp-server-4
    ports:
      - "7287:7284"
    volumes:
      - ./src:/app/src:ro
    environment:
      - CANTON_HOT_RELOAD=true
      - MCP_SERVER_URL=http://localhost:7287
      - DCAP_ENABLED=true
      - DCAP_MULTICAST_IP=159.89.110.236
      - DCAP_PORT=10191
      - DCAP_SERVER_ID=canton-mcp-4
      - DCAP_SERVER_NAME=Canton MCP Server 4
      - X402_ENABLED=false
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:7284/health').read()"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s
    networks:
      - canton-network
```

Then update the tester:

```yaml
  mcp-tester:
    depends_on:
      - canton-mcp-server
      - canton-mcp-server-2
      - canton-mcp-server-3
      - canton-mcp-server-4
    environment:
      - MCP_SERVER_URLS=http://canton-mcp-server:7284/mcp,http://canton-mcp-server-2:7284/mcp,http://canton-mcp-server-3:7284/mcp,http://canton-mcp-server-4:7284/mcp
```

### Reduce to Single Server

To use just one server, either:

1. **Stop extra servers:**
   ```bash
   docker-compose stop canton-mcp-server-2 canton-mcp-server-3
   ```

2. **Update tester config:**
   ```bash
   docker-compose exec mcp-tester sh -c 'export MCP_SERVER_URLS=http://canton-mcp-server:7284/mcp'
   docker-compose restart mcp-tester
   ```

## Load Balancing (External)

For production load balancing, use a reverse proxy:

### Nginx Example

```nginx
upstream mcp_servers {
    server localhost:7284;
    server localhost:7285;
    server localhost:7286;
}

server {
    listen 7280;
    
    location /mcp {
        proxy_pass http://mcp_servers;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

Then access via: `http://localhost:7280/mcp`

### HAProxy Example

```haproxy
frontend mcp_frontend
    bind *:7280
    default_backend mcp_servers

backend mcp_servers
    balance roundrobin
    server server1 localhost:7284 check
    server server2 localhost:7285 check
    server server3 localhost:7286 check
```

## Monitoring

### Check All Server Status

```bash
docker-compose ps
```

### View All Server Logs

```bash
# All servers combined
docker-compose logs -f canton-mcp-server canton-mcp-server-2 canton-mcp-server-3

# Specific server
docker-compose logs -f canton-mcp-server-2

# Last 50 lines from all
docker-compose logs --tail 50 canton-mcp-server canton-mcp-server-2 canton-mcp-server-3
```

### Health Check All Servers

```bash
#!/bin/bash
for port in 7284 7285 7286; do
    echo "Checking localhost:$port..."
    curl -s http://localhost:$port/health | python3 -m json.tool
    echo ""
done
```

### DCAP Statistics Per Server

On your DCAP dashboard at `159.89.110.236`, you can now:

- Filter by `sid`: `canton-mcp-1`, `canton-mcp-2`, `canton-mcp-3`
- Compare performance across servers
- Track load distribution
- Identify bottlenecks per instance

## Troubleshooting

### Server Won't Start

Check logs:
```bash
docker-compose logs canton-mcp-server-2
```

Common issues:
- Port already in use: Change port in docker-compose.yml
- Build failure: Check source code syntax
- Health check failing: Wait 30 seconds for startup

### Test Container Only Calls One Server

Check configuration:
```bash
docker-compose exec mcp-tester env | grep MCP_SERVER_URLS
```

Should show all 3 servers comma-separated.

### DCAP Not Showing Separate Servers

Verify server IDs:
```bash
docker-compose exec canton-mcp-server env | grep DCAP_SERVER_ID
docker-compose exec canton-mcp-server-2 env | grep DCAP_SERVER_ID
docker-compose exec canton-mcp-server-3 env | grep DCAP_SERVER_ID
```

Each should have a unique ID.

## Performance Testing

### Concurrent Load Test

```bash
# Install Apache Bench
# apt-get install apache2-utils

# Test server 1
ab -n 1000 -c 10 -p payload.json -T application/json http://localhost:7284/mcp

# Compare all servers
for port in 7284 7285 7286; do
    echo "Testing localhost:$port..."
    ab -n 100 -c 5 -p payload.json -T application/json http://localhost:$port/mcp
    echo ""
done
```

### Monitor Test Load Distribution

```bash
# Terminal 1: Watch tester
docker-compose logs -f mcp-tester | grep "Calling"

# Terminal 2: Watch server 1
docker-compose logs -f canton-mcp-server | grep "Tool.*completed"

# Terminal 3: Watch server 2
docker-compose logs -f canton-mcp-server-2 | grep "Tool.*completed"

# Terminal 4: Watch server 3
docker-compose logs -f canton-mcp-server-3 | grep "Tool.*completed"
```

## Production Considerations

1. **Resource Allocation**: Each server needs adequate CPU/memory
2. **Network**: Ensure DCAP_MULTICAST_IP is reachable from all containers
3. **Database**: If adding persistence, ensure proper connection pooling
4. **Session Affinity**: For stateful operations, use sticky sessions in load balancer
5. **Monitoring**: Set up alerts for individual server failures
6. **Scaling**: Add/remove servers based on DCAP metrics

## Environment Variables

All servers support the same environment variables. Set different values per server:

| Variable | Server 1 | Server 2 | Server 3 |
|----------|----------|----------|----------|
| `DCAP_SERVER_ID` | canton-mcp-1 | canton-mcp-2 | canton-mcp-3 |
| `DCAP_SERVER_NAME` | Canton MCP Server 1 | Canton MCP Server 2 | Canton MCP Server 3 |
| Port mapping | 7284:7284 | 7285:7284 | 7286:7284 |

All other variables (DCAP_MULTICAST_IP, X402 settings, etc.) are shared across all servers.

