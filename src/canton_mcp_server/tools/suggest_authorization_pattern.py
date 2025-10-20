"""
Suggest Authorization Pattern Tool

Suggest DAML authorization patterns based on workflow requirements.
"""

from typing import Any, Dict, List, Optional

from pydantic import Field

from ..core import Tool, ToolContext, register_tool
from ..core.pricing import PricingType, ToolPricing
from ..core.types.models import MCPModel


class SuggestPatternParams(MCPModel):
    """Parameters for suggesting authorization patterns"""

    workflow_description: str = Field(
        description="Description of the workflow to implement"
    )
    security_level: str = Field(
        default="basic",
        description="Required security level (basic, enhanced, enterprise)",
    )
    constraints: Optional[List[str]] = Field(
        default=None, description="Business or technical constraints"
    )


class SuggestPatternResult(MCPModel):
    """Result of pattern suggestion"""

    workflow_description: str = Field(description="The workflow that was analyzed")
    security_level: str = Field(description="The security level requested")
    constraints: List[str] = Field(description="Constraints that were considered")
    suggested_patterns: List[Dict[str, Any]] = Field(
        description="Suggested authorization patterns"
    )
    implementation_notes: List[str] = Field(
        description="Implementation notes and recommendations"
    )


@register_tool
class SuggestAuthorizationPatternTool(Tool[SuggestPatternParams, SuggestPatternResult]):
    """Tool for suggesting DAML authorization patterns"""

    name = "suggest_authorization_pattern"
    description = "Suggest DAML authorization patterns based on workflow requirements and security levels"
    params_model = SuggestPatternParams
    result_model = SuggestPatternResult
    pricing = ToolPricing(type=PricingType.FREE)

    async def execute(
        self, ctx: ToolContext[SuggestPatternParams, SuggestPatternResult]
    ):
        """Execute pattern suggestion"""
        # Extract parameters
        workflow_description = ctx.params.workflow_description
        security_level = ctx.params.security_level
        constraints = ctx.params.constraints or []

        patterns = []
        implementation_notes = []

        # Analyze workflow for common patterns
        workflow_lower = workflow_description.lower()

        if "transfer" in workflow_lower or "payment" in workflow_lower:
            patterns.append(
                {
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
                    "authorization_logic": "Sender signs, receiver observes",
                }
            )

        if "approval" in workflow_lower or "workflow" in workflow_lower:
            patterns.append(
                {
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
                    "authorization_logic": "Requester creates, approvers sign for approval",
                }
            )

        # Security level considerations
        if security_level == "enhanced":
            implementation_notes.append(
                "Consider adding choice controllers for fine-grained access"
            )
            implementation_notes.append(
                "Implement audit trails with observer patterns"
            )

        if security_level == "enterprise":
            implementation_notes.append("Add role-based access control")
            implementation_notes.append("Implement compliance reporting mechanisms")
            implementation_notes.append(
                "Consider privacy features with observer restrictions"
            )

        # Create result
        result = SuggestPatternResult(
            workflow_description=workflow_description,
            security_level=security_level,
            constraints=constraints,
            suggested_patterns=patterns,
            implementation_notes=implementation_notes,
        )

        # Return structured result
        yield ctx.structured(result)

