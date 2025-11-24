"""
DAML Compiler Integration

Subprocess wrapper for `daml build` validation.
Provides Gate 1: DAML Compiler Safety validation.
"""

import asyncio
import hashlib
import logging
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .types import (
    CompilationError,
    CompilationResult,
    CompilationStatus,
    ErrorCategory,
)

logger = logging.getLogger(__name__)


class DamlCompilerError(Exception):
    """Raised when DAML compiler integration encounters a system error"""

    pass


class DamlCompiler:
    """
    DAML compiler subprocess wrapper.

    Validates DAML code through compilation, providing:
    - Type safety guarantees
    - Authorization model enforcement
    - Syntax validation
    """

    def __init__(
        self,
        sdk_version: str = "2.9.0",
        compilation_timeout: int = 30,
        daml_command: str = "daml",
    ):
        """
        Initialize DAML compiler integration.

        Args:
            sdk_version: DAML SDK version to use
            compilation_timeout: Max seconds for compilation
            daml_command: Path to daml command (default: "daml" in PATH)
        """
        self.sdk_version = sdk_version
        self.compilation_timeout = compilation_timeout
        self.daml_command = daml_command

        # Verify daml command exists
        if not shutil.which(self.daml_command):
            raise DamlCompilerError(
                f"DAML compiler not found. Please install DAML SDK: {self.daml_command}"
            )

        logger.info(
            f"DAML compiler initialized (SDK version: {sdk_version}, "
            f"timeout: {compilation_timeout}s)"
        )

    async def compile(
        self, code: str, module_name: str = "Main", strict_mode: bool = True
    ) -> CompilationResult:
        """
        Compile DAML code and return validation result.

        Creates a temporary project, runs `daml build`, and parses the output.

        Args:
            code: DAML source code to compile
            module_name: Module name (default: "Main")
            strict_mode: Enable strict compilation flags (default: True)

        Returns:
            CompilationResult with status, errors, and metadata

        Raises:
            DamlCompilerError: If system error occurs (not code errors)
        """
        start_time = time.time()

        try:
            # Create temporary project
            with tempfile.TemporaryDirectory(prefix="daml_safety_") as tmpdir:
                project_dir = Path(tmpdir)
                logger.debug(f"Created temp project: {project_dir}")

                # Set up project structure
                self._create_project(project_dir, code, module_name, strict_mode)

                # Run daml build
                process_result = await self._run_daml_build(project_dir)

                # Parse output
                compilation_time_ms = int((time.time() - start_time) * 1000)
                result = self._parse_output(process_result, compilation_time_ms)

                logger.info(
                    f"Compilation completed: {result.status.value} "
                    f"({compilation_time_ms}ms, {len(result.errors)} errors)"
                )

                return result

        except asyncio.TimeoutError:
            raise DamlCompilerError(
                f"DAML compilation timed out after {self.compilation_timeout}s"
            )
        except Exception as e:
            logger.error(f"DAML compilation system error: {e}", exc_info=True)
            raise DamlCompilerError(f"DAML compilation system error: {e}") from e

    def _create_project(
        self, project_dir: Path, code: str, module_name: str, strict_mode: bool
    ):
        """
        Create DAML project structure in temp directory.

        Creates:
        - daml.yaml (project config)
        - daml/<module>.daml (source code)
        """
        # Create daml.yaml
        daml_yaml_content = self._generate_daml_yaml(module_name, strict_mode)
        (project_dir / "daml.yaml").write_text(daml_yaml_content)

        # Create source directory
        daml_dir = project_dir / "daml"
        daml_dir.mkdir()

        # Write source code
        source_file = daml_dir / f"{module_name}.daml"
        source_file.write_text(code)

        logger.debug(f"Project structure created: {project_dir}")

    def _generate_daml_yaml(self, module_name: str, strict_mode: bool) -> str:
        """
        Generate daml.yaml configuration.

        Args:
            module_name: Module name
            strict_mode: Enable strict compilation flags

        Returns:
            daml.yaml content as string
        """
        # Base config
        config = f"""sdk-version: {self.sdk_version}
name: safety-check
source: daml
version: 1.0.0
dependencies:
  - daml-prim
  - daml-stdlib
"""

        # Add strict build options if enabled
        if strict_mode:
            config += """build-options:
  - --ghc-option=-Werror
  - --ghc-option=-Wunused-top-binds
  - --ghc-option=-Wincomplete-uni-patterns
  - --ghc-option=-Wredundant-constraints
  - --ghc-option=-Wmissing-signatures
"""

        return config

    async def _run_daml_build(self, project_dir: Path) -> subprocess.CompletedProcess:
        """
        Execute `daml build` subprocess.

        Args:
            project_dir: Path to DAML project

        Returns:
            CompletedProcess with stdout/stderr

        Raises:
            asyncio.TimeoutError: If compilation times out
        """
        logger.debug(f"Running: {self.daml_command} build in {project_dir}")

        process = await asyncio.create_subprocess_exec(
            self.daml_command,
            "build",
            cwd=str(project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self.compilation_timeout
            )

            return subprocess.CompletedProcess(
                args=[self.daml_command, "build"],
                returncode=process.returncode or 0,
                stdout=stdout.decode("utf-8"),
                stderr=stderr.decode("utf-8"),
            )

        except asyncio.TimeoutError:
            # Kill the process if it times out
            process.kill()
            await process.wait()
            raise

    def _parse_output(
        self, result: subprocess.CompletedProcess, compilation_time_ms: int
    ) -> CompilationResult:
        """
        Parse `daml build` output into CompilationResult.

        Args:
            result: Subprocess result
            compilation_time_ms: Time taken for compilation

        Returns:
            CompilationResult with parsed errors and status
        """
        # Compilation succeeded if exit code is 0
        if result.returncode == 0:
            return CompilationResult(
                status=CompilationStatus.SUCCESS,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                compilation_time_ms=compilation_time_ms,
            )

        # Parse errors from stderr
        errors = self._parse_errors(result.stderr)

        return CompilationResult(
            status=CompilationStatus.FAILED,
            errors=errors,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            compilation_time_ms=compilation_time_ms,
        )

    def _parse_errors(self, stderr: str) -> list[CompilationError]:
        """
        Parse error messages from DAML compiler stderr.

        Supports both formats:
        1. GHC-style (DAML ≤2.9): `daml/Main.daml:10:5: error:`
        2. Structured (DAML ≥2.10): `File: ... Range: ... Message: ...`

        Args:
            stderr: Compiler stderr output

        Returns:
            List of parsed CompilationErrors
        """
        errors = []

        # Try new structured format first (DAML 2.10+)
        errors.extend(self._parse_structured_errors(stderr))

        # Fallback to GHC-style format (DAML 2.9 and earlier)
        if not errors:
            errors.extend(self._parse_ghc_errors(stderr))

        logger.debug(f"Parsed {len(errors)} errors from compiler output")
        return errors

    def _parse_structured_errors(self, stderr: str) -> list[CompilationError]:
        """Parse DAML 2.10+ structured error format"""
        errors = []
        lines = stderr.split("\n")
        i = 0

        while i < len(lines):
            # Look for structured error block
            if lines[i].startswith("File:"):
                file_path = lines[i].split("File:", 1)[1].strip()
                i += 1

                # Extract Range (e.g., "6:10-6:16") - may be a few lines down
                line_num, col_num = 0, 0
                # Search for Range within next few lines
                j = i
                while j < min(i + 5, len(lines)):
                    if lines[j].startswith("Range:"):
                        range_str = lines[j].split("Range:", 1)[1].strip()
                        # Parse "6:10-6:16" -> line=6, col=10
                        if ":" in range_str:
                            parts = range_str.split("-")[0].split(":")
                            if len(parts) >= 2:
                                line_num = int(parts[0])
                                col_num = int(parts[1])
                        break
                    j += 1

                # Skip to Message line
                while i < len(lines) and not lines[i].startswith("Message:"):
                    i += 1

                if i < len(lines) and lines[i].startswith("Message:"):
                    i += 1
                    # Collect message (may be multi-line, ANSI-colored)
                    message_lines = []
                    while i < len(lines) and not lines[i].startswith("File:") and lines[i].strip():
                        # Strip ANSI color codes
                        clean_line = re.sub(r'\x1b\[[0-9;]+m', '', lines[i])
                        if "error:" in clean_line.lower():
                            # Extract error message after "error:" (case-insensitive)
                            error_match = re.search(r'error:\s*(.+)', clean_line, re.IGNORECASE)
                            if error_match:
                                message_lines.append(error_match.group(1).strip())
                            else:
                                message_lines.append(clean_line.strip())
                        elif clean_line.strip():
                            message_lines.append(clean_line.strip())
                        i += 1

                    message = "\n".join(message_lines) if message_lines else "Unknown error"
                    category = self._categorize_error(message)

                    errors.append(
                        CompilationError(
                            file_path=file_path,
                            line=line_num,
                            column=col_num,
                            category=category,
                            message=message,
                            raw_error=f"{file_path}:{line_num}:{col_num}: {message}",
                        )
                    )
            else:
                i += 1

        return errors

    def _parse_ghc_errors(self, stderr: str) -> list[CompilationError]:
        """Parse GHC-style error format (DAML ≤2.9)"""
        errors = []

        # Pattern: file:line:column: error/warning:
        error_pattern = re.compile(
            r"^(.+):(\d+):(\d+):\s+(error|warning):\s*$", re.MULTILINE
        )

        # Split stderr into chunks by error/warning markers
        lines = stderr.split("\n")
        i = 0

        while i < len(lines):
            match = error_pattern.match(lines[i])
            if match:
                file_path = match.group(1)
                line_num = int(match.group(2))
                col_num = int(match.group(3))
                error_type = match.group(4)

                # Collect error message lines (indented lines following the marker)
                message_lines = []
                i += 1
                while i < len(lines) and (
                    lines[i].startswith(" ") or lines[i].startswith("\t")
                ):
                    message_lines.append(lines[i].strip())
                    i += 1

                message = "\n".join(message_lines)

                # Categorize error
                category = self._categorize_error(message)

                # Skip warnings in strict mode (treated as errors by -Werror)
                if error_type == "error" or True:  # All are errors in strict mode
                    errors.append(
                        CompilationError(
                            file_path=file_path,
                            line=line_num,
                            column=col_num,
                            category=category,
                            message=message,
                            raw_error=f"{file_path}:{line_num}:{col_num}: {message}",
                        )
                    )
            else:
                i += 1

        return errors

    def _categorize_error(self, error_msg: str) -> ErrorCategory:
        """
        Categorize error by analyzing error message.

        Args:
            error_msg: Error message text

        Returns:
            ErrorCategory enum value
        """
        error_lower = error_msg.lower()

        # Authorization errors
        auth_keywords = [
            "authorization",
            "signatory",
            "observer",
            "controller",
            "maintainer",
            "authority",
        ]
        if any(kw in error_lower for kw in auth_keywords):
            return ErrorCategory.AUTHORIZATION

        # Type errors
        type_keywords = [
            "type",
            "couldn't match",
            "expected type",
            "actual type",
            "no instance",
            "ambiguous",
        ]
        if any(kw in error_lower for kw in type_keywords):
            return ErrorCategory.TYPE_SAFETY

        # Syntax errors
        syntax_keywords = ["parse error", "unexpected", "lexical error"]
        if any(kw in error_lower for kw in syntax_keywords):
            return ErrorCategory.SYNTAX

        # Default to OTHER
        return ErrorCategory.OTHER

    def get_code_hash(self, code: str) -> str:
        """
        Generate SHA256 hash of DAML code.

        Args:
            code: DAML source code

        Returns:
            Hex digest of SHA256 hash
        """
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

