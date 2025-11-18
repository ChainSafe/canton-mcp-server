# DAML Automater Implementation Plan

**Status:** 📋 Ready to Implement  
**Estimated Total Time:** 4-6 days  
**Dependencies:** Docker, PyYAML, requests (already have)

---

## Architecture Overview

The `daml_automater` tool will provide automated DAML development workflows:

```
┌─────────────────────────────────────────────────────────────┐
│                    DAML Automater Tool                      │
│                  (MCP Tool Interface)                       │
└───────────────────┬─────────────────────────────────────────┘
                    │
                    ├──> CantonManager (Environment Lifecycle)
                    │    ├── Docker-based (primary)
                    │    └── Binary-based (fallback)
                    │
                    ├──> DAMLBuilder (Compilation)
                    │    ├── Parse daml.yaml
                    │    ├── Build DAR files
                    │    └── Version management
                    │
                    ├──> DAMLTester (Testing)
                    │    ├── Run daml test
                    │    ├── Parse test results
                    │    └── Report failures
                    │
                    └──> DAMLScriptRunner (Script Execution)
                         ├── Connect to Canton
                         ├── Execute scripts
                         └── Capture output
```

---

## Phase 1: Core Infrastructure (Days 1-2)

### 1.1 Add Dependencies

**File:** `pyproject.toml`

```toml
[project.dependencies]
# ... existing dependencies ...
docker = "^7.1.0"      # Docker container management
pyyaml = "^6.0.1"      # Parse daml.yaml files
```

**Action:**
```bash
cd /Users/martinmaurer/Projects/Martin/canton-mcp-server
uv add docker pyyaml
```

---

### 1.2 Create Canton Manager

**File:** `src/canton_mcp_server/core/canton_manager.py` (NEW)

**Purpose:** Manage Canton sandbox lifecycle (Docker or binary)

**Key Classes:**

```python
class CantonEnvironment:
    """Represents a running Canton environment"""
    def __init__(self, env_id: str, container=None, process=None):
        self.env_id = env_id
        self.container = container  # Docker container
        self.process = process      # subprocess.Popen
        self.ledger_port = 6865
        self.json_port = 7575
        self.started_at = datetime.utcnow()
    
    def is_healthy(self) -> bool:
        """Check if Canton is responding"""
        ...
    
    def stop(self):
        """Stop Canton environment"""
        ...

class CantonManager:
    """Manages Canton sandbox environments"""
    def __init__(self):
        self.environments: Dict[str, CantonEnvironment] = {}
        self.docker_client = docker.from_env()
    
    async def spin_up_docker(
        self,
        dar_path: Optional[str] = None,
        ledger_port: int = 6865,
        json_port: int = 7575
    ) -> CantonEnvironment:
        """Start Canton sandbox in Docker"""
        ...
    
    async def spin_up_binary(
        self,
        canton_path: str,
        dar_path: Optional[str] = None,
        ledger_port: int = 6865,
        json_port: int = 7575
    ) -> CantonEnvironment:
        """Start Canton sandbox using local binary"""
        ...
    
    async def wait_for_ready(
        self,
        env: CantonEnvironment,
        timeout: int = 60,
        poll_interval: int = 2
    ) -> bool:
        """Wait for Canton to be ready"""
        ...
    
    def get_status(self, env_id: str) -> Dict[str, Any]:
        """Get environment status"""
        ...
    
    async def teardown(self, env_id: str):
        """Stop and clean up environment"""
        ...
    
    def list_environments(self) -> List[Dict[str, Any]]:
        """List all running environments"""
        ...
```

**Key Methods Implementation:**

```python
import docker
import requests
import subprocess
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

async def spin_up_docker(
    self,
    dar_path: Optional[str] = None,
    ledger_port: int = 6865,
    json_port: int = 7575
) -> CantonEnvironment:
    """Start Canton sandbox in Docker"""
    
    env_id = f"canton-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
    
    # Build command
    cmd = [
        "sandbox",
        "--ledger-api-port", str(ledger_port),
        "--json-api-port", str(json_port)
    ]
    
    volumes = {}
    if dar_path:
        cmd.extend(["--dar", "/dars/project.dar"])
        volumes[dar_path] = {'bind': '/dars/project.dar', 'mode': 'ro'}
    
    # Start container
    container = self.docker_client.containers.run(
        "digitalasset/canton-open-source:latest",
        command=cmd,
        ports={
            f'{ledger_port}/tcp': ledger_port,
            f'{json_port}/tcp': json_port
        },
        volumes=volumes,
        detach=True,
        name=env_id,
        auto_remove=False  # Keep for debugging
    )
    
    env = CantonEnvironment(env_id, container=container)
    env.ledger_port = ledger_port
    env.json_port = json_port
    
    # Wait for ready
    if not await self.wait_for_ready(env):
        container.stop()
        raise RuntimeError(f"Canton failed to start within timeout")
    
    self.environments[env_id] = env
    logger.info(f"🚀 Canton sandbox started: {env_id}")
    return env

async def wait_for_ready(
    self,
    env: CantonEnvironment,
    timeout: int = 60,
    poll_interval: int = 2
) -> bool:
    """Wait for Canton to be ready"""
    
    start_time = datetime.utcnow()
    attempts = 0
    
    while (datetime.utcnow() - start_time).seconds < timeout:
        attempts += 1
        try:
            response = requests.get(
                f"http://localhost:{env.json_port}/livez",
                timeout=2
            )
            if response.status_code == 200:
                logger.info(f"✅ Canton ready after {attempts} attempts")
                return True
        except Exception as e:
            logger.debug(f"Attempt {attempts}: Canton not ready yet - {e}")
        
        await asyncio.sleep(poll_interval)
    
    logger.error(f"❌ Canton failed to start within {timeout}s")
    return False
```

---

### 1.3 Create DAML Builder

**File:** `src/canton_mcp_server/core/daml_builder.py` (NEW)

**Purpose:** Build DAML projects and parse daml.yaml

```python
from pathlib import Path
import yaml
import subprocess
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class DAMLProject:
    """Represents a DAML project"""
    name: str
    version: str
    sdk_version: str
    source_path: Path
    dar_path: Optional[Path] = None

class DAMLBuilder:
    """Builds DAML projects"""
    
    @staticmethod
    def parse_daml_yaml(project_path: Path) -> DAMLProject:
        """Parse daml.yaml file"""
        daml_yaml = project_path / "daml.yaml"
        
        if not daml_yaml.exists():
            raise FileNotFoundError(f"daml.yaml not found in {project_path}")
        
        with open(daml_yaml, 'r') as f:
            config = yaml.safe_load(f)
        
        return DAMLProject(
            name=config.get('name', 'unknown'),
            version=config.get('version', '0.0.0'),
            sdk_version=config.get('sdk-version', 'unknown'),
            source_path=project_path
        )
    
    async def build(self, project_path: Path) -> DAMLProject:
        """Build DAML project to DAR"""
        
        # Parse project
        project = self.parse_daml_yaml(project_path)
        
        # Run daml build
        result = subprocess.run(
            ["daml", "build"],
            cwd=project_path,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"DAML build failed: {result.stderr}")
        
        # Find DAR file
        dar_path = project_path / ".daml" / "dist" / f"{project.name}-{project.version}.dar"
        
        if not dar_path.exists():
            raise FileNotFoundError(f"DAR file not found: {dar_path}")
        
        project.dar_path = dar_path
        logger.info(f"✅ Built DAR: {dar_path}")
        return project
```

---

### 1.4 Create DAML Tester

**File:** `src/canton_mcp_server/core/daml_tester.py` (NEW)

**Purpose:** Run DAML tests and parse results

```python
import subprocess
import re
from pathlib import Path
from typing import Dict, Any, List
from dataclasses import dataclass

@dataclass
class TestResult:
    """Result of DAML test execution"""
    success: bool
    tests_run: int
    tests_passed: int
    tests_failed: int
    duration_seconds: float
    output: str
    failures: List[str]

class DAMLTester:
    """Runs DAML tests"""
    
    async def run_tests(self, project_path: Path) -> TestResult:
        """Run daml test"""
        
        import time
        start_time = time.time()
        
        result = subprocess.run(
            ["daml", "test"],
            cwd=project_path,
            capture_output=True,
            text=True
        )
        
        duration = time.time() - start_time
        
        # Parse output
        output = result.stdout + result.stderr
        
        # Simple parsing (improve as needed)
        tests_run = len(re.findall(r'✓|✗', output))
        tests_passed = len(re.findall(r'✓', output))
        tests_failed = tests_run - tests_passed
        
        failures = []
        if tests_failed > 0:
            # Extract failure messages
            failure_pattern = r'✗ (.+?)(?=\n|$)'
            failures = re.findall(failure_pattern, output)
        
        return TestResult(
            success=(result.returncode == 0),
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            duration_seconds=duration,
            output=output,
            failures=failures
        )
```

---

## Phase 2: Tool Implementation (Days 3-4)

### 2.1 Implement Core Actions

**File:** `src/canton_mcp_server/tools/daml_automater_tool.py`

**Update the execute method:**

```python
async def execute(
    self, ctx: ToolContext[DamlAutomaterParams, DamlAutomaterResult]
):
    """Execute DAML automation action"""
    
    action = ctx.params.action
    environment = ctx.params.environment or "local"
    config = ctx.params.config or {}
    
    # Initialize managers (lazy)
    if not hasattr(self, '_canton_manager'):
        from ..core.canton_manager import CantonManager
        from ..core.daml_builder import DAMLBuilder
        from ..core.daml_tester import DAMLTester
        
        self._canton_manager = CantonManager()
        self._daml_builder = DAMLBuilder()
        self._daml_tester = DAMLTester()
    
    try:
        if action == "spin_up_env":
            result = await self._spin_up_env(config)
        elif action == "run_tests":
            result = await self._run_tests(config)
        elif action == "build_dar":
            result = await self._build_dar(config)
        elif action == "status":
            result = await self._get_status(config)
        elif action == "teardown_env":
            result = await self._teardown_env(config)
        elif action == "run_script":
            result = await self._run_script(config)
        else:
            result = DamlAutomaterResult(
                success=False,
                action=action,
                message=f"Unknown action: {action}"
            )
        
        yield ctx.structured(result)
    
    except Exception as e:
        logger.error(f"Automation failed: {e}", exc_info=True)
        yield ctx.structured(DamlAutomaterResult(
            success=False,
            action=action,
            message=f"Error: {str(e)}",
            details={"error_type": type(e).__name__}
        ))

async def _spin_up_env(self, config: dict) -> DamlAutomaterResult:
    """Spin up Canton environment"""
    
    use_docker = config.get('use_docker', True)
    dar_path = config.get('dar_path')
    ledger_port = config.get('ledger_api_port', 6865)
    json_port = config.get('json_api_port', 7575)
    
    if use_docker:
        env = await self._canton_manager.spin_up_docker(
            dar_path=dar_path,
            ledger_port=ledger_port,
            json_port=json_port
        )
    else:
        canton_path = config.get('canton_path', './canton-release/bin/canton')
        env = await self._canton_manager.spin_up_binary(
            canton_path=canton_path,
            dar_path=dar_path,
            ledger_port=ledger_port,
            json_port=json_port
        )
    
    return DamlAutomaterResult(
        success=True,
        action="spin_up_env",
        message=f"Canton sandbox started: {env.env_id}",
        details={
            "env_id": env.env_id,
            "ledger_api_endpoint": f"localhost:{env.ledger_port}",
            "json_api_endpoint": f"http://localhost:{env.json_port}",
            "health_status": "ready",
            "started_at": env.started_at.isoformat()
        }
    )

async def _run_tests(self, config: dict) -> DamlAutomaterResult:
    """Run DAML tests"""
    
    project_path = Path(config.get('project_path', '.'))
    
    test_result = await self._daml_tester.run_tests(project_path)
    
    if test_result.success:
        message = f"✅ All tests passed ({test_result.tests_passed}/{test_result.tests_run})"
    else:
        message = f"❌ Tests failed ({test_result.tests_failed}/{test_result.tests_run} failures)"
    
    return DamlAutomaterResult(
        success=test_result.success,
        action="run_tests",
        message=message,
        details={
            "tests_run": test_result.tests_run,
            "tests_passed": test_result.tests_passed,
            "tests_failed": test_result.tests_failed,
            "duration_seconds": test_result.duration_seconds,
            "failures": test_result.failures,
            "output": test_result.output[:1000]  # Truncate
        }
    )

async def _build_dar(self, config: dict) -> DamlAutomaterResult:
    """Build DAML project"""
    
    project_path = Path(config.get('project_path', '.'))
    
    project = await self._daml_builder.build(project_path)
    
    return DamlAutomaterResult(
        success=True,
        action="build_dar",
        message=f"✅ Built DAR: {project.dar_path.name}",
        details={
            "dar_path": str(project.dar_path),
            "project_name": project.name,
            "version": project.version,
            "sdk_version": project.sdk_version
        }
    )

async def _get_status(self, config: dict) -> DamlAutomaterResult:
    """Get Canton environment status"""
    
    envs = self._canton_manager.list_environments()
    
    if not envs:
        return DamlAutomaterResult(
            success=True,
            action="status",
            message="No Canton environments running",
            details={"environments": []}
        )
    
    return DamlAutomaterResult(
        success=True,
        action="status",
        message=f"{len(envs)} Canton environment(s) running",
        details={"environments": envs}
    )

async def _teardown_env(self, config: dict) -> DamlAutomaterResult:
    """Teardown Canton environment"""
    
    env_id = config.get('env_id')
    
    if env_id:
        await self._canton_manager.teardown(env_id)
        message = f"✅ Stopped environment: {env_id}"
    else:
        # Stop all
        envs = list(self._canton_manager.environments.keys())
        for env_id in envs:
            await self._canton_manager.teardown(env_id)
        message = f"✅ Stopped {len(envs)} environment(s)"
    
    return DamlAutomaterResult(
        success=True,
        action="teardown_env",
        message=message
    )
```

---

## Phase 3: Testing & Documentation (Days 5-6)

### 3.1 Create Test Cases

**File:** `tests/test_daml_automater.py` (NEW)

```python
import pytest
from pathlib import Path

@pytest.mark.asyncio
async def test_build_dar():
    """Test building a DAML project"""
    # Use test-daml project
    ...

@pytest.mark.asyncio
async def test_run_tests():
    """Test running DAML tests"""
    ...

@pytest.mark.asyncio
@pytest.mark.docker
async def test_spin_up_env_docker():
    """Test spinning up Canton in Docker"""
    ...

@pytest.mark.asyncio
async def test_full_workflow():
    """Test complete workflow: build -> spin up -> test -> teardown"""
    ...
```

---

### 3.2 Update Documentation

**File:** `DAML_AUTOMATER_USAGE.md` (NEW)

Document how to use the automater tool with examples.

---

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Add `docker` and `pyyaml` dependencies
- [ ] Create `canton_manager.py`
  - [ ] Implement Docker-based spin up
  - [ ] Implement health checking
  - [ ] Implement teardown
  - [ ] Implement status checking
- [ ] Create `daml_builder.py`
  - [ ] Parse daml.yaml
  - [ ] Build DAR files
- [ ] Create `daml_tester.py`
  - [ ] Run tests
  - [ ] Parse test results

### Phase 2: Tool Implementation
- [ ] Update `daml_automater_tool.py`
  - [ ] Implement `spin_up_env`
  - [ ] Implement `run_tests`
  - [ ] Implement `build_dar`
  - [ ] Implement `status`
  - [ ] Implement `teardown_env`
  - [ ] Implement `run_script` (optional)

### Phase 3: Testing & Documentation
- [ ] Create test suite
- [ ] Test each action
- [ ] Test error handling
- [ ] Document usage
- [ ] Create example workflows

---

## Success Criteria

- ✅ Can spin up Canton sandbox in Docker
- ✅ Can build DAML projects
- ✅ Can run DAML tests
- ✅ Can check environment status
- ✅ Can teardown environments cleanly
- ✅ All tests pass
- ✅ Documentation complete

---

## Next Steps

1. **Review this plan** with team
2. **Start Phase 1** - Core infrastructure
3. **Test incrementally** as we build
4. **Document as we go**

Ready to start implementation? 🚀

