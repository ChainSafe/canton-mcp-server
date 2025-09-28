"""
Canton MCP Server - Main server implementation.

This server provides tools and resources for Canton blockchain development,
including DAML validation, authorization patterns, and Canton network management.
"""

from fastmcp import FastMCP
from typing import Any, Dict, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
app = FastMCP("Canton MCP Server")

@app.tool()
def validate_daml_business_logic(
    business_intent: str,
    daml_code: str,
    security_requirements: List[str] = None
) -> Dict[str, Any]:
    """
    Validate DAML code against canonical authorization patterns and business requirements.
    
    Args:
        business_intent: Description of what the developer wants to achieve
        daml_code: DAML code to validate
        security_requirements: Additional security requirements
    
    Returns:
        Validation results with suggestions and issues
    """
    if security_requirements is None:
        security_requirements = []
    
    # Basic validation logic (to be expanded)
    issues = []
    suggestions = []
    
    # Check for basic DAML structure
    if "template" not in daml_code.lower():
        issues.append("No template definition found in DAML code")
    
    if "signatory" not in daml_code.lower():
        issues.append("No signatory definition found - this may cause authorization issues")
        suggestions.append("Add signatory field to define who can create this contract")
    
    if "observer" not in daml_code.lower() and "disclosure" in business_intent.lower():
        suggestions.append("Consider adding observers for data disclosure requirements")
    
    # Check security requirements
    for req in security_requirements:
        if "multi-party" in req.lower() and "signatory" not in daml_code.lower():
            issues.append(f"Security requirement '{req}' not addressed - missing multi-party authorization")
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "suggestions": suggestions,
        "business_intent": business_intent,
        "security_requirements": security_requirements
    }

@app.tool()
def debug_authorization_failure(
    error_message: str,
    daml_code: str = None,
    context: str = None
) -> Dict[str, Any]:
    """
    Debug DAML authorization errors with detailed analysis.
    
    Args:
        error_message: The authorization error message
        daml_code: The DAML code that caused the error (optional)
        context: Additional context about the error (optional)
    
    Returns:
        Debug analysis with potential fixes
    """
    fixes = []
    analysis = []
    
    # Common authorization error patterns
    if "missing authorization" in error_message.lower():
        analysis.append("Authorization missing - likely signatory or observer issue")
        fixes.append("Check that all required signatories are present")
        fixes.append("Verify observer permissions for data access")
    
    if "signatory" in error_message.lower():
        analysis.append("Signatory-related authorization failure")
        fixes.append("Ensure all signatories have signed the transaction")
        fixes.append("Check signatory definitions in template")
    
    if "observer" in error_message.lower():
        analysis.append("Observer-related authorization failure")
        fixes.append("Verify observer permissions")
        fixes.append("Check if observer disclosure is properly configured")
    
    return {
        "error_message": error_message,
        "analysis": analysis,
        "suggested_fixes": fixes,
        "daml_code_provided": daml_code is not None,
        "context": context
    }

@app.tool()
def suggest_authorization_pattern(
    workflow_description: str,
    security_level: str = "basic",
    constraints: List[str] = None
) -> Dict[str, Any]:
    """
    Suggest DAML authorization patterns based on workflow requirements.
    
    Args:
        workflow_description: Description of the workflow to implement
        security_level: Required security level (basic, enhanced, enterprise)
        constraints: Business or technical constraints
    
    Returns:
        Suggested authorization patterns and implementation guidance
    """
    if constraints is None:
        constraints = []
    
    patterns = []
    implementation_notes = []
    
    # Analyze workflow for common patterns
    workflow_lower = workflow_description.lower()
    
    if "transfer" in workflow_lower or "payment" in workflow_lower:
        patterns.append({
            "name": "Asset Transfer Pattern",
            "description": "Multi-party authorization for asset transfers",
            "template_structure": """
template AssetTransfer
  with
    sender: Party
    receiver: Party
    asset: Asset
    amount: Decimal
  where
    signatory sender
    observer receiver
    """,
            "authorization_logic": "Sender signs, receiver observes"
        })
    
    if "approval" in workflow_lower or "workflow" in workflow_lower:
        patterns.append({
            "name": "Multi-Step Approval Pattern",
            "description": "Sequential approval workflow with multiple parties",
            "template_structure": """
template ApprovalRequest
  with
    requester: Party
    approvers: [Party]
    request: RequestData
  where
    signatory requester
    observer approvers
    """,
            "authorization_logic": "Requester creates, approvers sign for approval"
        })
    
    # Security level considerations
    if security_level == "enhanced":
        implementation_notes.append("Consider adding choice controllers for fine-grained access")
        implementation_notes.append("Implement audit trails with observer patterns")
    
    if security_level == "enterprise":
        implementation_notes.append("Add role-based access control")
        implementation_notes.append("Implement compliance reporting mechanisms")
        implementation_notes.append("Consider privacy features with observer restrictions")
    
    return {
        "workflow_description": workflow_description,
        "security_level": security_level,
        "constraints": constraints,
        "suggested_patterns": patterns,
        "implementation_notes": implementation_notes
    }

@app.tool()
def test_tool(message: str) -> str:
    """
    A simple test tool to verify server functionality.
    
    Args:
        message: Test message to echo back
        
    Returns:
        Echo of the test message
    """
    return f"Canton MCP Server received: {message}"

if __name__ == "__main__":
    # For development/testing
    logger.info("Canton MCP Server starting...")
    app.run()
