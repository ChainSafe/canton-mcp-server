"""
DAML Automater Tool - CI/CD and Environment Automation

This tool handles DAML development automation tasks such as:
- Spinning up local Canton environments
- Running tests in CI/CD
- Building DAML projects
- Managing Canton network connections
- Automating builds and deployments
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

from pydantic import Field

from ..core import Tool, ToolContext, register_tool
from ..core.canton_manager import CantonManager
from ..core.daml_builder import DAMLBuilder
from ..core.daml_tester import DAMLTester
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
- sdk_version: DAML SDK version (for init_project, default: '3.1.0')

IMPORTANT: Use absolute paths for project_path. The MCP server runs in its own directory,
not the client's working directory. Example: '/Users/you/my-daml-project'"""
    )


class DamlAutomaterResult(MCPModel):
    """Result from DAML Automater execution"""

    success: bool = Field(description="Whether the automation action succeeded")
    action: str = Field(description="The action that was performed")
    message: str = Field(description="Result message")
    details: Optional[dict] = Field(default=None, description="Additional details about the result")


@register_tool
class DamlAutomaterTool(Tool[DamlAutomaterParams, DamlAutomaterResult]):
    """
    DAML Automater - CI/CD and Environment Automation
    
    Handles automation tasks for DAML development:
    - Spin up local Canton environments using Docker
    - Run automated tests
    - Build DAML projects to DAR files
    - Manage Canton environment lifecycle
    """

    name = "daml_automater"
    description = (
        "🤖 DAML Automater - CI/CD and environment automation. "
        "Spins up Canton environments in Docker, runs tests, and builds projects."
    )
    params_model = DamlAutomaterParams
    result_model = DamlAutomaterResult
    
    pricing = ToolPricing(
        type=PricingType.FIXED,
        base_cost=0.0,
        description="Automation actions (free)"
    )
    
    def __init__(self):
        """Initialize automation managers"""
        super().__init__()
        self._canton_manager: Optional[CantonManager] = None
        self._daml_builder: Optional[DAMLBuilder] = None
        self._daml_tester: Optional[DAMLTester] = None
    
    def _ensure_managers(self):
        """Lazy initialization of managers"""
        if self._canton_manager is None:
            self._canton_manager = CantonManager()
        if self._daml_builder is None:
            self._daml_builder = DAMLBuilder()
        if self._daml_tester is None:
            self._daml_tester = DAMLTester()

    async def execute(
        self, ctx: ToolContext[DamlAutomaterParams, DamlAutomaterResult]
    ):
        """
        Execute DAML automation action.
        
        Supported actions:
        - spin_up_env: Start Canton sandbox in Docker
        - run_tests: Execute DAML tests
        - build_dar: Build DAML project to DAR
        - status: Check Canton environment status
        - teardown_env: Stop and remove Canton environment
        - check_project: Verify if valid DAML project exists
        - init_project: Initialize boilerplate DAML project structure
        """
        action = ctx.params.action
        environment = ctx.params.environment or "local"
        config = ctx.params.config or {}
        
        logger.info(f"🤖 DAML Automater: action={action}, environment={environment}")
        
        # Ensure managers are initialized
        self._ensure_managers()
        
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
            elif action == "check_project":
                result = await self._check_project(config)
            elif action == "init_project":
                result = await self._init_project(config)
            else:
                result = DamlAutomaterResult(
                    success=False,
                    action=action,
                    message=f"Unknown action: {action}",
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
            logger.error(f"❌ Automation failed: {e}", exc_info=True)
            yield ctx.structured(DamlAutomaterResult(
                success=False,
                action=action,
                message=f"Error: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            ))
    
    async def _spin_up_env(self, config: dict) -> DamlAutomaterResult:
        """
        Spin up Canton sandbox environment in Docker.
        
        Config options:
        - dar_path: Optional path to DAR file to preload
        - ledger_api_port: Port for Ledger API (default: 6865)
        - json_api_port: Port for JSON API (default: 7575)
        - canton_image: Docker image to use (default: digitalasset/canton-open-source:latest)
        """
        dar_path = config.get('dar_path')
        ledger_port = config.get('ledger_api_port', 6865)
        json_port = config.get('json_api_port', 7575)
        canton_image = config.get('canton_image', 'digitalasset/canton-open-source:latest')
        
        logger.info(f"🚀 Spinning up Canton sandbox...")
        
        env = await self._canton_manager.spin_up_docker(
            dar_path=dar_path,
            ledger_port=ledger_port,
            json_port=json_port,
            canton_image=canton_image
        )
        
        return DamlAutomaterResult(
            success=True,
            action="spin_up_env",
            message=f"✅ Canton sandbox started: {env.env_id}",
            details={
                "env_id": env.env_id,
                "ledger_api_endpoint": f"localhost:{env.ledger_port}",
                "json_api_endpoint": f"http://localhost:{env.json_port}",
                "health_status": "ready",
                "started_at": env.started_at.isoformat(),
                "dar_loaded": dar_path is not None
            }
        )
    
    async def _run_tests(self, config: dict) -> DamlAutomaterResult:
        """
        Run DAML tests for a project.
        
        Config options:
        - project_path: Absolute path to DAML project (REQUIRED)
        - test_filter: Optional filter for specific tests
        """
        project_path_str = config.get('project_path')
        if not project_path_str:
            return DamlAutomaterResult(
                success=False,
                action="run_tests",
                message="❌ Missing required config: project_path (must be absolute path to DAML project)",
                details={
                    "error": "project_path is required",
                    "example": {"project_path": "/Users/you/my-daml-project"}
                }
            )
        
        project_path = Path(project_path_str)
        test_filter = config.get('test_filter')
        
        logger.info(f"🧪 Running DAML tests: {project_path}")
        
        test_result = await self._daml_tester.run_tests(
            project_path=project_path,
            test_filter=test_filter
        )
        
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
                "output_preview": test_result.output[:500] if test_result.output else ""
            }
        )
    
    async def _build_dar(self, config: dict) -> DamlAutomaterResult:
        """
        Build DAML project to DAR file.
        
        Config options:
        - project_path: Absolute path to DAML project (REQUIRED)
        """
        project_path_str = config.get('project_path')
        if not project_path_str:
            return DamlAutomaterResult(
                success=False,
                action="build_dar",
                message="❌ Missing required config: project_path (must be absolute path to DAML project)",
                details={
                    "error": "project_path is required",
                    "example": {"project_path": "/Users/you/my-daml-project"}
                }
            )
        
        project_path = Path(project_path_str)
        
        logger.info(f"🔨 Building DAML project: {project_path}")
        
        project = await self._daml_builder.build(project_path)
        
        dar_size_kb = project.dar_path.stat().st_size / 1024 if project.dar_path else 0
        
        return DamlAutomaterResult(
            success=True,
            action="build_dar",
            message=f"✅ Built DAR: {project.dar_path.name}",
            details={
                "dar_path": str(project.dar_path),
                "dar_size_kb": round(dar_size_kb, 1),
                "project_name": project.name,
                "version": project.version,
                "sdk_version": project.sdk_version
            }
        )
    
    async def _get_status(self, config: dict) -> DamlAutomaterResult:
        """
        Get status of Canton environments.
        
        Config options:
        - env_id: Optional specific environment ID to check
        """
        env_id = config.get('env_id')
        
        if env_id:
            # Get specific environment status
            status = self._canton_manager.get_status(env_id)
            if not status.get('exists'):
                return DamlAutomaterResult(
                    success=False,
                    action="status",
                    message=f"❌ Environment not found: {env_id}",
                    details={"env_id": env_id}
                )
            
            return DamlAutomaterResult(
                success=True,
                action="status",
                message=f"Environment status: {env_id}",
                details=status
            )
        else:
            # List all environments
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
                details={"environments": envs, "count": len(envs)}
            )
    
    async def _teardown_env(self, config: dict) -> DamlAutomaterResult:
        """
        Teardown Canton environment(s).
        
        Config options:
        - env_id: Specific environment ID to teardown (if not provided, tears down all)
        """
        env_id = config.get('env_id')
        
        if env_id:
            logger.info(f"🧹 Tearing down environment: {env_id}")
            await self._canton_manager.teardown(env_id)
            message = f"✅ Stopped environment: {env_id}"
            details = {"env_id": env_id}
        else:
            # Teardown all
            envs = list(self._canton_manager.environments.keys())
            logger.info(f"🧹 Tearing down {len(envs)} environment(s)")
            await self._canton_manager.teardown_all()
            message = f"✅ Stopped {len(envs)} environment(s)"
            details = {"environments_stopped": envs, "count": len(envs)}
        
        return DamlAutomaterResult(
            success=True,
            action="teardown_env",
            message=message,
            details=details
        )
    
    async def _check_project(self, config: dict) -> DamlAutomaterResult:
        """
        Check if valid DAML project exists at path.
        
        Config options:
        - project_path: Absolute path to directory to check (REQUIRED)
        """
        project_path_str = config.get('project_path')
        if not project_path_str:
            return DamlAutomaterResult(
                success=False,
                action="check_project",
                message="❌ Missing required config: project_path",
                details={
                    "error": "project_path is required",
                    "example": {"project_path": "/Users/you/my-daml-project"}
                }
            )
        
        project_path = Path(project_path_str)
        
        logger.info(f"🔍 Checking DAML project: {project_path}")
        
        # Check if directory exists
        if not project_path.exists():
            return DamlAutomaterResult(
                success=True,
                action="check_project",
                message=f"Directory does not exist: {project_path}",
                details={
                    "exists": False,
                    "is_directory": False,
                    "has_daml_yaml": False,
                    "valid": False,
                    "project_path": str(project_path)
                }
            )
        
        if not project_path.is_dir():
            return DamlAutomaterResult(
                success=True,
                action="check_project",
                message=f"Path exists but is not a directory: {project_path}",
                details={
                    "exists": True,
                    "is_directory": False,
                    "has_daml_yaml": False,
                    "valid": False,
                    "project_path": str(project_path)
                }
            )
        
        # Check for daml.yaml
        daml_yaml = project_path / "daml.yaml"
        has_daml_yaml = daml_yaml.exists()
        
        if not has_daml_yaml:
            return DamlAutomaterResult(
                success=True,
                action="check_project",
                message=f"Directory exists but no daml.yaml found: {project_path}",
                details={
                    "exists": True,
                    "is_directory": True,
                    "has_daml_yaml": False,
                    "valid": False,
                    "project_path": str(project_path)
                }
            )
        
        # Try to parse daml.yaml
        try:
            project = self._daml_builder.parse_daml_yaml(project_path)
            
            return DamlAutomaterResult(
                success=True,
                action="check_project",
                message=f"✅ Valid DAML project: {project.name}",
                details={
                    "exists": True,
                    "is_directory": True,
                    "has_daml_yaml": True,
                    "valid": True,
                    "project_path": str(project_path),
                    "project_info": {
                        "name": project.name,
                        "version": project.version,
                        "sdk_version": project.sdk_version
                    }
                }
            )
        except Exception as e:
            return DamlAutomaterResult(
                success=True,
                action="check_project",
                message=f"⚠️ daml.yaml exists but is invalid: {str(e)}",
                details={
                    "exists": True,
                    "is_directory": True,
                    "has_daml_yaml": True,
                    "valid": False,
                    "project_path": str(project_path),
                    "parse_error": str(e)
                }
            )
    
    async def _init_project(self, config: dict) -> DamlAutomaterResult:
        """
        Initialize boilerplate DAML project structure.
        
        Config options:
        - project_path: Absolute path to create project in (REQUIRED)
        - project_name: Name of the project (default: 'daml-project')
        - sdk_version: DAML SDK version (default: '3.1.0')
        
        SAFETY: Will NOT overwrite existing daml.yaml
        """
        project_path_str = config.get('project_path')
        if not project_path_str:
            return DamlAutomaterResult(
                success=False,
                action="init_project",
                message="❌ Missing required config: project_path",
                details={
                    "error": "project_path is required",
                    "example": {"project_path": "/Users/you/my-daml-project"}
                }
            )
        
        project_path = Path(project_path_str)
        project_name = config.get('project_name', 'daml-project')
        sdk_version = config.get('sdk_version', '3.1.0')
        
        logger.info(f"🏗️ Initializing DAML project: {project_path}")
        
        # Create directory if it doesn't exist
        try:
            project_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return DamlAutomaterResult(
                success=False,
                action="init_project",
                message=f"❌ Failed to create directory: {str(e)}",
                details={"error": str(e), "project_path": str(project_path)}
            )
        
        # SAFETY CHECK: Fail if daml.yaml already exists
        daml_yaml = project_path / "daml.yaml"
        if daml_yaml.exists():
            return DamlAutomaterResult(
                success=False,
                action="init_project",
                message=f"❌ daml.yaml already exists at {project_path}. Will not overwrite.",
                details={
                    "error": "daml.yaml already exists",
                    "project_path": str(project_path),
                    "safety": "init_project will not overwrite existing files"
                }
            )
        
        # Create daml.yaml
        daml_yaml_content = f"""sdk-version: {sdk_version}
name: {project_name}
version: 0.0.1
source: daml
dependencies:
  - daml-prim
  - daml-stdlib
"""
        
        try:
            daml_yaml.write_text(daml_yaml_content)
            logger.info(f"✅ Created daml.yaml")
        except Exception as e:
            return DamlAutomaterResult(
                success=False,
                action="init_project",
                message=f"❌ Failed to create daml.yaml: {str(e)}",
                details={"error": str(e)}
            )
        
        # Create daml/ directory
        daml_dir = project_path / "daml"
        try:
            daml_dir.mkdir(exist_ok=True)
            logger.info(f"✅ Created daml/ directory")
        except Exception as e:
            return DamlAutomaterResult(
                success=False,
                action="init_project",
                message=f"❌ Failed to create daml/ directory: {str(e)}",
                details={"error": str(e)}
            )
        
        # Create placeholder Main.daml
        main_daml = daml_dir / "Main.daml"
        if not main_daml.exists():  # Only create if doesn't exist
            main_daml_content = f"""-- Main module for {project_name}
module Main where

-- TODO: Add your DAML code here
-- This is a placeholder file to get you started

template Placeholder
  with
    party: Party
  where
    signatory party
"""
            try:
                main_daml.write_text(main_daml_content)
                logger.info(f"✅ Created Main.daml placeholder")
            except Exception as e:
                logger.warning(f"Failed to create Main.daml: {e}")
        
        return DamlAutomaterResult(
            success=True,
            action="init_project",
            message=f"✅ Initialized DAML project: {project_name}",
            details={
                "project_path": str(project_path),
                "project_name": project_name,
                "sdk_version": sdk_version,
                "files_created": [
                    str(daml_yaml.relative_to(project_path)),
                    str(daml_dir.relative_to(project_path)),
                    str(main_daml.relative_to(project_path)) if main_daml.exists() else None
                ]
            }
        )

