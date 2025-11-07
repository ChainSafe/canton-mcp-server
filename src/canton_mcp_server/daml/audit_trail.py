"""
DAML Compilation Audit Trail

Maintains complete audit log of all DAML compilation attempts.
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from .types import (
    AuditEntry,
    AuthorizationModel,
    CompilationResult,
    CompilationStatus,
    PolicyCheckResult,
)

logger = logging.getLogger(__name__)


class AuditTrail:
    """
    Audit trail for DAML compilation safety checks.

    Logs all compilation attempts with:
    - Code hash
    - Compilation result
    - Authorization model
    - Timestamp
    - Block/allow decision
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize audit trail.

        Args:
            storage_path: Directory to store audit logs (default: ./daml_audit_logs)
        """
        if storage_path is None:
            storage_path = Path("./daml_audit_logs")

        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"Audit trail initialized: {self.storage_path}")

    def log_compilation(
        self,
        code_hash: str,
        module_name: str,
        result: CompilationResult,
        auth_model: Optional[AuthorizationModel],
        blocked: bool,
        policy_check: Optional[PolicyCheckResult] = None,
    ) -> str:
        """
        Log compilation attempt to audit trail.

        Args:
            code_hash: SHA256 hash of code
            module_name: Module name
            result: Compilation result
            auth_model: Extracted authorization model (if successful)
            blocked: Whether pattern was blocked
            policy_check: Policy check result (if policy checking was performed)

        Returns:
            audit_id: Unique ID for this audit entry
        """
        audit_id = str(uuid.uuid4())
        timestamp = datetime.utcnow()

        # Extract policy violation details if present
        policy_blocked = False
        anti_pattern_name = None
        policy_reasoning = None
        
        if policy_check and policy_check.matches_anti_pattern:
            policy_blocked = True
            anti_pattern_name = policy_check.matched_anti_pattern_name
            policy_reasoning = policy_check.match_reasoning

        entry = AuditEntry(
            audit_id=audit_id,
            timestamp=timestamp,
            code_hash=code_hash,
            module_name=module_name,
            status=result.status,
            errors=result.errors,
            authorization_model=auth_model,
            blocked=blocked,
            policy_blocked=policy_blocked,
            anti_pattern_name=anti_pattern_name,
            policy_reasoning=policy_reasoning,
        )

        # Write to JSON file
        self._write_entry(entry)

        log_msg = (
            f"Audit logged: {audit_id} (status: {result.status.value}, "
            f"blocked: {blocked}, errors: {len(result.errors)}"
        )
        if policy_blocked:
            log_msg += f", policy_blocked: {anti_pattern_name}"
        log_msg += ")"
        
        logger.info(log_msg)

        return audit_id

    def _write_entry(self, entry: AuditEntry):
        """
        Write audit entry to JSON file.

        Files are organized by date: YYYY-MM-DD.jsonl
        """
        date_str = entry.timestamp.strftime("%Y-%m-%d")
        log_file = self.storage_path / f"{date_str}.jsonl"

        # Append entry as JSON line
        with open(log_file, "a") as f:
            json.dump(entry.to_dict(), f)
            f.write("\n")

    def get_audit_entry(self, audit_id: str) -> Optional[AuditEntry]:
        """
        Retrieve audit entry by ID.

        Args:
            audit_id: Audit ID to search for

        Returns:
            AuditEntry if found, None otherwise
        """
        # Search all log files
        for log_file in sorted(self.storage_path.glob("*.jsonl"), reverse=True):
            try:
                with open(log_file) as f:
                    for line in f:
                        data = json.loads(line.strip())
                        if data.get("audit_id") == audit_id:
                            return AuditEntry.from_dict(data)
            except Exception as e:
                logger.warning(f"Error reading audit log {log_file}: {e}")
                continue

        return None

    def get_recent_audits(self, limit: int = 100) -> List[AuditEntry]:
        """
        Get recent audit entries.

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of recent AuditEntry objects (newest first)
        """
        entries = []

        # Read from most recent log files first
        for log_file in sorted(self.storage_path.glob("*.jsonl"), reverse=True):
            try:
                with open(log_file) as f:
                    # Read lines in reverse order (newest first within file)
                    lines = f.readlines()
                    for line in reversed(lines):
                        if len(entries) >= limit:
                            return entries

                        data = json.loads(line.strip())
                        entries.append(AuditEntry.from_dict(data))

            except Exception as e:
                logger.warning(f"Error reading audit log {log_file}: {e}")
                continue

        return entries

    def get_stats(self) -> dict:
        """
        Get audit trail statistics.

        Returns:
            Dictionary with stats (total, blocked, by_status, etc.)
        """
        stats = {
            "total": 0,
            "blocked": 0,
            "by_status": {status.value: 0 for status in CompilationStatus},
            "by_date": {},
        }

        for log_file in self.storage_path.glob("*.jsonl"):
            date = log_file.stem
            date_count = 0

            try:
                with open(log_file) as f:
                    for line in f:
                        data = json.loads(line.strip())
                        stats["total"] += 1
                        date_count += 1

                        if data.get("blocked"):
                            stats["blocked"] += 1

                        status = data.get("status")
                        if status:
                            stats["by_status"][status] = (
                                stats["by_status"].get(status, 0) + 1
                            )

                stats["by_date"][date] = date_count

            except Exception as e:
                logger.warning(f"Error reading audit log {log_file}: {e}")
                continue

        return stats

    def cleanup_old_logs(self, days: int = 30):
        """
        Clean up audit logs older than specified days.

        Args:
            days: Keep logs from last N days
        """
        cutoff_date = datetime.utcnow().date()
        cutoff_date = cutoff_date.replace(
            year=cutoff_date.year, month=cutoff_date.month, day=cutoff_date.day - days
        )

        deleted = 0
        for log_file in self.storage_path.glob("*.jsonl"):
            try:
                # Parse date from filename (YYYY-MM-DD.jsonl)
                date_str = log_file.stem
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()

                if file_date < cutoff_date:
                    log_file.unlink()
                    deleted += 1
                    logger.info(f"Deleted old audit log: {log_file}")

            except Exception as e:
                logger.warning(f"Error processing {log_file}: {e}")
                continue

        logger.info(f"Cleanup complete: deleted {deleted} old audit logs")




