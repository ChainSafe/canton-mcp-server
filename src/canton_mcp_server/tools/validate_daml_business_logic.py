"""
Validate DAML Business Logic Tool

Validates DAML code against canonical authorization patterns and business requirements.
"""

from typing import List, Optional

from pydantic import Field

from ..core import Tool, ToolContext, register_tool
from ..core.pricing import PricingType, ToolPricing
from ..core.types.models import MCPModel


class ValidateDamlParams(MCPModel):
    """Parameters for DAML validation"""

    business_intent: str = Field(
        description="Description of what the developer wants to achieve"
    )
    daml_code: str = Field(description="DAML code to validate")
    security_requirements: Optional[List[str]] = Field(
        default=None, description="Additional security requirements"
    )


class ValidateDamlResult(MCPModel):
    """Result of DAML validation"""

    valid: bool = Field(description="Whether the DAML code is valid")
    issues: List[str] = Field(description="List of validation issues found")
    suggestions: List[str] = Field(description="List of suggestions for improvement")
    business_intent: str = Field(description="The business intent that was validated")
    security_requirements: List[str] = Field(
        description="Security requirements that were checked"
    )


@register_tool
class ValidateDamlBusinessLogicTool(Tool[ValidateDamlParams, ValidateDamlResult]):
    """Tool for validating DAML business logic against authorization patterns"""

    name = "validate_daml_business_logic"
    description = "Validate DAML code against canonical authorization patterns and business requirements"
    params_model = ValidateDamlParams
    result_model = ValidateDamlResult
    pricing = ToolPricing(type=PricingType.FREE)

    async def execute(
        self, ctx: ToolContext[ValidateDamlParams, ValidateDamlResult]
    ):
        """Execute DAML validation"""
        # Extract parameters
        business_intent = ctx.params.business_intent
        daml_code = ctx.params.daml_code
        security_requirements = ctx.params.security_requirements or []

        # Basic validation logic
        issues = []
        suggestions = []

        # Check for basic DAML structure
        if "template" not in daml_code.lower():
            issues.append("No template definition found in DAML code")

        if "signatory" not in daml_code.lower():
            issues.append(
                "No signatory definition found - this may cause authorization issues"
            )
            suggestions.append(
                "Add signatory field to define who can create this contract"
            )

        if "observer" not in daml_code.lower() and "disclosure" in business_intent.lower():
            suggestions.append(
                "Consider adding observers for data disclosure requirements"
            )

        # Check security requirements
        for req in security_requirements:
            if "multi-party" in req.lower() and "signatory" not in daml_code.lower():
                issues.append(
                    f"Security requirement '{req}' not addressed - missing multi-party authorization"
                )

        # Create result
        result = ValidateDamlResult(
            valid=len(issues) == 0,
            issues=issues,
            suggestions=suggestions,
            business_intent=business_intent,
            security_requirements=security_requirements,
        )

        # Return structured result
        yield ctx.structured(result)

