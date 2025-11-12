"""
DAML Reason Tool - Comprehensive DAML Code Analysis and Advisory

This is the primary tool for DAML developers. It takes DAML code and business intent,
then either validates, suggests patterns, recommends edits, or delegates back.

Workflow:
1. Validate code through Gate 1 (compilation + authorization + anti-patterns)
2. If validation fails, recommend canonical patterns that match the intent
3. If validation succeeds with low confidence, provide insights and delegate if needed
4. If validation succeeds with high confidence, return approval with insights

This tool integrates:
- Safety checking (validate_daml_business_logic)
- Pattern recommendation (recommend_canonical_resources)
- LLM insights and explanations
- Confidence-based delegation
"""

import logging
import os
import re
from typing import List, Optional
from pathlib import Path

from pydantic import Field

from ..core import Tool, ToolContext, register_tool
from ..core.pricing import PricingType, ToolPricing
from ..core.types.models import MCPModel
from ..daml.safety_checker import SafetyChecker
from ..core.direct_file_loader import DirectFileResourceLoader
from ..core.structured_ingestion import StructuredIngestionEngine
from ..core.resource_recommender import CanonicalResourceRecommender, RecommendationRequest
from ..core.llm_enrichment import LLMEnrichmentEngine
from ..env import get_env_bool

logger = logging.getLogger(__name__)


class DamlReasonParams(MCPModel):
    """Parameters for DAML Reason tool"""

    business_intent: str = Field(
        description="What the developer wants to achieve with this DAML code"
    )
    daml_code: Optional[str] = Field(
        default=None,
        description="DAML code to analyze (optional - if not provided, only pattern recommendations returned)"
    )
    security_requirements: Optional[List[str]] = Field(
        default=None,
        description="Specific security requirements to check"
    )


class DamlReasonResult(MCPModel):
    """Result from DAML Reason analysis"""

    action: str = Field(
        description="Action type: 'approved', 'suggest_patterns', 'suggest_edits', 'delegate'"
    )
    
    # Validation results (when action='approved' or 'suggest_edits')
    valid: bool = Field(default=False, description="Whether the code is valid")
    confidence: float = Field(default=0.0, description="Confidence in analysis (0.0-1.0)")
    issues: List[str] = Field(default=[], description="Issues found in the code")
    suggestions: List[str] = Field(default=[], description="Suggestions for improvement")
    llm_insights: Optional[str] = Field(default=None, description="LLM insights about the code")
    
    # Pattern recommendations (when action='suggest_patterns' or 'suggest_edits')
    recommended_patterns: List[dict] = Field(default=[], description="Recommended canonical patterns")
    
    # Delegation (when action='delegate')
    delegation_reason: Optional[str] = Field(default=None, description="Why delegation is needed")
    
    # Common fields
    business_intent: str = Field(description="The business intent analyzed")
    reasoning: str = Field(description="Explanation of the action taken")


@register_tool
class DamlReasonTool(Tool[DamlReasonParams, DamlReasonResult]):
    """
    DAML Reason - Comprehensive DAML Code Analysis and Advisory
    
    This tool is the primary interface for DAML developers. It analyzes DAML code
    and business intent, providing validation, pattern recommendations, or delegation.
    
    Use this tool when:
    - You have DAML code and want to validate it
    - You have a business requirement and need pattern recommendations
    - You want security analysis and best practice suggestions
    - You need help understanding complex DAML patterns
    """

    name = "daml_reason"
    description = (
        "🧠 DAML Reason - Comprehensive DAML code analyzer and advisor. "
        "Validates code, recommends patterns, provides insights, and delegates when uncertain. "
        "This is the primary tool for all DAML development assistance."
    )
    params_model = DamlReasonParams
    result_model = DamlReasonResult
    
    pricing = ToolPricing(
        type=PricingType.DYNAMIC,
        base_cost=0.0,  # Dynamic cost based on LLM usage
        description="Pay for actual LLM analysis cost (compilation + validation + pattern matching)"
    )

    def __init__(self):
        super().__init__()
        # Initialize SafetyChecker (loads anti-patterns internally via ResourceLoader)
        self.safety_checker = SafetyChecker()
        
        # Initialize pattern recommendation components (SEPARATE from SafetyChecker)
        # Uses enriched metadata from ~/.canton-mcp/enrichment-cache.json
        canonical_docs_path = Path(os.environ.get("CANONICAL_DOCS_PATH", "../../canonical-daml-docs"))
        self.loader = DirectFileResourceLoader(canonical_docs_path)
        self._structured_resources = None
        self._recommender = None

    def _ensure_structured_resources(self):
        """Ensure structured resources are loaded with enrichment."""
        if self._structured_resources is None:
            logger.info("Loading and structuring canonical resources...")
            raw_resources = self.loader.get_all_resources()
            
            # Initialize enrichment engine if enabled
            # This reads from ~/.canton-mcp/enrichment-cache.json
            enrichment_engine = None
            if get_env_bool("ENABLE_LLM_ENRICHMENT", False):
                enrichment_engine = LLMEnrichmentEngine()
                if enrichment_engine.enabled:
                    cache_status = enrichment_engine.get_cache_status()
                    logger.info(f"✅ LLM enrichment enabled: {cache_status['total_enrichments']} enrichments available")
                else:
                    logger.warning("LLM enrichment requested but not available (check ANTHROPIC_API_KEY)")
            
            ingestion_engine = StructuredIngestionEngine(enrichment_engine=enrichment_engine)
            self._structured_resources = ingestion_engine.ingest_resources(raw_resources)
            self._recommender = CanonicalResourceRecommender(self._structured_resources, enrichment_engine=enrichment_engine)
            logger.info(f"Loaded {sum(len(resources) for resources in self._structured_resources.values())} structured resources")

    def _normalize_use_case(self, use_case: str) -> str:
        """Normalize use_case to snake_case format."""
        # Convert camelCase to snake_case
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', use_case)
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower()

    async def execute(
        self, params: DamlReasonParams, ctx: ToolContext
    ):
        """
        Execute DAML Reason analysis.
        
        Flow:
        1. If no code provided → Return pattern recommendations
        2. If code provided → Validate through Gate 1
        3. If validation fails → Return issues + pattern recommendations
        4. If low confidence → Delegate
        5. If high confidence → Approve with insights
        """
        business_intent = params.business_intent
        daml_code = params.daml_code
        security_requirements = params.security_requirements or []

        # CASE 1: No code provided - just recommend patterns
        if not daml_code or daml_code.strip() == "":
            logger.info(f"No code provided, recommending patterns for: {business_intent}")
            
            self._ensure_structured_resources()
            
            # Infer use_case from business_intent (simple heuristic)
            use_case = self._infer_use_case(business_intent)
            
            request = RecommendationRequest(
                use_case=use_case,
                description=business_intent,
                security_level=None,
                complexity_level=None,
                constraints=security_requirements,
                existing_patterns=[]
            )
            
            recommendations = self._recommender.recommend_resources(request)
            
            # Format recommendations
            formatted_patterns = []
            for rec in recommendations[:5]:  # Top 5
                formatted_patterns.append({
                    "name": rec.resource.name,
                    "path": rec.resource.file_path,
                    "score": rec.relevance_score,
                    "reasoning": rec.reasoning,
                    "use_case": rec.use_case_match
                })
            
            yield ctx.text(f"📚 Based on your intent: '{business_intent}'")
            yield ctx.text(f"\nI recommend exploring these canonical patterns:\n")
            
            yield DamlReasonResult(
                action="suggest_patterns",
                valid=False,
                business_intent=business_intent,
                recommended_patterns=formatted_patterns,
                reasoning="No code provided - recommending relevant canonical patterns to start from"
            )
            return

        # CASE 2: Code provided - validate it
        logger.info(f"Validating DAML code for: {business_intent}")
        
        # Run Gate 1 safety check
        module_name = self._extract_module_name(daml_code) or "Main"
        safety_result = await self.safety_checker.check_pattern_safety(
            daml_code, 
            module_name=module_name
        )
        
        # CASE 2a: Validation passed with high confidence
        if safety_result.passed and not safety_result.should_delegate:
            logger.info(f"✅ Code validation passed (confidence: {safety_result.confidence:.2f})")
            
            yield DamlReasonResult(
                action="approved",
                valid=True,
                confidence=safety_result.confidence,
                issues=[],
                suggestions=[],
                llm_insights=safety_result.llm_insights,
                business_intent=business_intent,
                recommended_patterns=[],
                reasoning=f"Code validated successfully with {safety_result.confidence:.0%} confidence. "
                         f"Authorization model extracted and verified. Ready to use."
            )
            return
        
        # CASE 2b: Low confidence - delegate
        if safety_result.should_delegate:
            logger.warning(f"⚠️  Delegation required: {safety_result.delegation_reason}")
            
            yield DamlReasonResult(
                action="delegate",
                valid=False,
                confidence=safety_result.confidence,
                issues=[f"Analysis uncertain: {safety_result.delegation_reason}"],
                suggestions=["Simplify the authorization model", "Use canonical patterns", "Request manual review"],
                llm_insights=safety_result.llm_insights,
                business_intent=business_intent,
                delegation_reason=safety_result.delegation_reason,
                reasoning=f"Code complexity exceeds reliable analysis threshold. "
                         f"Consider simplifying or using canonical patterns."
            )
            return
        
        # CASE 2c: Validation failed - provide issues + pattern recommendations
        logger.warning(f"❌ Code validation failed: {safety_result.blocked_reason}")
        
        issues = []
        if safety_result.blocked_reason:
            issues.append(safety_result.blocked_reason)
        
        if safety_result.compilation_result and not safety_result.compilation_result.succeeded:
            for error in safety_result.compilation_result.errors:
                issues.append(str(error))
        
        # Get pattern recommendations to help fix the issues
        self._ensure_structured_resources()
        
        use_case = self._infer_use_case(business_intent)
        request = RecommendationRequest(
            use_case=use_case,
            description=business_intent,
            security_level=None,
            complexity_level=None,
            constraints=security_requirements,
            existing_patterns=[]
        )
        
        recommendations = self._recommender.recommend_resources(request)
        
        formatted_patterns = []
        for rec in recommendations[:5]:
            formatted_patterns.append({
                "name": rec.resource.name,
                "path": rec.resource.file_path,
                "score": rec.relevance_score,
                "reasoning": rec.reasoning,
                "use_case": rec.use_case_match
            })
        
        yield DamlReasonResult(
            action="suggest_edits",
            valid=False,
            confidence=safety_result.confidence,
            issues=issues,
            suggestions=["Review the recommended patterns below", "Fix authorization model issues", "Ensure all signatories are defined"],
            llm_insights=safety_result.llm_insights,
            business_intent=business_intent,
            recommended_patterns=formatted_patterns,
            reasoning="Code validation failed. Review issues and consider using recommended canonical patterns."
        )

    def _extract_module_name(self, daml_code: str) -> Optional[str]:
        """Extract module name from DAML code"""
        match = re.search(r'^\s*module\s+(\w+)\s+where', daml_code, re.MULTILINE)
        return match.group(1) if match else None

    def _infer_use_case(self, business_intent: str) -> str:
        """Infer use_case from business intent using simple keyword matching."""
        intent_lower = business_intent.lower()
        
        # Keyword-based use case detection
        if any(kw in intent_lower for kw in ["asset", "portfolio", "fund", "investment"]):
            return "asset_management"
        elif any(kw in intent_lower for kw in ["bond", "swap", "option", "instrument", "financial"]):
            return "financial_instruments"
        elif any(kw in intent_lower for kw in ["vote", "govern", "proposal", "dao"]):
            return "governance"
        elif any(kw in intent_lower for kw in ["identity", "kyc", "credential", "verification"]):
            return "identity_management"
        elif any(kw in intent_lower for kw in ["supply", "chain", "logistics", "shipment"]):
            return "supply_chain"
        else:
            return "basic_templates"

