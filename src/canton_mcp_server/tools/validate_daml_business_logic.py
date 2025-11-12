"""
Validate DAML Business Logic Tool

Validates DAML code against canonical authorization patterns and business requirements.
Uses Gate 1 (SafetyChecker) with canonical anti-pattern enforcement.
"""

import logging
from typing import List, Optional

from pydantic import Field

from ..core import Tool, ToolContext, register_tool
from ..core.pricing import PricingType, ToolPricing
from ..core.types.models import MCPModel
from ..daml.safety_checker import SafetyChecker

logger = logging.getLogger(__name__)


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
    # Gate 1 policy enforcement results
    blocked_by_policy: bool = Field(default=False, description="Whether code was blocked by canonical anti-pattern policy")
    anti_pattern_matched: Optional[str] = Field(default=None, description="Name of matched anti-pattern if blocked")
    policy_reasoning: Optional[str] = Field(default=None, description="Reasoning for policy block")
    safe_alternatives: List[str] = Field(default=[], description="Suggested safe alternative patterns")
    
    # Delegation support
    should_delegate: bool = Field(default=False, description="Whether tool should delegate to LLM due to low confidence")
    delegation_reason: Optional[str] = Field(default=None, description="Why delegation is recommended")
    confidence: float = Field(default=1.0, description="Overall confidence in validation (0.0-1.0)")
    
    # LLM insights (when available)
    llm_insights: Optional[str] = Field(default=None, description="Additional context and insights from LLM analysis")


@register_tool
class ValidateDamlBusinessLogicTool(Tool[ValidateDamlParams, ValidateDamlResult]):
    """Tool for validating DAML business logic against authorization patterns"""

    name = "validate_daml_business_logic"
    description = (
        "⚠️ REQUIRED: Validate DAML code through Gate 1 BEFORE writing files. "
        "Gate 1 prevents unsafe authorization patterns by checking: (1) DAML compilation, "
        "(2) canonical anti-pattern matching, (3) authorization model validity. "
        "NEVER write DAML code without validating first. If validation fails, suggest safe alternatives."
    )
    params_model = ValidateDamlParams
    result_model = ValidateDamlResult
    pricing = ToolPricing(type=PricingType.FIXED, base_price=0.005)
    
    def __init__(self):
        """Initialize with SafetyChecker"""
        super().__init__()
        self.safety_checker = SafetyChecker()

    async def execute(
        self, ctx: ToolContext[ValidateDamlParams, ValidateDamlResult]
    ):
        """Execute DAML validation with Gate 1 policy enforcement"""
        # Extract parameters
        business_intent = ctx.params.business_intent
        daml_code = ctx.params.daml_code
        security_requirements = ctx.params.security_requirements or []
        
        logger.info(f"Validating DAML code for: {business_intent}")

        # Gate 1: Safety Check with Canonical Anti-Pattern Enforcement
        try:
            # Extract module name from code
            extracted_module = self._extract_module_name(daml_code)
            
            # If code doesn't have module declaration, prepend it with default name
            if not extracted_module:
                module_name = "ValidationTest"
                daml_code = f"module {module_name} where\n\n{daml_code}"
            else:
                # Use the extracted module name
                module_name = extracted_module
            
            safety_result = await self.safety_checker.check_pattern_safety(daml_code, module_name=module_name)
        except Exception as e:
            logger.error(f"Safety check failed: {e}")
            # Fallback to basic validation if safety checker fails
            safety_result = None
        
        issues = []
        suggestions = []
        blocked_by_policy = False
        anti_pattern_matched = None
        policy_reasoning = None
        safe_alternatives = []
        should_delegate = False
        delegation_reason = None
        confidence = 1.0
        llm_insights = None
        
        # Check Gate 1 results
        if safety_result:
            # Check if delegation is needed (low confidence)
            if safety_result.should_delegate:
                logger.warning(f"⚠️  Delegation required: {safety_result.delegation_reason}")
                should_delegate = True
                delegation_reason = safety_result.delegation_reason
                confidence = safety_result.confidence
                
                issues.append(f"⚠️  ANALYSIS UNCERTAIN (confidence: {confidence:.2f})")
                issues.append(f"Reason: {delegation_reason}")
                suggestions.append(
                    "This code uses complex patterns that require human review or LLM analysis. "
                    "Consider simplifying the authorization model or using the LLM-enhanced analysis."
                )
            elif not safety_result.passed:
                logger.warning(f"Gate 1 blocked: {safety_result.blocked_reason}")
                confidence = safety_result.confidence
                
                # Check if it was blocked by policy (anti-pattern match)
                if safety_result.policy_check and safety_result.policy_check.matches_anti_pattern:
                    blocked_by_policy = True
                    anti_pattern_matched = safety_result.policy_check.matched_anti_pattern_name
                    policy_reasoning = safety_result.policy_check.match_reasoning
                    safe_alternatives = safety_result.policy_check.suggested_alternatives or []
                    
                    issues.append(f"❌ BLOCKED BY POLICY: Matches anti-pattern '{anti_pattern_matched}'")
                    issues.append(f"Reason: {policy_reasoning}")
                    
                    if safe_alternatives:
                        suggestions.append(f"Consider using these safe patterns instead: {', '.join(safe_alternatives)}")
                else:
                    # Blocked for other reasons (compilation failure, etc.)
                    issues.append(f"Gate 1 Safety Check Failed: {safety_result.blocked_reason}")
                    
                    if safety_result.compilation_result and not safety_result.compilation_result.succeeded:
                        error_msgs = [str(err) for err in safety_result.compilation_result.errors]
                        issues.append(f"Compilation errors: {', '.join(error_msgs)}")
            else:
                # Passed - set confidence and LLM insights
                confidence = safety_result.confidence
                llm_insights = safety_result.llm_insights
        
        # Additional basic validation (if not blocked by policy)
        if not blocked_by_policy:
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

        # Create result
        result = ValidateDamlResult(
            valid=(len(issues) == 0 and not blocked_by_policy and not should_delegate),
            issues=issues,
            suggestions=suggestions,
            business_intent=business_intent,
            security_requirements=security_requirements,
            blocked_by_policy=blocked_by_policy,
            anti_pattern_matched=anti_pattern_matched,
            policy_reasoning=policy_reasoning,
            safe_alternatives=safe_alternatives,
            should_delegate=should_delegate,
            delegation_reason=delegation_reason,
            confidence=confidence,
            llm_insights=llm_insights,
        )

        # Return structured result
        yield ctx.structured(result)
    
    def _extract_module_name(self, daml_code: str) -> Optional[str]:
        """Extract module name from DAML code."""
        import re
        # Use search() not match() to find module anywhere in the code
        match = re.search(r'^\s*module\s+(\w+)\s+where', daml_code, re.MULTILINE)
        return match.group(1) if match else None

