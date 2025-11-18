"""
DAML Builder - DAML Project Compilation and Configuration

Handles building DAML projects, parsing daml.yaml configuration,
and managing DAR file generation.
"""

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class DAMLProject:
    """Represents a DAML project with its configuration"""
    
    name: str
    version: str
    sdk_version: str
    source_path: Path
    dar_path: Optional[Path] = None
    
    def __str__(self) -> str:
        return f"{self.name}-{self.version} (SDK {self.sdk_version})"


class DAMLBuilder:
    """
    Builds DAML projects and manages project configuration.
    
    Parses daml.yaml files to extract project metadata and
    compiles DAML code into DAR (DAML Archive) files.
    """
    
    @staticmethod
    def parse_daml_yaml(project_path: Path) -> DAMLProject:
        """
        Parse daml.yaml configuration file.
        
        Args:
            project_path: Path to DAML project directory
            
        Returns:
            DAMLProject with parsed configuration
            
        Raises:
            FileNotFoundError: If daml.yaml doesn't exist
            ValueError: If required fields are missing
        """
        project_path = Path(project_path).resolve()
        daml_yaml = project_path / "daml.yaml"
        
        if not daml_yaml.exists():
            raise FileNotFoundError(
                f"daml.yaml not found in {project_path}. "
                "Is this a valid DAML project?"
            )
        
        logger.debug(f"Parsing daml.yaml: {daml_yaml}")
        
        with open(daml_yaml, 'r') as f:
            config = yaml.safe_load(f)
        
        if not config:
            raise ValueError(f"daml.yaml is empty or invalid: {daml_yaml}")
        
        # Extract required fields
        name = config.get('name')
        version = config.get('version')
        sdk_version = config.get('sdk-version')
        
        if not name:
            raise ValueError("daml.yaml missing required field: name")
        if not version:
            raise ValueError("daml.yaml missing required field: version")
        if not sdk_version:
            raise ValueError("daml.yaml missing required field: sdk-version")
        
        project = DAMLProject(
            name=name,
            version=version,
            sdk_version=sdk_version,
            source_path=project_path
        )
        
        logger.info(f"📋 Parsed project: {project}")
        return project
    
    async def build(self, project_path: Path) -> DAMLProject:
        """
        Build DAML project to DAR file.
        
        Args:
            project_path: Path to DAML project directory
            
        Returns:
            DAMLProject with dar_path populated
            
        Raises:
            FileNotFoundError: If daml.yaml doesn't exist
            RuntimeError: If build fails
        """
        project_path = Path(project_path).resolve()
        
        # Parse project configuration
        project = self.parse_daml_yaml(project_path)
        
        logger.info(f"🔨 Building DAML project: {project}")
        
        # Run daml build
        try:
            result = subprocess.run(
                ["daml", "build"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )
            
            if result.returncode != 0:
                logger.error(f"DAML build failed (exit code {result.returncode})")
                logger.error(f"stdout: {result.stdout}")
                logger.error(f"stderr: {result.stderr}")
                raise RuntimeError(
                    f"DAML build failed: {result.stderr or result.stdout}"
                )
            
            logger.debug(f"Build output: {result.stdout}")
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("DAML build timed out after 120 seconds")
        except FileNotFoundError:
            raise RuntimeError(
                "daml command not found. Is DAML SDK installed? "
                "Install from: https://docs.daml.com/getting-started/installation.html"
            )
        
        # Find generated DAR file
        dar_path = (
            project_path / ".daml" / "dist" /
            f"{project.name}-{project.version}.dar"
        )
        
        if not dar_path.exists():
            raise RuntimeError(
                f"DAR file not found after build: {dar_path}. "
                "Build may have succeeded but DAR location is unexpected."
            )
        
        project.dar_path = dar_path
        logger.info(f"✅ Built DAR: {dar_path.name} ({dar_path.stat().st_size / 1024:.1f} KB)")
        
        return project

