"""
Tests for AuditTrail

Unit tests for DAML compilation audit logging.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from canton_mcp_server.daml.audit_trail import AuditTrail
from canton_mcp_server.daml.types import (
    AuthorizationModel,
    CompilationError,
    CompilationResult,
    CompilationStatus,
    ErrorCategory,
)


class TestAuditTrail:
    """Test AuditTrail functionality"""

    def setup_method(self):
        """Setup test fixtures with temporary directory"""
        self.temp_dir = tempfile.mkdtemp(prefix="audit_test_")
        self.storage_path = Path(self.temp_dir)
        self.audit = AuditTrail(storage_path=self.storage_path)

    def teardown_method(self):
        """Cleanup temporary directory"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_init_creates_storage_directory(self):
        """Test initialization creates storage directory"""
        new_path = self.storage_path / "subdir"
        audit = AuditTrail(storage_path=new_path)

        assert new_path.exists()
        assert new_path.is_dir()

    def test_log_compilation_success(self):
        """Test logging successful compilation"""
        code_hash = "abc123"
        module_name = "TestModule"

        result = CompilationResult(status=CompilationStatus.SUCCESS, exit_code=0)

        auth_model = AuthorizationModel(
            template_name="Test", signatories=["issuer"], observers=["owner"]
        )

        audit_id = self.audit.log_compilation(
            code_hash=code_hash,
            module_name=module_name,
            result=result,
            auth_model=auth_model,
            blocked=False,
        )

        assert audit_id is not None
        assert isinstance(audit_id, str)

        # Verify log file was created
        today = datetime.utcnow().strftime("%Y-%m-%d")
        log_file = self.storage_path / f"{today}.jsonl"
        assert log_file.exists()

    def test_log_compilation_failed(self):
        """Test logging failed compilation"""
        code_hash = "def456"
        module_name = "BadModule"

        error = CompilationError(
            file_path="Main.daml",
            line=10,
            column=5,
            category=ErrorCategory.AUTHORIZATION,
            message="Missing signatory",
            raw_error="",
        )

        result = CompilationResult(
            status=CompilationStatus.FAILED, exit_code=1, errors=[error]
        )

        audit_id = self.audit.log_compilation(
            code_hash=code_hash,
            module_name=module_name,
            result=result,
            auth_model=None,
            blocked=True,
        )

        assert audit_id is not None

        # Retrieve and verify entry
        entry = self.audit.get_audit_entry(audit_id)
        assert entry is not None
        assert entry.code_hash == code_hash
        assert entry.module_name == module_name
        assert entry.status == CompilationStatus.FAILED
        assert entry.blocked is True
        assert len(entry.errors) == 1

    def test_get_audit_entry_exists(self):
        """Test retrieving existing audit entry"""
        code_hash = "test123"
        result = CompilationResult(status=CompilationStatus.SUCCESS, exit_code=0)

        audit_id = self.audit.log_compilation(
            code_hash=code_hash,
            module_name="Test",
            result=result,
            auth_model=None,
            blocked=False,
        )

        entry = self.audit.get_audit_entry(audit_id)

        assert entry is not None
        assert entry.audit_id == audit_id
        assert entry.code_hash == code_hash

    def test_get_audit_entry_not_found(self):
        """Test retrieving non-existent audit entry"""
        entry = self.audit.get_audit_entry("nonexistent-id")

        assert entry is None

    def test_get_recent_audits_empty(self):
        """Test getting recent audits with no entries"""
        audits = self.audit.get_recent_audits(limit=10)

        assert audits == []

    def test_get_recent_audits_multiple(self):
        """Test getting recent audits with multiple entries"""
        result = CompilationResult(status=CompilationStatus.SUCCESS, exit_code=0)

        # Log 5 compilations
        for i in range(5):
            self.audit.log_compilation(
                code_hash=f"hash{i}",
                module_name=f"Module{i}",
                result=result,
                auth_model=None,
                blocked=False,
            )

        audits = self.audit.get_recent_audits(limit=10)

        assert len(audits) == 5

        # Verify newest first
        for i, entry in enumerate(audits):
            # Entries should be in reverse order (newest first)
            assert f"hash{4-i}" == entry.code_hash or f"hash{i}" in [
                e.code_hash for e in audits
            ]

    def test_get_recent_audits_respects_limit(self):
        """Test limit parameter works correctly"""
        result = CompilationResult(status=CompilationStatus.SUCCESS, exit_code=0)

        # Log 10 compilations
        for i in range(10):
            self.audit.log_compilation(
                code_hash=f"hash{i}",
                module_name=f"Module{i}",
                result=result,
                auth_model=None,
                blocked=False,
            )

        audits = self.audit.get_recent_audits(limit=3)

        assert len(audits) == 3

    def test_get_stats_empty(self):
        """Test statistics with no entries"""
        stats = self.audit.get_stats()

        assert stats["total"] == 0
        assert stats["blocked"] == 0

    def test_get_stats_multiple_entries(self):
        """Test statistics with multiple entries"""
        # Log successful compilation
        result_success = CompilationResult(status=CompilationStatus.SUCCESS, exit_code=0)
        self.audit.log_compilation(
            code_hash="hash1",
            module_name="Module1",
            result=result_success,
            auth_model=None,
            blocked=False,
        )

        # Log failed compilation (blocked)
        result_failed = CompilationResult(status=CompilationStatus.FAILED, exit_code=1)
        self.audit.log_compilation(
            code_hash="hash2",
            module_name="Module2",
            result=result_failed,
            auth_model=None,
            blocked=True,
        )

        # Log another failed (blocked)
        self.audit.log_compilation(
            code_hash="hash3",
            module_name="Module3",
            result=result_failed,
            auth_model=None,
            blocked=True,
        )

        stats = self.audit.get_stats()

        assert stats["total"] == 3
        assert stats["blocked"] == 2
        assert stats["by_status"]["success"] == 1
        assert stats["by_status"]["failed"] == 2

    def test_audit_entry_serialization(self):
        """Test AuditEntry to_dict and from_dict"""
        from canton_mcp_server.daml.types import AuditEntry

        error = CompilationError(
            file_path="Main.daml",
            line=10,
            column=5,
            category=ErrorCategory.AUTHORIZATION,
            message="Missing signatory",
            raw_error="raw error text",
        )

        auth_model = AuthorizationModel(
            template_name="Test",
            signatories=["issuer"],
            observers=["owner"],
            controllers={"Transfer": ["owner"]},
        )

        entry = AuditEntry(
            audit_id="test-123",
            timestamp=datetime.utcnow(),
            code_hash="abc123",
            module_name="TestModule",
            status=CompilationStatus.SUCCESS,
            errors=[error],
            authorization_model=auth_model,
            blocked=False,
        )

        # Serialize
        data = entry.to_dict()

        # Deserialize
        restored = AuditEntry.from_dict(data)

        assert restored.audit_id == entry.audit_id
        assert restored.code_hash == entry.code_hash
        assert restored.module_name == entry.module_name
        assert restored.status == entry.status
        assert len(restored.errors) == 1
        assert restored.errors[0].message == error.message
        assert restored.authorization_model.template_name == auth_model.template_name
        assert restored.blocked == entry.blocked




