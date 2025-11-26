"""
DAML Automater Tool - CI/CD and Environment Automation Instructions

This tool provides guidance for DAML development automation tasks such as:
- Spinning up local Canton environments
- Running tests in CI/CD
- Building DAML projects
- Managing Canton network connections
- Automating builds and deployments

NOTE: This tool returns INSTRUCTIONS for client-side execution, not server-side operations.
The MCP server does not have DAML SDK or Docker installed.
"""

import logging
from typing import Optional, Dict, Any, List

from pydantic import Field

from ..core import Tool, ToolContext, register_tool
from ..core.pricing import PricingType, ToolPricing
from ..core.types.models import MCPModel

logger = logging.getLogger(__name__)


class DamlAutomaterParams(MCPModel):
    """Parameters for DAML Automater tool"""

    action: str = Field(
        description="Automation action to perform: 'spin_up_env', 'run_tests', 'build_dar', 'status', 'teardown_env', 'check_project', 'init_project'"
    )
    environment: Optional[str] = Field(
        default="local",
        description="Target environment: 'local', 'dev', 'staging', 'prod'"
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="""Additional configuration for the automation action.
        
Common config options:
- project_path: Absolute path to DAML project (required for run_tests, build_dar, check_project, init_project)
- dar_path: Path to DAR file (for spin_up_env)
- env_id: Environment ID (for status, teardown_env)
- ledger_api_port: Port for Ledger API (default: 6865)
- json_api_port: Port for JSON API (default: 7575)
- project_name: Name for new project (for init_project, default: 'daml-project')
- sdk_version: DAML SDK version (for init_project, default: '3.4.0-snapshot.20251013.0')

IMPORTANT: Use absolute paths for project_path. The MCP server runs in its own directory,
not the client's working directory. Example: '/Users/you/my-daml-project'"""
    )


class DamlAutomaterResult(MCPModel):
    """Result from DAML Automater execution"""

    success: bool = Field(description="Whether the automation action succeeded")
    action: str = Field(description="The action that was performed")
    message: str = Field(description="Result message")
    commands: List[str] = Field(default=[], description="Shell commands for client to execute")
    instructions: str = Field(default="", description="Human-readable instructions for the client")
    details: Optional[dict] = Field(default=None, description="Additional details about the result")


@register_tool
class DamlAutomaterTool(Tool[DamlAutomaterParams, DamlAutomaterResult]):
    """
    DAML Automater - CI/CD and Environment Automation Instructions
    
    Provides client-side automation guidance for DAML development:
    - Instructions for spinning up local Canton environments
    - Commands for running automated tests
    - Steps for building DAML projects to DAR files
    - Canton environment lifecycle management guidance
    
    NOTE: This tool returns INSTRUCTIONS for the client to execute locally,
    not server-side execution. The MCP server does not have DAML SDK or Docker.
    """

    name = "daml_automater"
    description = (
        "🤖 DAML Automater - CI/CD and environment automation instructions. "
        "Provides commands and guidance for Canton environments, tests, and builds (client-side execution)."
    )
    params_model = DamlAutomaterParams
    result_model = DamlAutomaterResult
    
    pricing = ToolPricing(
        type=PricingType.FIXED,
        base_cost=0.0,
        description="Automation guidance (free)"
    )
    
    def __init__(self):
        """Initialize automation tool"""
        super().__init__()

    async def execute(
        self, ctx: ToolContext[DamlAutomaterParams, DamlAutomaterResult]
    ):
        """
        Provide DAML automation instructions for client-side execution.
        
        Supported actions:
        - spin_up_env: Instructions to start Canton sandbox locally
        - run_tests: Commands to execute DAML tests
        - build_dar: Commands to build DAML project to DAR
        - status: Commands to check Canton environment status
        - teardown_env: Commands to stop Canton environment
        - check_project: Commands to verify DAML project validity
        - init_project: Commands to initialize DAML project structure
        """
        action = ctx.params.action
        environment = ctx.params.environment or "local"
        config = ctx.params.config or {}
        
        logger.info(f"🤖 DAML Automater: providing guidance for action={action}, environment={environment}")
        
        try:
            if action == "spin_up_env":
                result = self._spin_up_env_instructions(config)
            elif action == "run_tests":
                result = self._run_tests_instructions(config)
            elif action == "build_dar":
                result = self._build_dar_instructions(config)
            elif action == "status":
                result = self._get_status_instructions(config)
            elif action == "teardown_env":
                result = self._teardown_env_instructions(config)
            elif action == "check_project":
                result = self._check_project_instructions(config)
            elif action == "init_project":
                result = self._init_project_instructions(config)
            else:
                result = DamlAutomaterResult(
                    success=False,
                    action=action,
                    message=f"Unknown action: {action}",
                    instructions="Please use one of the available actions.",
                    details={
                        "available_actions": [
                            "spin_up_env",
                            "run_tests",
                            "build_dar",
                            "status",
                            "teardown_env",
                            "check_project",
                            "init_project"
                        ]
                    }
                )
            
            yield ctx.structured(result)
            
        except Exception as e:
            logger.error(f"❌ Failed to generate instructions: {e}", exc_info=True)
            yield ctx.structured(DamlAutomaterResult(
                success=False,
                action=action,
                message=f"Error generating instructions: {str(e)}",
                instructions="Unable to provide automation guidance at this time.",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            ))
    
    def _spin_up_env_instructions(self, config: dict) -> DamlAutomaterResult:
        """
        Provide instructions to spin up Canton sandbox environment locally.
        
        Config options:
        - dar_path: Optional path to DAR file to preload
        - ledger_api_port: Port for Ledger API (default: 6865)
        - json_api_port: Port for JSON API (default: 7575)
        """
        dar_path = config.get('dar_path')
        ledger_port = config.get('ledger_api_port', 6865)
        
        commands = [
            f"daml sandbox --port {ledger_port}"
        ]
        
        if dar_path:
            commands[0] += f" --dar {dar_path}"
        
        instructions = f"""To start a local Canton sandbox:

1. **Start the sandbox:**
   ```bash
   {commands[0]}
   ```

2. **Verify it's running:**
   - Ledger API will be available at `localhost:{ledger_port}`
   - You should see "Started Canton Sandbox" in the output

3. **Keep the terminal open** - the sandbox runs in the foreground

**What this does:**
- Starts an in-memory Canton ledger for development
- Exposes Ledger API on port {ledger_port}
{"- Preloads your DAR file automatically" if dar_path else ""}

**Prerequisites:**
- DAML SDK installed (`daml version` to check)
- Port {ledger_port} available
"""
        
        return DamlAutomaterResult(
            success=True,
            action="spin_up_env",
            message="📋 Instructions to start Canton sandbox",
            commands=commands,
            instructions=instructions,
            details={
                "ledger_port": ledger_port,
                "dar_path": dar_path,
                "method": "daml_sandbox"
            }
        )
    
    def _run_tests_instructions(self, config: dict) -> DamlAutomaterResult:
        """
        Provide instructions to run DAML tests for a project.
        
        Config options:
        - project_path: Path to DAML project (REQUIRED)
        - test_filter: Optional filter for specific tests
        """
        project_path_str = config.get('project_path')
        if not project_path_str:
            return DamlAutomaterResult(
                success=False,
                action="run_tests",
                message="❌ Missing required config: project_path",
                instructions="Please provide the path to your DAML project directory.",
                details={
                    "error": "project_path is required",
                    "example": {"project_path": "/Users/you/my-daml-project"}
                }
            )
        
        test_filter = config.get('test_filter')
        
        commands = ["cd " + project_path_str]
        if test_filter:
            commands.append(f"daml test -- -m {test_filter}")
        else:
            commands.append("daml test")
        
        instructions = f"""To run DAML tests in your project:

1. **Navigate to your project:**
   ```bash
   cd {project_path_str}
   ```

2. **Run the tests:**
   ```bash
   {commands[1]}
   ```

**What this does:**
- Compiles your DAML project
- Executes all test scenarios
{"- Filters tests matching: " + test_filter if test_filter else "- Runs all tests in the project"}
- Reports pass/fail status

**Expected output:**
```
Compiling...
Running tests...
✅ All 5 tests passed
```

**Common issues:**
- If tests fail, check the error messages for assertion failures
- Ensure your `daml.yaml` has proper dependencies
- Use `daml build` first to check for compilation errors
"""
        
        return DamlAutomaterResult(
            success=True,
            action="run_tests",
            message="📋 Instructions to run DAML tests",
            commands=commands,
            instructions=instructions,
            details={
                "project_path": project_path_str,
                "test_filter": test_filter
            }
        )
    
    def _build_dar_instructions(self, config: dict) -> DamlAutomaterResult:
        """
        Provide instructions to build DAML project to DAR file.
        
        Config options:
        - project_path: Path to DAML project (REQUIRED)
        """
        project_path_str = config.get('project_path')
        if not project_path_str:
            return DamlAutomaterResult(
                success=False,
                action="build_dar",
                message="❌ Missing required config: project_path",
                instructions="Please provide the path to your DAML project directory.",
                details={
                    "error": "project_path is required",
                    "example": {"project_path": "/Users/you/my-daml-project"}
                }
            )
        
        commands = [
            f"cd {project_path_str}",
            "daml build"
        ]
        
        instructions = f"""To build your DAML project into a DAR file:

1. **Navigate to your project:**
   ```bash
   cd {project_path_str}
   ```

2. **Build the project:**
   ```bash
   daml build
   ```

**What this does:**
- Compiles all DAML modules in the `daml/` directory
- Type-checks and validates your code
- Packages everything into a DAR (DAML Archive) file
- Outputs to `.daml/dist/<project-name>-<version>.dar`

**Expected output:**
```
Compiling my-project to a DAR.
Created .daml/dist/my-project-1.0.0.dar
```

**The DAR file:**
- Contains all compiled DAML code
- Can be deployed to Canton ledgers
- Can be used in DAML scripts
- Is fully self-contained and portable

**Next steps after building:**
- Deploy: `daml ledger upload-dar .daml/dist/your-project.dar`
- Run scripts: `daml script --dar .daml/dist/your-project.dar ...`
"""
        
        return DamlAutomaterResult(
            success=True,
            action="build_dar",
            message="📋 Instructions to build DAML project",
            commands=commands,
            instructions=instructions,
            details={
                "project_path": project_path_str,
                "output_location": ".daml/dist/"
            }
        )
    
    def _get_status_instructions(self, config: dict) -> DamlAutomaterResult:
        """
        Provide instructions to check Canton environment status.
        
        Config options:
        - ledger_port: Port where Canton is running (default: 6865)
        """
        ledger_port = config.get('ledger_api_port', 6865)
        
        commands = [
            f"curl -s http://localhost:{ledger_port}/livez || echo 'Canton not running'",
            "ps aux | grep 'daml sandbox' | grep -v grep"
        ]
        
        instructions = f"""To check if Canton sandbox is running:

**Method 1: Check the process**
```bash
ps aux | grep 'daml sandbox' | grep -v grep
```
- If you see output, Canton is running
- Note the process ID (PID) in the second column

**Method 2: Check if port is in use**
```bash
lsof -i :{ledger_port}
```
- If you see output, something is listening on port {ledger_port}
- Should show `daml` or `java` process

**Method 3: Try connecting**
```bash
curl -s http://localhost:{ledger_port}/livez
```
- Canton health endpoint (if available)
- Returns JSON status if running

**Visual check:**
- Look for a terminal window with Canton sandbox running
- You should see log output if it's active

**If not running:**
- Use the `spin_up_env` action to start Canton
- Or manually run: `daml sandbox --port {ledger_port}`
"""
        
        return DamlAutomaterResult(
                success=True,
                action="status",
                message="📋 Instructions to check Canton status",
                commands=commands,
                instructions=instructions,
                details={
                    "ledger_port": ledger_port,
                    "check_methods": ["ps", "lsof", "curl"]
                }
            )
    
    def _teardown_env_instructions(self, config: dict) -> DamlAutomaterResult:
        """
        Provide instructions to stop Canton environment.
        
        Config options:
        - ledger_port: Port where Canton is running (default: 6865)
        """
        ledger_port = config.get('ledger_api_port', 6865)
        
        commands = [
            "# Find the Canton process",
            "ps aux | grep 'daml sandbox' | grep -v grep",
            "# Kill it (replace <PID> with the actual process ID)",
            "kill <PID>",
            "# Or use pkill to kill by name",
            "pkill -f 'daml sandbox'"
        ]
        
        instructions = f"""To stop a running Canton sandbox:

**Method 1: Interactive stop (recommended)**
1. Go to the terminal where Canton is running
2. Press `Ctrl+C` to gracefully stop it
3. Wait for shutdown messages

**Method 2: Kill by process ID**
```bash
# Find the process
ps aux | grep 'daml sandbox' | grep -v grep

# Kill it (replace <PID> with actual number from second column)
kill <PID>
```

**Method 3: Kill by name**
```bash
pkill -f 'daml sandbox'
```

**Verify it stopped:**
```bash
lsof -i :{ledger_port}
```
- Should return nothing if Canton is stopped

**Clean shutdown vs force kill:**
- `Ctrl+C` or `kill <PID>` = graceful shutdown (recommended)
- `kill -9 <PID>` = force kill (use only if frozen)

**After stopping:**
- Port {ledger_port} will be released
- In-memory data will be lost (expected for sandbox)
- You can start a fresh sandbox anytime
"""
        
        return DamlAutomaterResult(
            success=True,
            action="teardown_env",
            message="📋 Instructions to stop Canton sandbox",
            commands=commands,
            instructions=instructions,
            details={
                "ledger_port": ledger_port,
                "methods": ["interactive", "kill_pid", "pkill"]
            }
        )
    
    def _check_project_instructions(self, config: dict) -> DamlAutomaterResult:
        """
        Provide instructions to check if valid DAML project exists at path.
        
        Config options:
        - project_path: Path to directory to check (REQUIRED)
        """
        project_path_str = config.get('project_path')
        if not project_path_str:
            return DamlAutomaterResult(
                success=False,
                action="check_project",
                message="❌ Missing required config: project_path",
                instructions="Please provide the path to check for a DAML project.",
                details={
                    "error": "project_path is required",
                    "example": {"project_path": "/Users/you/my-daml-project"}
                }
            )
        
        commands = [
            f"cd {project_path_str}",
            "ls -la",
            "cat daml.yaml"
        ]
        
        instructions = f"""To check if a valid DAML project exists:

1. **Check if directory exists:**
   ```bash
   ls -ld {project_path_str}
   ```

2. **Look for daml.yaml:**
   ```bash
   ls {project_path_str}/daml.yaml
   ```

3. **View project configuration:**
   ```bash
   cat {project_path_str}/daml.yaml
   ```

**A valid DAML project should have:**
- ✅ A `daml.yaml` file in the root
- ✅ Required fields: `name`, `version`, `sdk-version`
- ✅ A `daml/` directory with DAML source files
- ✅ Optional: `dependencies`, `build-options`, `source` path

**Quick validation:**
```bash
cd {project_path_str}
daml build
```
- If this succeeds, the project is valid
- If it fails, check the error messages

**Example valid daml.yaml:**
```yaml
sdk-version: 3.1.0
name: my-project
version: 1.0.0
source: daml
dependencies:
  - daml-prim
  - daml-stdlib
```
"""
        
        return DamlAutomaterResult(
                success=True,
                action="check_project",
                message="📋 Instructions to check DAML project validity",
                commands=commands,
                instructions=instructions,
                details={
                    "project_path": project_path_str,
                    "required_files": ["daml.yaml", "daml/"],
                    "validation_command": "daml build"
                }
            )
    
    def _init_project_instructions(self, config: dict) -> DamlAutomaterResult:
        """
        Provide instructions to initialize boilerplate DAML project structure.
        
        Config options:
        - project_path: Path to create project in (REQUIRED)
        - project_name: Name of the project (default: 'daml-project')
        - sdk_version: DAML SDK version (default: '3.1.0')
        """
        project_path_str = config.get('project_path')
        if not project_path_str:
            return DamlAutomaterResult(
                success=False,
                action="init_project",
                message="❌ Missing required config: project_path",
                instructions="Please provide the path where you want to create the DAML project.",
                details={
                    "error": "project_path is required",
                    "example": {"project_path": "/Users/you/my-daml-project"}
                }
            )
        
        project_name = config.get('project_name', 'daml-project')
        sdk_version = config.get('sdk_version', '3.1.0')
        
        commands = [
            f"mkdir -p {project_path_str}",
            f"cd {project_path_str}",
            "# Create daml.yaml",
            f"cat > daml.yaml << 'EOF'\nsdk-version: {sdk_version}\nname: {project_name}\nversion: 0.0.1\nsource: daml\ndependencies:\n  - daml-prim\n  - daml-stdlib\nEOF",
            "# Create source directory",
            "mkdir -p daml",
            "# Create placeholder module",
            "cat > daml/Main.daml << 'EOF'\nmodule Main where\n\ntemplate Placeholder\n  with\n    party: Party\n  where\n    signatory party\nEOF"
        ]
        
        instructions = f"""To initialize a new DAML project:

**Option 1: Use DAML CLI (Recommended)**
```bash
cd {project_path_str.rsplit('/', 1)[0] if '/' in project_path_str else '.'}
daml new {project_name} --template skeleton
```
This creates a complete project structure with examples.

**Option 2: Manual setup**
```bash
# Create project directory
mkdir -p {project_path_str}
cd {project_path_str}
        
        # Create daml.yaml
cat > daml.yaml << 'EOF'
sdk-version: {sdk_version}
name: {project_name}
version: 0.0.1
source: daml
dependencies:
  - daml-prim
  - daml-stdlib
EOF

# Create source directory
mkdir daml

# Create Main.daml
cat > daml/Main.daml << 'EOF'
module Main where

template Placeholder
  with
    party: Party
  where
    signatory party
EOF
```

**Verify the setup:**
```bash
cd {project_path_str}
daml build
```
Should compile successfully.

**Project structure:**
```
{project_name}/
├── daml.yaml          # Project configuration
└── daml/              # Source files
    └── Main.daml      # Your DAML code
```

**Next steps:**
1. Edit `daml/Main.daml` with your business logic
2. Run `daml build` to compile
3. Run `daml test` to validate (after adding test scenarios)
"""
        
        return DamlAutomaterResult(
            success=True,
            action="init_project",
            message="📋 Instructions to initialize DAML project",
            commands=commands,
            instructions=instructions,
            details={
                "project_path": project_path_str,
                "project_name": project_name,
                "sdk_version": sdk_version,
                "recommended_method": "daml new"
            }
        )

