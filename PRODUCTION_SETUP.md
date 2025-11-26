# 🚀 Production Setup Guide

This guide covers the final steps to fully configure the Canton MCP Server in production.

---

## 📋 Quick Checklist

- [ ] Clone canonical DAML repositories
- [ ] Set up repository auto-update cronjob
- [ ] Configure environment variables (API keys)
- [ ] Set up log rotation
- [ ] Configure domain/SSL (optional)
- [ ] Set up monitoring/alerts (optional)

---

## 1. Clone Canonical Repositories

The server needs these repositories for pattern recommendations:

```bash
# SSH to server
ssh devops@91.99.186.83

# Navigate to parent directory
cd /opt

# Clone canonical docs
git clone https://github.com/digital-asset/daml.git canonical-daml-docs-daml
git clone https://github.com/digital-asset/canton.git canonical-daml-docs-canton
git clone https://github.com/digital-asset/daml-finance.git canonical-daml-docs-daml-finance

# Verify
ls -la canonical-daml-docs-*
```

**Expected structure:**
```
/opt/
├── canton-mcp-server/          (your server)
├── canonical-daml-docs-daml/   (DAML SDK docs)
├── canonical-daml-docs-canton/ (Canton docs)
└── canonical-daml-docs-daml-finance/ (DAML Finance docs)
```

**Update docker-compose.yml** to mount these:

```yaml
services:
  canton-mcp-server:
    volumes:
      - ./src:/app/src:ro
      - /opt/canonical-daml-docs-daml:/opt/canonical-daml-docs/daml:ro
      - /opt/canonical-daml-docs-canton:/opt/canonical-daml-docs/canton:ro
      - /opt/canonical-daml-docs-daml-finance:/opt/canonical-daml-docs/daml-finance:ro
```

Then restart:
```bash
cd /opt/canton-mcp-server
docker compose down
docker compose up -d
```

---

## 2. Set Up Auto-Update Cronjob

Keep canonical repos up to date:

```bash
# Create update script
sudo tee /opt/update-canonical-repos.sh > /dev/null << 'EOF'
#!/bin/bash
# Update canonical DAML documentation repositories

REPOS=(
  "/opt/canonical-daml-docs-daml"
  "/opt/canonical-daml-docs-canton"
  "/opt/canonical-daml-docs-daml-finance"
)

for repo in "${REPOS[@]}"; do
  if [ -d "$repo" ]; then
    echo "Updating $repo..."
    cd "$repo"
    git fetch origin
    git reset --hard origin/main
    echo "✅ Updated $repo"
  else
    echo "⚠️ Repository not found: $repo"
  fi
done

# Restart server to pick up changes
cd /opt/canton-mcp-server
docker compose restart

echo "✅ All repositories updated and server restarted"
EOF

# Make executable
sudo chmod +x /opt/update-canonical-repos.sh

# Add cronjob (runs daily at 3am)
crontab -e
```

**Add this line:**
```cron
0 3 * * * /opt/update-canonical-repos.sh >> /var/log/canton-repo-updates.log 2>&1
```

**Test it manually:**
```bash
/opt/update-canonical-repos.sh
```

---

## 3. Configure Environment Variables

Create `.env.canton` file on the server:

```bash
cd /opt/canton-mcp-server

# Create .env.canton file
cat > .env.canton << 'EOF'
# Anthropic API Key (for LLM-based authorization extraction)
ANTHROPIC_API_KEY=sk-ant-your-actual-key-here

# Enable LLM-based authorization extraction
ENABLE_LLM_AUTH_EXTRACTION=true

# DCAP Configuration (if you want semantic discovery)
DCAP_ENABLED=true
DCAP_SERVER_URL=http://your-dcap-server:10191
DCAP_SERVER_ID=canton-mcp-prod
DCAP_SERVER_NAME=Canton MCP Production Server

# X402 Payment Configuration (optional, for paid API access)
X402_ENABLED=false
X402_WALLET_ADDRESS=
X402_WALLET_PRIVATE_KEY=
X402_NETWORK=base-sepolia
X402_TOKEN=USDC

# Server Configuration
LOG_LEVEL=info
EOF

# Set proper permissions
chmod 600 .env.canton
```

**Update docker-compose.yml** to use the .env file:

```yaml
services:
  canton-mcp-server:
    env_file:
      - .env.canton
    # ... rest of config
```

**Restart:**
```bash
docker compose down
docker compose up -d
```

**Verify:**
```bash
docker compose logs -f | grep "ANTHROPIC_API_KEY not set"
# Should NOT see this warning anymore
```

---

## 4. Set Up Log Rotation

Prevent logs from consuming disk space:

```bash
# Create logrotate config
sudo tee /etc/logrotate.d/canton-mcp-server > /dev/null << 'EOF'
/var/log/canton-repo-updates.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0644 devops devops
}
EOF

# Test logrotate
sudo logrotate -d /etc/logrotate.d/canton-mcp-server
```

**For Docker logs:**
```yaml
# In docker-compose.yml
services:
  canton-mcp-server:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 5. Configure Domain & SSL (Optional)

If you want `https://canton-mcp.yourdomain.com` instead of `http://91.99.186.83:7284`:

### Option A: Nginx + Let's Encrypt

```bash
# Install nginx and certbot
sudo apt install nginx certbot python3-certbot-nginx

# Create nginx config
sudo tee /etc/nginx/sites-available/canton-mcp << 'EOF'
server {
    listen 80;
    server_name canton-mcp.yourdomain.com;

    location / {
        proxy_pass http://localhost:7284;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/canton-mcp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Get SSL certificate
sudo certbot --nginx -d canton-mcp.yourdomain.com
```

### Option B: Caddy (Simpler)

```bash
# Install Caddy
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy

# Create Caddyfile
sudo tee /etc/caddy/Caddyfile > /dev/null << 'EOF'
canton-mcp.yourdomain.com {
    reverse_proxy localhost:7284
}
EOF

# Restart Caddy (auto SSL!)
sudo systemctl restart caddy
```

---

## 6. Monitoring & Alerts (Optional)

### Simple Health Check Script

```bash
# Create health check script
sudo tee /opt/check-canton-health.sh > /dev/null << 'EOF'
#!/bin/bash
HEALTH_URL="http://localhost:7284/health"

if ! curl -sf "$HEALTH_URL" > /dev/null; then
  echo "❌ Canton MCP Server is DOWN!"
  # Send alert (email, Slack, etc.)
  # curl -X POST https://hooks.slack.com/your-webhook...
  
  # Try to restart
  cd /opt/canton-mcp-server
  docker compose restart
else
  echo "✅ Canton MCP Server is healthy"
fi
EOF

sudo chmod +x /opt/check-canton-health.sh

# Add to crontab (check every 5 minutes)
crontab -e
```

**Add:**
```cron
*/5 * * * * /opt/check-canton-health.sh >> /var/log/canton-health.log 2>&1
```

---

## 7. Quick Commands Reference

```bash
# View logs (live)
docker compose logs -f

# View last 100 lines
docker compose logs --tail=100

# Restart server
docker compose restart

# Rebuild and restart
docker compose up -d --build

# Stop server
docker compose down

# Check status
docker compose ps

# Check health
curl http://localhost:7284/health

# Update code from GitHub
git pull origin main
docker compose up -d --build
```

---

## ✅ Verification Checklist

After setup, verify everything works:

1. **Canonical repos loaded:**
   ```bash
   docker compose logs | grep "Found [0-9]* documentation files"
   # Should show > 0 files
   ```

2. **No API key warnings:**
   ```bash
   docker compose logs | grep "ANTHROPIC_API_KEY not set"
   # Should return nothing
   ```

3. **Server accessible externally:**
   ```bash
   # From your laptop
   curl http://91.99.186.83:7284/health
   # Should return: {"status":"healthy"}
   ```

4. **MCP tools available:**
   ```bash
   curl -X POST http://91.99.186.83:7284/mcp \
     -H "Content-Type: application/json" \
     -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
   # Should return 2 tools: daml_reason, daml_automater
   ```

---

## 🎯 Priority Tasks (Do These First)

1. ✅ **Clone canonical repos** - Critical for pattern recommendations
2. ✅ **Set up cronjob** - Keep repos updated
3. ✅ **Add ANTHROPIC_API_KEY** - Enable LLM-based auth extraction
4. ⏸️ **Log rotation** - Can wait, but prevents disk issues
5. ⏸️ **Domain/SSL** - Nice to have, not critical
6. ⏸️ **Monitoring** - Can add later

---

## 🆘 Troubleshooting

**Problem: "Repository not found" warnings**
```bash
# Check repo paths
ls -la /opt/canonical-daml-docs-*

# Verify docker-compose mounts
docker compose config | grep volumes
```

**Problem: Server won't start**
```bash
# Check logs
docker compose logs

# Rebuild from scratch
docker compose down
docker compose build --no-cache
docker compose up -d
```

**Problem: Can't access from outside**
```bash
# Check firewall
sudo ufw status
sudo ufw allow 7284/tcp

# Check if server is listening
sudo netstat -tlnp | grep 7284
```

---

## 📞 Next Steps

Once everything is set up, the server will:
- ✅ Auto-deploy on every merge to `main`
- ✅ Validate DAML code with multi-gate safety checks
- ✅ Provide pattern recommendations from canonical repos
- ✅ Extract authorization models using LLM
- ✅ Auto-update documentation repositories daily

**Ready for production!** 🚀

