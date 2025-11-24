# Deployment Setup Guide

**Auto-deploy to production server on every merge to `main`**

---

## 🔐 Step 1: Add SSH Key to GitHub Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Create secret:
   - **Name**: `SSH_PRIVATE_KEY`
   - **Value**: Paste your SSH private key (entire file content)
   
   ```bash
   # Get your SSH key (copy the output)
   cat ~/.ssh/id_rsa
   # OR if you have a specific key:
   cat ~/.ssh/devops_key
   ```

5. Click **Add secret**

---

## 🖥️ Step 2: Server Setup

SSH to your server and set up the project:

```bash
ssh devops@91.99.186.83

# Option A: Install in /opt (recommended for production)
sudo mkdir -p /opt/canton-mcp-server
sudo chown devops:devops /opt/canton-mcp-server
cd /opt/canton-mcp-server

# OR Option B: Install in home directory
cd ~
mkdir -p canton-mcp-server
cd canton-mcp-server

# Clone the repository
git clone https://github.com/ChainSafe/canton-mcp-server.git .

# Create .env.canton if needed
cp .env.canton.example .env.canton  # If you have one
# OR create manually with your API keys

# First build
docker compose build
docker compose up -d

# Verify it's running
docker compose ps
curl http://localhost:7284/health
```

---

## 📋 Step 3: Update CI Workflow (if needed)

The CI workflow is configured to deploy to `/opt/canton-mcp-server` or `~/canton-mcp-server`.

If your server uses a different path, update `.github/workflows/ci.yml`:

```yaml
cd /opt/canton-mcp-server || cd ~/canton-mcp-server || cd /your/custom/path
```

---

## 🧪 Step 4: Test Deployment

1. Make a small change and push to `main`:
   ```bash
   git checkout main
   echo "# Test deployment" >> README.md
   git add README.md
   git commit -m "Test: trigger deployment"
   git push origin main
   ```

2. Watch the GitHub Actions run:
   - Go to **Actions** tab in GitHub
   - Click on the latest workflow run
   - Watch the `deploy` job

3. Verify on server:
   ```bash
   ssh devops@91.99.186.83
   cd /opt/canton-mcp-server
   docker compose ps  # Should show running containers
   docker compose logs --tail=50  # Check logs
   curl http://localhost:7284/health  # Test endpoint
   ```

---

## 🔄 Deployment Flow

```
Push to main
    ↓
GitHub Actions
    ↓
✅ Run tests (linting, type checking, unit tests)
    ↓
✅ Build Docker image
    ↓
✅ Deploy to 91.99.186.83
    ↓
    1. SSH to server
    2. cd /opt/canton-mcp-server
    3. git pull origin main
    4. docker compose down
    5. docker compose up -d --build
    ↓
✅ Server updated!
```

---

## 🔧 Troubleshooting

### SSH Connection Failed
```bash
# Check SSH key format in GitHub Secrets
# Should start with: -----BEGIN OPENSSH PRIVATE KEY-----
# Should end with: -----END OPENSSH PRIVATE KEY-----

# Test SSH manually:
ssh -i ~/.ssh/id_rsa devops@91.99.186.83
```

### Git Pull Failed
```bash
# On server, check git status:
ssh devops@91.99.186.83
cd /opt/canton-mcp-server
git status
git pull origin main  # Should work without password
```

### Docker Compose Failed
```bash
# On server, check docker:
ssh devops@91.99.186.83
docker compose ps
docker compose logs
docker compose down && docker compose up -d --build
```

---

## 🛡️ Security Notes

1. **SSH Key**: Only the private key is in GitHub Secrets (encrypted)
2. **Server Access**: Only `devops` user can deploy
3. **No Passwords**: All auth via SSH keys
4. **Automatic Only**: Deploys only trigger on `main` branch pushes
5. **PR Protection**: Pull requests don't trigger deployment

---

## 📊 Monitoring

### Check Deployment Status
```bash
# GitHub Actions logs
https://github.com/ChainSafe/canton-mcp-server/actions

# Server logs
ssh devops@91.99.186.83 "cd /opt/canton-mcp-server && docker compose logs --tail=100"

# Health check
curl http://91.99.186.83:7284/health
```

### Rollback (if needed)
```bash
ssh devops@91.99.186.83
cd /opt/canton-mcp-server
git log --oneline -10  # See recent commits
git reset --hard <commit-hash>  # Rollback to specific commit
docker compose up -d --build  # Rebuild
```

---

## ✅ Deployment Checklist

- [ ] SSH key added to GitHub Secrets (`SSH_PRIVATE_KEY`)
- [ ] Server has project cloned in `/opt/canton-mcp-server`
- [ ] Server can `git pull` without password
- [ ] Docker and docker-compose installed on server
- [ ] `.env.canton` configured on server (if needed)
- [ ] Initial manual deployment successful
- [ ] Test commit triggers auto-deployment
- [ ] Health check returns 200 OK

---

**Ready to deploy!** 🚀

Every merge to `main` will automatically update your production server.

