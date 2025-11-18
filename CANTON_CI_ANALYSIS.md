# Canton CI Analysis: Local Automation Capabilities

**Date:** November 18, 2025  
**Source:** `/Users/martinmaurer/Projects/Martin/canton-ci`  
**Purpose:** Understand what automation capabilities exist for implementing `daml_automater` tool

---

## Repository Overview

The `canton-ci` repository provides **reusable GitHub Actions** for DAML/Canton CI/CD workflows. It's structured as a collection of composable automation building blocks.

### Structure

```
canton-ci/
├── .github/
│   ├── actions/
│   │   ├── install-daml/         # Install DAML SDK
│   │   ├── install-canton/       # Install Canton (open source)
│   │   ├── daml-test/            # Run DAML tests
│   │   ├── daml-script/          # Run DAML scripts on Canton
│   │   └── get-project-variables/ # Parse daml.yaml
│   └── workflows/
│       └── enterprise-canton-node.yaml  # Enterprise Canton workflow
```

---

## Available Actions

### 1. Install DAML SDK

**File:** `.github/actions/install-daml/action.yml`

**Capabilities:**
- Installs specific DAML SDK version or latest stable
- Downloads from Digital Asset GitHub releases
- Installs Java (Temurin 21) as dependency
- Adds DAML to PATH

**Key Commands:**
```bash
# Latest stable
curl -sSL https://get.daml.com/ | sh

# Specific version
gh release download v$VERSION \
  --repo digital-asset/daml \
  --pattern "daml-sdk*linux-x86_64.tar.gz"
tar xzf daml-sdk.tar.gz
./install.sh --install-with-custom-version $VERSION
```

**Local Adaptation:**
- ✅ Can be replicated with Python `subprocess` calls
- ✅ Or use existing DAML installation on system
- ✅ Check version with: `daml version`

---

### 2. Install Canton

**File:** `.github/actions/install-canton/action.yml`

**Capabilities:**
- Downloads Canton open-source from GitHub releases
- Supports specific version or latest stable
- Extracts to `./canton-release/` directory

**Key Commands:**
```bash
# Get latest version
gh release list --repo digital-asset/daml \
  --json tagName,isPrerelease \
  --jq 'map(select(.isPrerelease == false)) | .[0].tagName'

# Download Canton
gh release download v$VERSION \
  --repo digital-asset/daml \
  --pattern "canton-open-source*.tar.gz"

# Extract
tar zxvf canton-release.tar.gz -C canton-release --strip-components=1
```

**Canton Binary:**
- Located at: `./canton-release/bin/canton`
- Usage: `./canton-release/bin/canton --version`

**Local Adaptation:**
- ✅ Can download and cache Canton releases
- ✅ Or use system-installed Canton
- ✅ Or use Docker container (preferred for isolation)

---

### 3. DAML Test

**File:** `.github/actions/daml-test/action.yml`

**Capabilities:**
- Runs DAML unit tests using DAML Sandbox
- Parses `daml.yaml` to get project configuration
- Installs correct DAML SDK version automatically

**Key Commands:**
```bash
cd /path/to/daml/project
daml test
```

**Workflow:**
1. Parse `daml.yaml` for SDK version
2. Install matching DAML SDK
3. Run `daml test` in project directory

**Local Adaptation:**
- ✅ Very straightforward: `subprocess.run(["daml", "test"], cwd=project_path)`
- ✅ Capture stdout/stderr for test results
- ✅ Parse output for pass/fail status

---

### 4. DAML Script (Canton Sandbox)

**File:** `.github/actions/daml-script/action.yml`

**Capabilities:**
- **Spins up local Canton sandbox node**
- Runs DAML scripts against live Canton ledger
- Waits for Canton to be ready before running scripts
- Configurable ports for Ledger API and JSON API

**Key Commands:**

```bash
# 1. Build DAML project
cd /path/to/project
daml build
# Output: .daml/dist/project-name-version.dar

# 2. Start Canton sandbox in background
./canton-release/bin/canton sandbox \
  --ledger-api-port 6865 \
  --json-api-port 7575 \
  --dar /path/to/project.dar &

# 3. Wait for Canton to be ready (poll /livez endpoint)
for i in $(seq 1 10); do
  if curl http://localhost:7575/livez > /dev/null 2>&1; then
    echo "Canton ready"
    exit 0
  fi
  sleep 5
done

# 4. Run DAML scripts
daml script \
  --dar /path/to/project.dar \
  --all \
  --ledger-host localhost \
  --ledger-port 6865
```

**Health Check:**
- **JSON API:** `http://localhost:7575/livez`
- **Ledger API:** gRPC port 6865

**Local Adaptation:**
- ✅ **CRITICAL:** This shows how to spin up Canton locally!
- ✅ Use Python `subprocess.Popen` to run Canton in background
- ✅ Poll health endpoint with `requests.get()`
- ✅ Or use Docker container (cleaner isolation)

---

### 5. Get Project Variables

**File:** `.github/actions/get-project-variables/action.yml`

**Capabilities:**
- Parses `daml.yaml` file
- Extracts SDK version, project name, project version
- Uses `yq` YAML parser

**Key Commands:**
```bash
yq -r '.sdk-version' daml.yaml
yq -r '.name' daml.yaml
yq -r '.version' daml.yaml
```

**Local Adaptation:**
- ✅ Use Python `PyYAML` library
- ✅ Parse `daml.yaml` directly

---

## Canton Sandbox Details

### Starting Canton Sandbox

**Command:**
```bash
canton sandbox \
  --ledger-api-port 6865 \
  --json-api-port 7575 \
  --dar /path/to/project.dar
```

**Ports:**
- **6865:** Ledger API (gRPC) - Used for DAML script execution
- **7575:** JSON API (HTTP) - Used for health checks, queries

**Health Endpoint:**
```bash
curl http://localhost:7575/livez
# Returns 200 OK when ready
```

**Shutdown:**
- Send SIGTERM to process
- Or use Canton console commands

---

## Local Automation Strategy

### Option 1: Direct Process Management (Simple)

**Pros:**
- No additional dependencies
- Direct control over processes
- Fast startup

**Cons:**
- Requires DAML/Canton installed on system
- Cleanup can be tricky (orphaned processes)
- Port conflicts if multiple instances

**Implementation:**
```python
import subprocess
import requests
import time

def spin_up_canton(dar_path: str, ledger_port=6865, json_port=7575):
    """Start Canton sandbox with DAR file"""
    
    # Start Canton in background
    process = subprocess.Popen([
        "./canton-release/bin/canton", "sandbox",
        "--ledger-api-port", str(ledger_port),
        "--json-api-port", str(json_port),
        "--dar", dar_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for Canton to be ready
    for attempt in range(10):
        try:
            response = requests.get(f"http://localhost:{json_port}/livez", timeout=2)
            if response.status_code == 200:
                return process
        except:
            time.sleep(5)
    
    raise RuntimeError("Canton failed to start")

def run_daml_tests(project_path: str):
    """Run DAML tests"""
    result = subprocess.run(
        ["daml", "test"],
        cwd=project_path,
        capture_output=True,
        text=True
    )
    return result.returncode == 0, result.stdout, result.stderr
```

---

### Option 2: Docker Containers (Recommended)

**Pros:**
- ✅ Clean isolation
- ✅ No system installation required
- ✅ Easy cleanup (stop/remove container)
- ✅ Consistent environment
- ✅ Can use official Canton images

**Cons:**
- Requires Docker
- Slightly slower startup

**Implementation:**
```python
import docker
import requests
import time

def spin_up_canton_docker(dar_path: str, ledger_port=6865, json_port=7575):
    """Start Canton sandbox in Docker"""
    
    client = docker.from_env()
    
    # Start Canton container
    container = client.containers.run(
        "digitalasset/canton-open-source:latest",
        command=[
            "sandbox",
            "--ledger-api-port", str(ledger_port),
            "--json-api-port", str(json_port),
            "--dar", "/dars/project.dar"
        ],
        ports={
            f'{ledger_port}/tcp': ledger_port,
            f'{json_port}/tcp': json_port
        },
        volumes={
            dar_path: {'bind': '/dars/project.dar', 'mode': 'ro'}
        },
        detach=True,
        auto_remove=True
    )
    
    # Wait for ready
    for attempt in range(10):
        try:
            response = requests.get(f"http://localhost:{json_port}/livez", timeout=2)
            if response.status_code == 200:
                return container
        except:
            time.sleep(5)
    
    raise RuntimeError("Canton failed to start")

def cleanup_canton_docker(container):
    """Stop and remove Canton container"""
    container.stop()
```

---

## Proposed `daml_automater` Actions

Based on the canton-ci analysis, here are the automation actions to implement:

### 1. `spin_up_env`

**Purpose:** Start a local Canton environment for testing/development

**Parameters:**
```json
{
  "action": "spin_up_env",
  "environment": "local",
  "config": {
    "ledger_api_port": 6865,
    "json_api_port": 7575,
    "dar_path": "/path/to/project.dar",  // Optional
    "use_docker": true  // true=Docker, false=Local binary
  }
}
```

**Returns:**
```json
{
  "success": true,
  "action": "spin_up_env",
  "message": "Canton sandbox started successfully",
  "details": {
    "container_id": "abc123...",  // If Docker
    "ledger_api_endpoint": "http://localhost:6865",
    "json_api_endpoint": "http://localhost:7575",
    "health_status": "ready"
  }
}
```

---

### 2. `run_tests`

**Purpose:** Compile and test DAML code

**Parameters:**
```json
{
  "action": "run_tests",
  "environment": "local",
  "config": {
    "project_path": "/path/to/daml/project",
    "test_filter": null  // Optional: filter specific tests
  }
}
```

**Returns:**
```json
{
  "success": true,
  "action": "run_tests",
  "message": "All tests passed (15/15)",
  "details": {
    "tests_run": 15,
    "tests_passed": 15,
    "tests_failed": 0,
    "duration_seconds": 12.3,
    "output": "..."
  }
}
```

---

### 3. `run_script`

**Purpose:** Run DAML scripts against Canton sandbox

**Parameters:**
```json
{
  "action": "run_script",
  "environment": "local",
  "config": {
    "project_path": "/path/to/daml/project",
    "dar_path": "/path/to/project.dar",
    "script_name": "Main:setup",  // Optional: specific script
    "ledger_api_port": 6865
  }
}
```

**Returns:**
```json
{
  "success": true,
  "action": "run_script",
  "message": "Script executed successfully",
  "details": {
    "script_name": "Main:setup",
    "output": "...",
    "duration_seconds": 5.2
  }
}
```

---

### 4. `build_dar`

**Purpose:** Build DAML project to DAR file

**Parameters:**
```json
{
  "action": "build_dar",
  "config": {
    "project_path": "/path/to/daml/project"
  }
}
```

**Returns:**
```json
{
  "success": true,
  "action": "build_dar",
  "message": "DAR built successfully",
  "details": {
    "dar_path": "/path/to/project/.daml/dist/project-1.0.0.dar",
    "project_name": "project",
    "version": "1.0.0",
    "sdk_version": "3.4.0"
  }
}
```

---

### 5. `status`

**Purpose:** Check Canton environment status

**Parameters:**
```json
{
  "action": "status",
  "environment": "local"
}
```

**Returns:**
```json
{
  "success": true,
  "action": "status",
  "message": "Canton environment is running",
  "details": {
    "status": "running",
    "containers": [
      {
        "id": "abc123",
        "name": "canton-sandbox",
        "ports": {"6865": 6865, "7575": 7575},
        "health": "ready"
      }
    ],
    "uptime_seconds": 1234
  }
}
```

---

### 6. `teardown_env`

**Purpose:** Stop and clean up Canton environment

**Parameters:**
```json
{
  "action": "teardown_env",
  "environment": "local"
}
```

**Returns:**
```json
{
  "success": true,
  "action": "teardown_env",
  "message": "Canton environment stopped",
  "details": {
    "containers_stopped": 1,
    "containers_removed": 1
  }
}
```

---

## Implementation Dependencies

### Python Libraries Needed

```toml
# Add to pyproject.toml
[project.dependencies]
# Existing...
docker = "^7.0.0"  # For Docker container management
pyyaml = "^6.0"    # For parsing daml.yaml
requests = "^2.31.0"  # Already have this

# Optional for advanced features
kubernetes = "^28.1.0"  # If deploying to k8s
```

### System Requirements

**For Docker-based automation:**
- Docker installed and running
- Network access to pull Canton images

**For binary-based automation:**
- DAML SDK installed (`daml` command available)
- Canton installed (optional, can download dynamically)
- Java 21 (required by DAML/Canton)

---

## Known Limitations (from canton-ci)

1. **Multi-package projects not supported** - Only single-package DAML projects
2. **Canton binary not globally accessible** - Must use path to binary
3. **Enterprise Canton requires authentication** - JFrog credentials needed
4. **Version compatibility** - Older Canton versions have CLI syntax changes

---

## Recommended Implementation Plan

### Phase 1: Core Actions (Docker-based)

1. ✅ `build_dar` - Compile DAML project
2. ✅ `run_tests` - Run DAML tests
3. ✅ `spin_up_env` - Start Canton sandbox in Docker
4. ✅ `status` - Check Canton status
5. ✅ `teardown_env` - Stop Canton

**Estimated Time:** 2-3 days

### Phase 2: Advanced Actions

6. ✅ `run_script` - Execute DAML scripts
7. ✅ `deploy` - Deploy DAR to Canton network (requires network config)
8. ✅ Smart environment management (auto-cleanup, port allocation)

**Estimated Time:** 2-3 days

### Phase 3: Enterprise Features

9. ✅ Multi-package support
10. ✅ Canton Enterprise integration
11. ✅ Kubernetes deployment support
12. ✅ Remote Canton network connections

**Estimated Time:** 3-5 days

---

## Next Steps

1. **Add Docker dependency** to `pyproject.toml`
2. **Implement core actions** in `daml_automater_tool.py`
3. **Create Canton manager class** for environment lifecycle
4. **Add comprehensive tests** in `test-daml/` directory
5. **Document usage** for developers

---

## Example Usage (Proposed)

```python
# Via MCP tool
result = await daml_automater.execute({
    "action": "spin_up_env",
    "config": {"use_docker": true}
})

# Start Canton, run tests, cleanup
await daml_automater.execute({"action": "spin_up_env"})
await daml_automater.execute({
    "action": "run_tests",
    "config": {"project_path": "./test-daml"}
})
await daml_automater.execute({"action": "teardown_env"})
```

---

## Summary

The `canton-ci` repository provides excellent patterns for DAML/Canton automation. The key insight is the **Canton sandbox** command with health checking via `/livez` endpoint. This gives us a clear path to implement local environment automation with either Docker or direct process management.

**Recommendation:** Implement Docker-based approach first (cleaner, more reliable), then add binary support as fallback.

