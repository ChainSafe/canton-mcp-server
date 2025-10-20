"""
Debug Authorization Failure Tool

Debug DAML authorization errors with detailed analysis.
"""

from typing import List, Optional

from pydantic import Field

from ..core import Tool, ToolContext, register_tool
from ..core.pricing import PricingType, ToolPricing
from ..core.types.models import MCPModel


class DebugAuthParams(MCPModel):
    """Parameters for debugging authorization failures"""

    error_message: str = Field(description="The authorization error message")
    daml_code: Optional[str] = Field(
        default=None, description="The DAML code that caused the error (optional)"
    )
    context: Optional[str] = Field(
        default=None, description="Additional context about the error (optional)"
    )


class DebugAuthResult(MCPModel):
    """Result of authorization debugging"""

    error_message: str = Field(description="The error message that was analyzed")
    analysis: List[str] = Field(description="Analysis of the error")
    suggested_fixes: List[str] = Field(description="Suggested fixes for the error")
    daml_code_provided: bool = Field(description="Whether DAML code was provided")
    context: Optional[str] = Field(description="Additional context")


@register_tool
class DebugAuthorizationFailureTool(Tool[DebugAuthParams, DebugAuthResult]):
    """Tool for debugging DAML authorization failures"""

    name = "debug_authorization_failure"
    description = "Debug DAML authorization errors with detailed analysis and suggested fixes"
    params_model = DebugAuthParams
    result_model = DebugAuthResult
    pricing = ToolPricing(type=PricingType.FREE)

    async def execute(self, ctx: ToolContext[DebugAuthParams, DebugAuthResult]):
        """Execute authorization debugging"""
        # Extract parameters
        error_message = ctx.params.error_message
        daml_code = ctx.params.daml_code
        context = ctx.params.context

        fixes = []
        analysis = []

        # Common authorization error patterns
        if "missing authorization" in error_message.lower():
            analysis.append(
                "Authorization missing - likely signatory or observer issue"
            )
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

        # Create result
        result = DebugAuthResult(
            error_message=error_message,
            analysis=analysis,
            suggested_fixes=fixes,
            daml_code_provided=daml_code is not None,
            context=context,
        )

        # Return structured result
        yield ctx.structured(result)

