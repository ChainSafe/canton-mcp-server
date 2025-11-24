"""
DAML Tester - DAML Test Execution and Result Parsing

Executes DAML test suites and parses test results for reporting.
"""

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of DAML test execution"""
    
    success: bool
    tests_run: int
    tests_passed: int
    tests_failed: int
    duration_seconds: float
    output: str
    failures: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        status = "✅ PASSED" if self.success else "❌ FAILED"
        return (
            f"{status}: {self.tests_passed}/{self.tests_run} tests "
            f"({self.duration_seconds:.1f}s)"
        )


class DAMLTester:
    """
    Runs DAML tests and parses results.
    
    Executes `daml test` command and analyzes output to provide
    structured test results.
    """
    
    async def run_tests(
        self,
        project_path: Path,
        test_filter: str = None
    ) -> TestResult:
        """
        Run DAML tests for a project.
        
        Args:
            project_path: Path to DAML project directory
            test_filter: Optional filter for specific tests
            
        Returns:
            TestResult with execution details
            
        Raises:
            FileNotFoundError: If project doesn't exist
            RuntimeError: If daml command fails to execute
        """
        project_path = Path(project_path).resolve()
        
        if not (project_path / "daml.yaml").exists():
            raise FileNotFoundError(
                f"daml.yaml not found in {project_path}. "
                "Is this a valid DAML project?"
            )
        
        logger.info(f"🧪 Running DAML tests: {project_path.name}")
        
        # Build command
        cmd = ["daml", "test"]
        if test_filter:
            cmd.extend(["--", "-m", test_filter])
        
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=180  # 3 minute timeout for tests
            )
            
            duration = time.time() - start_time
            
            # Capture output
            output = result.stdout + result.stderr
            
            # Parse test results
            test_result = self._parse_test_output(output, result.returncode, duration)
            
            if test_result.success:
                logger.info(f"✅ {test_result}")
            else:
                logger.warning(f"❌ {test_result}")
                if test_result.failures:
                    logger.warning("Failures:")
                    for failure in test_result.failures:
                        logger.warning(f"  - {failure}")
            
            return test_result
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return TestResult(
                success=False,
                tests_run=0,
                tests_passed=0,
                tests_failed=0,
                duration_seconds=duration,
                output="Test execution timed out after 180 seconds",
                failures=["Timeout: Tests did not complete within 3 minutes"]
            )
        except FileNotFoundError:
            raise RuntimeError(
                "daml command not found. Is DAML SDK installed? "
                "Install from: https://docs.daml.com/getting-started/installation.html"
            )
    
    def _parse_test_output(
        self,
        output: str,
        exit_code: int,
        duration: float
    ) -> TestResult:
        """
        Parse daml test output to extract test results.
        
        Args:
            output: Combined stdout and stderr from daml test
            exit_code: Process exit code
            duration: Test execution duration
            
        Returns:
            TestResult with parsed information
        """
        # Look for test result indicators
        # DAML test output typically shows:
        # - "✓" or "ok" for passed tests
        # - "✗" or "FAIL" for failed tests
        # - Summary lines like "X tests, Y failures"
        
        # Count passed/failed tests
        passed_matches = re.findall(r'✓|(?:^|\s)ok(?:\s|$)', output, re.MULTILINE)
        failed_matches = re.findall(r'✗|FAIL', output)
        
        tests_passed = len(passed_matches)
        tests_failed = len(failed_matches)
        tests_run = tests_passed + tests_failed
        
        # Extract failure messages
        failures = []
        
        # Look for common failure patterns
        failure_patterns = [
            r'✗\s+(.+?)(?=\n|$)',  # ✗ followed by failure message
            r'FAIL\s+(.+?)(?=\n|$)',  # FAIL followed by test name
            r'failed:\s+(.+?)(?=\n|$)',  # "failed: ..." messages
        ]
        
        for pattern in failure_patterns:
            matches = re.findall(pattern, output, re.MULTILINE)
            failures.extend(matches)
        
        # Remove duplicates and clean up
        failures = list(dict.fromkeys(failures))  # Preserve order, remove dupes
        failures = [f.strip() for f in failures if f.strip()]
        
        # Determine success
        # Exit code 0 typically means all tests passed
        success = (exit_code == 0) and (tests_failed == 0)
        
        # Handle case where no tests were found
        if tests_run == 0 and exit_code == 0:
            # No tests might be ok, or might indicate an issue
            # Check output for indicators
            if "No tests to run" in output or "0 tests" in output:
                logger.info("No tests found in project")
                success = True
            else:
                logger.warning("Unable to parse test results from output")
        
        return TestResult(
            success=success,
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            duration_seconds=duration,
            output=output,
            failures=failures
        )

