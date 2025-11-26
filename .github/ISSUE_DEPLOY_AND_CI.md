# 🚀 Setup CI for Canton MCP Server

## 📋 Summary

Add GitHub Actions CI to run tests on every PR. Keep deployment simple - users clone the repo and run `docker-compose up -d`.

## 🎯 Goals

1. **Automated Testing**: Run tests on every PR to prevent regressions
2. **Simple Deployment**: Users git clone + docker-compose up
3. **Keep It Simple**: No fancy registries, no complex pipelines

---

## 🔧 What We Actually Need

### GitHub Actions CI (`.github/workflows/ci.yml`)
**Trigger:** Every PR, every push to main

**Jobs:**
```yaml
test:
  - Install dependencies (uv sync)
  - Run linting (ruff)
  - Run type checking (mypy) 
  - Run tests (pytest)
  - Validate docker-compose builds

docker-test:
  - Build Docker image
  - Run server in container
  - Smoke test endpoints
```

That's it. No publishing, no registries, no complexity.

---

## 📋 Implementation Checklist

### Step 1: Create `.github/workflows/ci.yml`
- [ ] Setup Python with uv
- [ ] Run `uv sync` to install deps
- [ ] Run `ruff check .` for linting
- [ ] Run `mypy src/` for type checking
- [ ] Run `pytest tests/` for unit tests
- [ ] Run `docker-compose build` to validate Docker

### Step 2: Branch Protection
- [ ] Require CI to pass before merge to main
- [ ] Require 1 review for PRs

### Step 3: Add Badge to README
- [ ] Add build status badge

### Done
That's literally it.

---

## 🎯 Success Criteria

- ✅ Every PR runs tests automatically
- ✅ Failed tests block merge
- ✅ CI completes in < 5 minutes

---

## 📝 Example CI Workflow

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run mypy src/
      - run: uv run pytest tests/
      
  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker-compose build
      - run: docker-compose up -d
      - run: sleep 5 && curl http://localhost:7284/health
```

---

## 📝 Notes

**Current State:**
- ✅ Code on main, working
- ❌ No CI yet

**Timeline:** 
- 1-2 hours to set up

**Deployment:**
- Users: `git clone` + `docker-compose up -d`
- No registry needed

---

## 🎯 Stretch Goal: Auto-Deploy to Remote Server

**Optional:** Automatically deploy to a hosted server on push to main.

### Setup
1. Get a cheap VPS (DigitalOcean, Hetzner, AWS EC2)
2. Add SSH key to GitHub Secrets (`SSH_PRIVATE_KEY`, `SSH_HOST`, `SSH_USER`)
3. Add deploy job to CI:

```yaml
deploy:
  needs: [test, docker]
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  steps:
    - name: Deploy to server
      env:
        SSH_PRIVATE_KEY: ${{ secrets.SSH_PRIVATE_KEY }}
        SSH_HOST: ${{ secrets.SSH_HOST }}
        SSH_USER: ${{ secrets.SSH_USER }}
      run: |
        mkdir -p ~/.ssh
        echo "$SSH_PRIVATE_KEY" > ~/.ssh/id_rsa
        chmod 600 ~/.ssh/id_rsa
        ssh -o StrictHostKeyChecking=no $SSH_USER@$SSH_HOST << 'EOF'
          cd /opt/canton-mcp-server
          git pull origin main
          docker-compose up -d --build
        EOF
```

### Result
- Server publicly available at `https://canton-mcp.your-domain.com`
- Auto-deploys on every merge to main
- Users can use it without running locally

**Benefits:**
- Demo/showcase server
- Test integration before users install
- Quick onboarding (just point Claude Desktop at the URL)

**Cost:** ~$5-10/month for a small VPS

