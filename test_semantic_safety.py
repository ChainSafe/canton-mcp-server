#!/usr/bin/env python3
"""
Test script for the refactored SafetyChecker with semantic search and LLM reasoning.
"""

import asyncio
import os

# Set environment variables
os.environ["CANONICAL_DOCS_PATH"] = "/Users/martinmaurer/Projects/Martin/canonical-daml-docs"
os.environ["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "")

from canton_mcp_server.daml.safety_checker import SafetyChecker


async def test_valid_code():
    """Test with valid DAML code"""
    print("\n" + "=" * 60)
    print("Test 1: Valid DAML Code")
    print("=" * 60)
    
    valid_code = """
module Test where

template SimpleAsset
  with
    issuer: Party
    owner: Party
    amount: Int
  where
    signatory issuer, owner
    
    choice Transfer: ContractId SimpleAsset
      with
        newOwner: Party
      controller owner
      do
        create this with owner = newOwner
"""
    
    checker = SafetyChecker()
    result = await checker.check_pattern_safety(valid_code, "Test")
    
    print(f"\n✅ Result: {'PASSED' if result.passed else 'FAILED'}")
    print(f"Compilation: {result.compilation_result.status.value}")
    if result.authorization_model:
        print(f"Authorization Model: {len(result.authorization_model.signatories)} signatories")
    if result.blocked_reason:
        print(f"Blocked Reason: {result.blocked_reason}")
    if result.llm_insights:
        print(f"LLM Insights: {result.llm_insights[:200]}...")
    if result.similar_files:
        print(f"Similar Files Found: {len(result.similar_files)}")
        for i, file in enumerate(result.similar_files[:3], 1):
            print(f"  {i}. {file.get('file_path', 'unknown')} (score: {file.get('similarity_score', 0):.3f})")


async def test_suspicious_code():
    """Test with potentially suspicious DAML code"""
    print("\n" + "=" * 60)
    print("Test 2: Suspicious DAML Code (Missing Signatory)")
    print("=" * 60)
    
    suspicious_code = """
module Test where

template SuspiciousAsset
  with
    owner: Party
    amount: Int
  where
    signatory owner
    
    choice SuspiciousTransfer: ContractId SuspiciousAsset
      with
        newOwner: Party
      controller newOwner  -- This is suspicious: controller is not a signatory
      do
        create this with owner = newOwner
"""
    
    checker = SafetyChecker()
    result = await checker.check_pattern_safety(suspicious_code, "Test")
    
    print(f"\n✅ Result: {'PASSED' if result.passed else 'BLOCKED'}")
    print(f"Compilation: {result.compilation_result.status.value}")
    if result.blocked_reason:
        print(f"Blocked Reason: {result.blocked_reason}")
    if result.llm_insights:
        print(f"LLM Insights: {result.llm_insights[:300]}...")
    if result.similar_files:
        print(f"Similar Files Found: {len(result.similar_files)}")
        for i, file in enumerate(result.similar_files[:3], 1):
            print(f"  {i}. {file.get('file_path', 'unknown')} (score: {file.get('similarity_score', 0):.3f})")


async def test_invalid_code():
    """Test with invalid DAML code (compilation error)"""
    print("\n" + "=" * 60)
    print("Test 3: Invalid DAML Code (Compilation Error)")
    print("=" * 60)
    
    invalid_code = """
module Test where

template InvalidTemplate
  with
    owner: Party
  where
    signatory owner
    
    choice InvalidChoice: ContractId InvalidTemplate
      with
        newOwner: Party
      controller owner
      do
        -- Missing return statement
"""
    
    checker = SafetyChecker()
    result = await checker.check_pattern_safety(invalid_code, "Test")
    
    print(f"\n✅ Result: {'PASSED' if result.passed else 'BLOCKED'}")
    print(f"Compilation: {result.compilation_result.status.value}")
    if result.blocked_reason:
        print(f"Blocked Reason: {result.blocked_reason}")
    if result.compilation_result.errors:
        print(f"Compilation Errors: {len(result.compilation_result.errors)}")
        for error in result.compilation_result.errors[:3]:
            print(f"  - {error.message[:100]}")


async def main():
    """Run all tests"""
    print("\n🧪 Testing Refactored SafetyChecker with Semantic Search + LLM")
    print("=" * 60)
    
    # Check if ANTHROPIC_API_KEY is set
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("\n⚠️  Warning: ANTHROPIC_API_KEY not set. LLM reasoning will be disabled.")
        print("Set ANTHROPIC_API_KEY to enable full LLM safety analysis.\n")
    
    try:
        await test_valid_code()
        await test_suspicious_code()
        await test_invalid_code()
        
        print("\n" + "=" * 60)
        print("✅ All tests completed!")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

