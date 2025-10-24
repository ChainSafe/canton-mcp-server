#!/usr/bin/env python3
"""
Test the two-gate validation system
"""

import yaml
import subprocess
from pathlib import Path
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_git_verification(resource):
    """Test Gate 1: Git verification"""
    canonical_hash = resource["canonical_hash"]
    source_commit = resource["source_commit"]
    source_file = resource["source_file"]
    
    # Determine repo path
    repo_path = Path("../canonical-daml-docs/daml")  # Our test file is from DAML repo
    
    # Verify Git blob hash
    try:
        # Get tree hash
        result = subprocess.run(['git', 'show', '--format=%T', '-s', source_commit], 
                               cwd=repo_path, capture_output=True, text=True, check=True)
        tree_hash = result.stdout.strip()
        
        # Get blob hash
        result = subprocess.run(['git', 'ls-tree', tree_hash, source_file], 
                               cwd=repo_path, capture_output=True, text=True, check=True)
        actual_hash = result.stdout.strip().split()[2]
        
        if actual_hash == canonical_hash:
            logger.info("✅ GATE 1 PASSED - Git verification successful")
            return True
        else:
            logger.error(f"❌ GATE 1 FAILED - Hash mismatch: expected {canonical_hash}, got {actual_hash}")
            return False
            
    except Exception as e:
        logger.error(f"❌ GATE 1 FAILED - Git verification error: {e}")
        return False

def test_schema_validation(resource):
    """Test Gate 2: Schema validation (simplified)"""
    required_fields = [
        "name", "version", "description", "tags", "author", "created_at",
        "pattern_type", "daml_template", "authorization_requirements",
        "when_to_use", "when_not_to_use", "security_considerations", "test_cases"
    ]
    
    missing_fields = [field for field in required_fields if field not in resource]
    
    if missing_fields:
        logger.error(f"❌ GATE 2 FAILED - Missing required fields: {missing_fields}")
        return False
    
    # Check field types
    if not isinstance(resource["tags"], list):
        logger.error("❌ GATE 2 FAILED - 'tags' must be a list")
        return False
    
    if not isinstance(resource["authorization_requirements"], list):
        logger.error("❌ GATE 2 FAILED - 'authorization_requirements' must be a list")
        return False
    
    logger.info("✅ GATE 2 PASSED - Schema validation successful")
    return True

def main():
    """Test the two-gate validation system"""
    print("Testing Two-Gate Validation System")
    print("=" * 40)
    
    # Load our sample resource
    resource_file = Path("resources-extracted/patterns/well-authorized-create-v1.0.yaml")
    
    if not resource_file.exists():
        print(f"❌ Resource file not found: {resource_file}")
        return
    
    with open(resource_file, 'r') as f:
        resource = yaml.safe_load(f)
    
    print(f"Testing resource: {resource['name']}")
    print()
    
    # Test Gate 1: Git verification
    print("GATE 1: Git Verification (Authenticity)")
    gate1_passed = test_git_verification(resource)
    print()
    
    # Test Gate 2: Schema validation
    print("GATE 2: Schema Validation (Documentation Quality)")
    gate2_passed = test_schema_validation(resource)
    print()
    
    # Final result
    if gate1_passed and gate2_passed:
        print("🎉 BOTH GATES PASSED - Resource is valid and authentic!")
    else:
        print("❌ VALIDATION FAILED - Resource rejected")

if __name__ == "__main__":
    main()
