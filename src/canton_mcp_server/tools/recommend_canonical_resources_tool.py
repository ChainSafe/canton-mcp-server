"""
Canonical Resource Recommendation Tool

MCP tool for recommending canonical resources based on user requirements.
"""

import logging
import os
import re
from typing import Dict, List, Any, Optional
from pathlib import Path

from pydantic import Field

from ..core import Tool, ToolContext, register_tool
from ..core.pricing import PricingType, ToolPricing
from ..core.responses import ErrorCodes
from ..core.types.models import MCPModel
from ..core.direct_file_loader import DirectFileResourceLoader
from ..core.structured_ingestion import StructuredIngestionEngine
from ..core.resource_recommender import CanonicalResourceRecommender, RecommendationRequest

logger = logging.getLogger(__name__)


class RecommendCanonicalResourcesParams(MCPModel):
    """Parameters for canonical resource recommendations"""
    
    use_case: str = Field(
        description="The primary use case. Accepts both snake_case and camelCase. Examples: 'asset_management' or 'assetManagement', 'financial_instruments' or 'financialInstruments', 'governance', 'identity_management', 'supply_chain', 'basic_templates'"
    )
    description: str = Field(
        description="Detailed description of what you're trying to build. Be specific! Good: 'hedge fund with trading strategies and portfolio rebalancing'. Bad: 'a hedge fund'. Include key concepts, workflows, and domain terms for better matches."
    )
    security_level: Optional[str] = Field(
        default=None,
        description="Required security level ('basic', 'enhanced', 'enterprise')"
    )
    complexity_level: Optional[str] = Field(
        default=None,
        description="Required complexity level ('beginner', 'intermediate', 'advanced')"
    )
    constraints: List[str] = Field(
        default=[],
        description="List of specific constraints or requirements"
    )
    existing_patterns: List[str] = Field(
        default=[],
        description="List of patterns you're already using to avoid duplicates"
    )


@register_tool
class RecommendCanonicalResourcesTool(Tool[RecommendCanonicalResourcesParams, dict]):
    """MCP tool for recommending canonical DAML resources."""
    
    name = "recommend_canonical_resources"
    description = "Recommend canonical DAML patterns, anti-patterns, and documentation based on user requirements. Acts as a 'sentinel' to intelligently map user requests to the most relevant canonical resources."
    params_model = RecommendCanonicalResourcesParams
    pricing = ToolPricing(type=PricingType.FIXED, base_price=0.001)
    
    def __init__(self):
        """Initialize the recommendation tool."""
        super().__init__()
        # Use environment variable for path, falling back to this machine's default
        canonical_docs_path = Path(os.environ.get("CANONICAL_DOCS_PATH", "../../canonical-daml-docs"))
        self.loader = DirectFileResourceLoader(canonical_docs_path)
        self._structured_resources = None
        self._recommender = None
    
    def _ensure_structured_resources(self):
        """Ensure structured resources are loaded."""
        if self._structured_resources is None:
            logger.info("Loading and structuring canonical resources...")
            raw_resources = self.loader.get_all_resources()
            ingestion_engine = StructuredIngestionEngine()
            self._structured_resources = ingestion_engine.ingest_resources(raw_resources)
            self._recommender = CanonicalResourceRecommender(self._structured_resources)
            logger.info(f"Loaded {sum(len(resources) for resources in self._structured_resources.values())} structured resources")
    
    def _normalize_use_case(self, use_case: str) -> str:
        """
        Normalize use_case to snake_case format.
        
        Handles both camelCase and snake_case input from users.
        Examples:
            "assetManagement" -> "asset_management"
            "asset_management" -> "asset_management"
            "financialInstruments" -> "financial_instruments"
        """
        # Convert camelCase to snake_case
        # Insert underscore before uppercase letters that follow lowercase letters
        s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', use_case)
        # Insert underscore before uppercase letters that follow lowercase or uppercase letters
        s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1)
        return s2.lower()
    
    async def execute(self, ctx: ToolContext[RecommendCanonicalResourcesParams, dict]):
        """Execute the recommendation tool."""
        try:
            self._ensure_structured_resources()
            
            # Normalize use_case to snake_case (handle both formats from users)
            use_case_normalized = self._normalize_use_case(ctx.params.use_case)
            
            logger.info(f"Recommending resources for use case: {use_case_normalized} (original: {ctx.params.use_case})")
            
            # Create recommendation request
            request = RecommendationRequest(
                use_case=use_case_normalized,
                description=ctx.params.description,
                security_level=ctx.params.security_level,
                complexity_level=ctx.params.complexity_level,
                constraints=ctx.params.constraints or [],
                existing_patterns=ctx.params.existing_patterns or []
            )
            
            # Get recommendations
            recommendations = self._recommender.recommend_resources(request)
            
            if not recommendations:
                available_use_cases = list(self._structured_resources.keys())
                error_msg = (
                    f"No relevant canonical resources found for use case: '{use_case_normalized}'.\n\n"
                    f"Available use cases: {', '.join(available_use_cases)}\n\n"
                    f"Try:\n"
                    f"1. Use one of the available use cases listed above\n"
                    f"2. Adjust your security_level or complexity_level requirements\n"
                    f"3. Broaden your description to match more resources"
                )
                yield ctx.error(ErrorCodes.UNAVAILABLE_RESOURCES, error_msg)
                return
            
            # Format recommendations
            formatted_recommendations = []
            for rec in recommendations:
                formatted_recommendations.append({
                    "name": rec.resource.name,
                    "file_path": rec.resource.file_path,
                    "relevance_score": rec.relevance_score,
                    "reasoning": rec.reasoning,
                    "use_case_match": rec.use_case_match,
                    "security_level": rec.resource.security_level.value,
                    "complexity_level": rec.resource.complexity_level.value,
                    "keywords": rec.resource.keywords[:10],  # Top 10 keywords
                    "related_patterns": rec.resource.related_patterns,
                    "source_repo": rec.resource.source_repo,
                    "canonical_hash": rec.resource.canonical_hash[:16] + "..."  # Truncated hash
                })
            
            # Create structured result
            result = {
                "message": f"Found {len(recommendations)} relevant canonical resources for your {ctx.params.use_case} use case:",
                "recommendations": formatted_recommendations,
                "use_case": ctx.params.use_case,
                "total_canonical_resources": sum(len(resources) for resources in self._structured_resources.values()),
                "available_use_cases": list(self._structured_resources.keys())
            }
            
            yield ctx.structured(result)
            
        except Exception as e:
            logger.error(f"Error recommending canonical resources: {e}")
            yield ctx.error(ErrorCodes.INTERNAL_ERROR, f"Failed to recommend canonical resources: {str(e)}")


class GetCanonicalOverviewParams(MCPModel):
    """Parameters for getting canonical resource overview"""
    pass


@register_tool
class GetCanonicalOverviewTool(Tool[GetCanonicalOverviewParams, dict]):
    """MCP tool for getting canonical resource overview."""
    
    name = "get_canonical_resource_overview"
    description = "Get an overview of available canonical resources organized by use case, security level, and complexity."
    params_model = GetCanonicalOverviewParams
    pricing = ToolPricing(type=PricingType.FIXED, base_price=0.001)
    
    def __init__(self):
        """Initialize the overview tool."""
        super().__init__()
        # Use environment variable for path, falling back to this machine's default
        canonical_docs_path = Path(os.environ.get("CANONICAL_DOCS_PATH", "../../canonical-daml-docs"))
        self.loader = DirectFileResourceLoader(canonical_docs_path)
        self._structured_resources = None
        self._recommender = None
    
    def _ensure_structured_resources(self):
        """Ensure structured resources are loaded."""
        if self._structured_resources is None:
            logger.info("Loading and structuring canonical resources...")
            raw_resources = self.loader.get_all_resources()
            ingestion_engine = StructuredIngestionEngine()
            self._structured_resources = ingestion_engine.ingest_resources(raw_resources)
            self._recommender = CanonicalResourceRecommender(self._structured_resources)
            logger.info(f"Loaded {sum(len(resources) for resources in self._structured_resources.values())} structured resources")
    
    async def execute(self, ctx: ToolContext[GetCanonicalOverviewParams, dict]):
        """Execute the overview tool."""
        try:
            self._ensure_structured_resources()
            
            overview = self._recommender.get_use_case_overview()
            
            # Create structured result
            result = {
                "message": "Canonical resource overview by use case:",
                "overview": overview,
                "total_resources": sum(len(resources) for resources in self._structured_resources.values()),
                "use_cases": list(self._structured_resources.keys())
            }
            
            yield ctx.structured(result)
            
        except Exception as e:
            logger.error(f"Error getting canonical resource overview: {e}")
            yield ctx.error(f"Failed to get canonical resource overview: {str(e)}")
