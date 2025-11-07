"""
Tests for Canonical Policy Enforcement

Validates that Gate 1 blocks all canonical anti-patterns.
This is a SECURITY requirement - every anti-pattern must be blocked.
"""

import shutil
import tempfile
from pathlib import Path
from typing import List

import pytest

from canton_mcp_server.core.resources.base import ResourceCategory
from canton_mcp_server.core.resources.loader import ResourceLoader
from canton_mcp_server.daml.audit_trail import AuditTrail
from canton_mcp_server.daml.safety_checker import SafetyChecker


# Check if daml command is available
DAML_AVAILABLE = shutil.which("daml") is not None
requires_daml = pytest.mark.skipif(
    not DAML_AVAILABLE, reason="DAML SDK not installed"
)


def get_all_anti_pattern_names() -> List[str]:
    """Get names of all canonical anti-patterns for parametrized tests"""
    loader = ResourceLoader(resources_dir="resources")
    loader.load_all_resources()
    
    anti_patterns = loader.registry.list_resources(ResourceCategory.ANTI_PATTERN)
    return [ap.name for ap in anti_patterns]


def get_all_safe_pattern_names() -> List[str]:
    """Get names of all canonical safe patterns for validation"""
    loader = ResourceLoader(resources_dir="resources")
    loader.load_all_resources()
    
    patterns = loader.registry.list_resources(ResourceCategory.PATTERN)
    return [p.name for p in patterns]


@pytest.fixture
def safety_checker():
    """Create SafetyChecker with policy enforcement enabled"""
    if not DAML_AVAILABLE:
        pytest.skip("Requires DAML SDK")
    
    temp_dir = tempfile.mkdtemp(prefix="policy_test_")
    storage_path = Path(temp_dir)
    
    # Initialize resource loader with canonical resources
    resource_loader = ResourceLoader(resources_dir="resources")
    resource_loader.load_all_resources()
    
    # Create safety checker with resource loader
    audit_trail = AuditTrail(storage_path=storage_path)
    checker = SafetyChecker(
        audit_trail=audit_trail,
        resource_loader=resource_loader,
    )
    
    yield checker
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def resource_loader():
    """Create ResourceLoader with all canonical resources loaded"""
    loader = ResourceLoader(resources_dir="resources")
    loader.load_all_resources()
    return loader


class TestPolicyEnforcement:
    """Test canonical policy enforcement in Gate 1"""
    
    @requires_daml
    @pytest.mark.security
    @pytest.mark.parametrize("anti_pattern_name", get_all_anti_pattern_names())
    @pytest.mark.asyncio
    async def test_gate1_blocks_canonical_anti_pattern(
        self, safety_checker, resource_loader, anti_pattern_name
    ):
        """
        SECURITY: Gate 1 must block ALL canonical anti-patterns.
        
        This validates the policy enforcement layer. Even if code compiles,
        it should be blocked if it matches a known anti-pattern.
        """
        # Load the anti-pattern
        anti_patterns = resource_loader.registry.list_resources(
            ResourceCategory.ANTI_PATTERN
        )
        anti_pattern = next(ap for ap in anti_patterns if ap.name == anti_pattern_name)
        
        # Get the problematic code from the anti-pattern
        problematic_code = anti_pattern.content.get("problematic_code")
        assert problematic_code, f"Anti-pattern {anti_pattern_name} has no problematic_code"
        
        # Run safety check
        result = await safety_checker.check_pattern_safety(
            problematic_code,
            module_name="TestAntiPattern",
        )
        
        # SECURITY CRITICAL: Must be blocked
        assert result.passed is False, (
            f"SECURITY VIOLATION: Anti-pattern '{anti_pattern_name}' was NOT blocked! "
            f"This is a critical security issue."
        )
        
        # Verify policy check detected the anti-pattern
        assert result.policy_check is not None, (
            f"Anti-pattern '{anti_pattern_name}' was blocked but policy_check is None"
        )
        assert result.policy_check.matches_anti_pattern is True, (
            f"Anti-pattern '{anti_pattern_name}' was not detected by policy checker"
        )
        
        # Verify the correct anti-pattern was matched
        # (May match by name or by related patterns)
        assert result.policy_check.matched_anti_pattern_name is not None
        
        # Verify audit trail captured the policy block
        assert result.audit_id
        audit_entry = safety_checker.audit_trail.get_audit_entry(result.audit_id)
        assert audit_entry is not None
        assert audit_entry.policy_blocked is True
        assert audit_entry.anti_pattern_name is not None
    
    @requires_daml
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_gate1_allows_safe_patterns(self, safety_checker, resource_loader):
        """
        Validate that safe patterns are NOT blocked by policy enforcement.
        
        This ensures we don't have false positives.
        """
        # Load safe patterns
        safe_patterns = resource_loader.registry.list_resources(ResourceCategory.PATTERN)
        
        if not safe_patterns:
            pytest.skip("No safe patterns found to test")
        
        # Test each safe pattern
        for pattern in safe_patterns:
            daml_code = pattern.content.get("daml_template")
            if not daml_code:
                continue  # Skip patterns without code examples
            
            result = await safety_checker.check_pattern_safety(
                daml_code,
                module_name=f"Safe{pattern.name}",
            )
            
            # Safe patterns should pass (unless they have compilation errors)
            # If it's blocked, it should NOT be due to policy
            if not result.passed:
                # If blocked, it should be compilation error, not policy
                assert result.policy_check is None or not result.policy_check.matches_anti_pattern, (
                    f"Safe pattern '{pattern.name}' was incorrectly blocked by policy. "
                    f"This is a false positive."
                )
    
    @requires_daml
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_policy_check_suggests_alternatives(
        self, safety_checker, resource_loader
    ):
        """
        Verify that when code is blocked, safe alternatives are suggested.
        """
        # Get an anti-pattern
        anti_patterns = resource_loader.registry.list_resources(
            ResourceCategory.ANTI_PATTERN
        )
        
        if not anti_patterns:
            pytest.skip("No anti-patterns found")
        
        anti_pattern = anti_patterns[0]
        problematic_code = anti_pattern.content.get("problematic_code")
        
        if not problematic_code:
            pytest.skip(f"Anti-pattern {anti_pattern.name} has no problematic_code")
        
        # Run safety check
        result = await safety_checker.check_pattern_safety(
            problematic_code,
            module_name="TestSuggestions",
        )
        
        # Should be blocked
        assert result.passed is False
        assert result.policy_check is not None
        assert result.policy_check.matches_anti_pattern is True
        
        # Should have suggestions (may be empty if no relevant patterns)
        assert hasattr(result.policy_check, "suggested_alternatives")
        assert isinstance(result.policy_check.suggested_alternatives, list)
    
    @requires_daml
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_audit_trail_records_policy_violations(
        self, safety_checker, resource_loader
    ):
        """
        Verify that audit trail properly records policy-based blocks.
        """
        # Get an anti-pattern
        anti_patterns = resource_loader.registry.list_resources(
            ResourceCategory.ANTI_PATTERN
        )
        
        if not anti_patterns:
            pytest.skip("No anti-patterns found")
        
        anti_pattern = anti_patterns[0]
        problematic_code = anti_pattern.content.get("problematic_code")
        
        if not problematic_code:
            pytest.skip(f"Anti-pattern {anti_pattern.name} has no problematic_code")
        
        # Run safety check
        result = await safety_checker.check_pattern_safety(
            problematic_code,
            module_name="TestAudit",
        )
        
        # Get audit entry
        audit_entry = safety_checker.audit_trail.get_audit_entry(result.audit_id)
        
        assert audit_entry is not None
        assert audit_entry.blocked is True
        assert audit_entry.policy_blocked is True
        assert audit_entry.anti_pattern_name is not None
        assert audit_entry.policy_reasoning is not None
        
        # Verify audit entry serializes correctly
        audit_dict = audit_entry.to_dict()
        assert audit_dict["policy_blocked"] is True
        assert audit_dict["anti_pattern_name"] is not None
    
    @requires_daml
    @pytest.mark.asyncio
    async def test_policy_enforcement_with_valid_code(self, safety_checker):
        """
        Test that valid code passes policy enforcement.
        """
        valid_code = """
module Main where

data Asset = Asset with
    owner: Party
  deriving (Eq, Show)

template SimpleIOU
  with
    issuer: Party
    owner: Party
    amount: Decimal
  where
    signatory issuer, owner
    
    choice Transfer : ContractId SimpleIOU
      with
        newOwner: Party
      controller owner
      do
        create this with owner = newOwner
"""
        
        result = await safety_checker.check_pattern_safety(
            valid_code,
            module_name="ValidCode",
        )
        
        # Should pass all checks including policy
        assert result.passed is True
        # Policy check may or may not be present, but if present should not match
        if result.policy_check:
            assert result.policy_check.matches_anti_pattern is False


class TestPolicyCheckerIntegration:
    """Test policy checker integration with resource loader"""
    
    def test_resource_loader_finds_anti_patterns(self, resource_loader):
        """Verify resource loader can find anti-patterns"""
        anti_patterns = resource_loader.registry.list_resources(
            ResourceCategory.ANTI_PATTERN
        )
        
        assert len(anti_patterns) > 0, "No anti-patterns found in resources/anti-patterns/"
        
        for ap in anti_patterns:
            assert ap.name
            assert ap.metadata.version
            assert ap.content.get("problematic_code") or ap.content.get("detection_pattern")
    
    def test_resource_loader_finds_safe_patterns(self, resource_loader):
        """Verify resource loader can find safe patterns"""
        patterns = resource_loader.registry.list_resources(ResourceCategory.PATTERN)
        
        assert len(patterns) > 0, "No safe patterns found in resources/patterns/"
        
        for pattern in patterns:
            assert pattern.name
            assert pattern.metadata.version

