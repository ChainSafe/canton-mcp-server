"""
Canton Manager - Docker-based Canton Sandbox Lifecycle Management

Manages Canton sandbox environments using Docker containers for isolated,
ephemeral testing and development environments.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Any, List

import docker
import requests
from docker.models.containers import Container

logger = logging.getLogger(__name__)


@dataclass
class CantonEnvironment:
    """Represents a running Canton sandbox environment"""
    
    env_id: str
    container: Optional[Container] = None
    ledger_port: int = 6865
    json_port: int = 7575
    started_at: datetime = field(default_factory=datetime.utcnow)
    config_dir: Optional[Path] = None  # Temp config directory to cleanup
    
    def is_healthy(self) -> bool:
        """Check if Canton is responding"""
        # Check container status first
        if self.container:
            try:
                self.container.reload()
                if self.container.status != "running":
                    return False
            except Exception:
                return False
        
        # Try admin API health check (admin-api.port = ledger_port + 1000)
        admin_port = self.ledger_port + 1000
        try:
            response = requests.get(
                f"http://localhost:{admin_port}/health",
                timeout=2
            )
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False
    
    def stop(self):
        """Stop Canton environment"""
        if self.container:
            try:
                logger.info(f"Stopping container: {self.env_id}")
                self.container.stop(timeout=10)
            except Exception as e:
                logger.error(f"Failed to stop container {self.env_id}: {e}")
    
    def remove(self):
        """Remove Canton container"""
        if self.container:
            try:
                logger.info(f"Removing container: {self.env_id}")
                self.container.remove(force=True)
            except Exception as e:
                logger.error(f"Failed to remove container {self.env_id}: {e}")
        
        # Cleanup temp config directory
        if self.config_dir and self.config_dir.exists():
            try:
                import shutil
                shutil.rmtree(self.config_dir)
                logger.debug(f"Cleaned up config dir: {self.config_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup config dir: {e}")


class CantonManager:
    """
    Manages Canton sandbox environments using Docker.
    
    Provides lifecycle management for isolated Canton instances:
    - Spin up Docker containers running Canton sandbox
    - Health monitoring via /livez endpoint
    - Clean teardown and resource management
    """
    
    def __init__(self):
        """Initialize Canton manager with Docker client"""
        try:
            self.docker_client = docker.from_env()
            # Test Docker connection
            self.docker_client.ping()
            logger.info("✅ Docker client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Docker client: {e}")
            raise RuntimeError(
                "Docker is not available. Please ensure Docker is installed and running."
            ) from e
        
        self.environments: Dict[str, CantonEnvironment] = {}
    
    async def spin_up_docker(
        self,
        dar_path: Optional[str] = None,
        ledger_port: int = 6865,
        json_port: int = 7575,
        canton_image: str = "digitalasset/canton-open-source:latest"
    ) -> CantonEnvironment:
        """
        Start Canton sandbox in Docker container.
        
        Args:
            dar_path: Optional path to DAR file to load
            ledger_port: Port for Ledger API (gRPC)
            json_port: Port for JSON API (HTTP)
            canton_image: Docker image to use
            
        Returns:
            CantonEnvironment instance
            
        Raises:
            RuntimeError: If Canton fails to start or become healthy
        """
        env_id = f"canton-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        # Create minimal Canton config for sandbox mode
        canton_config = f"""
canton {{
  participants {{
    sandbox {{
      storage.type = memory
      ledger-api.port = {ledger_port}
      admin-api.port = {ledger_port + 1000}
    }}
  }}
}}
"""
        
        # Build command - use daemon mode with config
        cmd = ["daemon", "-c", "/canton-config/sandbox.conf"]
        
        # Setup volumes
        import tempfile
        config_dir = Path(tempfile.mkdtemp(prefix="canton-config-"))
        config_file = config_dir / "sandbox.conf"
        config_file.write_text(canton_config)
        
        volumes = {
            str(config_dir): {
                'bind': '/canton-config',
                'mode': 'ro'
            }
        }
        
        if dar_path:
            dar_path_obj = Path(dar_path).resolve()
            if not dar_path_obj.exists():
                raise FileNotFoundError(f"DAR file not found: {dar_path}")
            
            volumes[str(dar_path_obj)] = {
                'bind': '/dars/project.dar',
                'mode': 'ro'
            }
            logger.info(f"📦 Loading DAR: {dar_path_obj.name}")
        
        logger.info(f"🚀 Starting Canton sandbox: {env_id}")
        logger.debug(f"Command: {' '.join(cmd)}")
        logger.debug(f"Ports: Ledger={ledger_port}, JSON={json_port}")
        
        try:
            # Pull image if not present
            try:
                self.docker_client.images.get(canton_image)
            except docker.errors.ImageNotFound:
                logger.info(f"📥 Pulling Canton image: {canton_image}")
                self.docker_client.images.pull(canton_image)
            
            # Start container
            container = self.docker_client.containers.run(
                canton_image,
                command=cmd,
                ports={
                    f'{ledger_port}/tcp': ledger_port,
                    f'{json_port}/tcp': json_port
                },
                volumes=volumes,
                detach=True,
                name=env_id,
                auto_remove=False,  # Keep for debugging/logs
                remove=False
            )
            
            env = CantonEnvironment(
                env_id=env_id,
                container=container,
                ledger_port=ledger_port,
                json_port=json_port,
                config_dir=config_dir
            )
            
            # Wait for Canton to be ready
            logger.info(f"⏳ Waiting for Canton to be ready...")
            if not await self.wait_for_ready(env, timeout=60):
                # Capture logs before cleanup
                logs = container.logs(tail=50).decode('utf-8')
                logger.error(f"Canton logs:\n{logs}")
                
                container.stop()
                container.remove()
                raise RuntimeError(
                    f"Canton failed to start within timeout. Check logs above."
                )
            
            self.environments[env_id] = env
            logger.info(f"✅ Canton sandbox ready: {env_id}")
            logger.info(f"   Ledger API: localhost:{ledger_port}")
            logger.info(f"   JSON API: http://localhost:{json_port}")
            
            return env
            
        except Exception as e:
            logger.error(f"❌ Failed to start Canton: {e}")
            raise
    
    async def wait_for_ready(
        self,
        env: CantonEnvironment,
        timeout: int = 60,
        poll_interval: int = 2
    ) -> bool:
        """
        Wait for Canton to be ready by polling health endpoint.
        
        Args:
            env: Canton environment to check
            timeout: Maximum time to wait in seconds
            poll_interval: Time between health checks in seconds
            
        Returns:
            True if Canton becomes ready, False if timeout
        """
        start_time = time.time()
        attempts = 0
        
        while (time.time() - start_time) < timeout:
            attempts += 1
            
            if env.is_healthy():
                logger.info(f"✅ Canton ready after {attempts} attempts ({int(time.time() - start_time)}s)")
                return True
            
            logger.debug(f"Attempt {attempts}: Canton not ready yet")
            await asyncio.sleep(poll_interval)
        
        logger.error(f"❌ Canton failed to start within {timeout}s")
        return False
    
    def get_status(self, env_id: str) -> Dict[str, Any]:
        """
        Get status of a Canton environment.
        
        Args:
            env_id: Environment ID
            
        Returns:
            Status dictionary with environment details
        """
        env = self.environments.get(env_id)
        if not env:
            return {"exists": False}
        
        container_status = "unknown"
        if env.container:
            try:
                env.container.reload()
                container_status = env.container.status
            except Exception as e:
                logger.error(f"Failed to get container status: {e}")
        
        return {
            "exists": True,
            "env_id": env.env_id,
            "container_status": container_status,
            "ledger_port": env.ledger_port,
            "json_port": env.json_port,
            "started_at": env.started_at.isoformat(),
            "uptime_seconds": int((datetime.utcnow() - env.started_at).total_seconds()),
            "healthy": env.is_healthy()
        }
    
    async def teardown(self, env_id: str):
        """
        Stop and remove a Canton environment.
        
        Args:
            env_id: Environment ID to teardown
        """
        env = self.environments.get(env_id)
        if not env:
            logger.warning(f"Environment not found: {env_id}")
            return
        
        logger.info(f"🧹 Tearing down environment: {env_id}")
        
        # Stop container
        env.stop()
        
        # Remove container
        env.remove()
        
        # Remove from tracking
        del self.environments[env_id]
        logger.info(f"✅ Environment removed: {env_id}")
    
    async def teardown_all(self):
        """Stop and remove all Canton environments"""
        env_ids = list(self.environments.keys())
        logger.info(f"🧹 Tearing down {len(env_ids)} environment(s)")
        
        for env_id in env_ids:
            await self.teardown(env_id)
    
    def list_environments(self) -> List[Dict[str, Any]]:
        """
        List all running Canton environments.
        
        Returns:
            List of environment status dictionaries
        """
        return [self.get_status(env_id) for env_id in self.environments.keys()]

