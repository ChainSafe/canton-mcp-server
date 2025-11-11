"""
Canonical Resource Recommendation MCP Tool

MCP tool that acts as a "sentinel" to intelligently recommend canonical resources
based on user requirements and use cases.
"""

import logging
import os
from typing import Dict, List, Any, Optional
from pathlib import Path

from ..core.structured_ingestion import StructuredIngestionEngine
from ..core.resource_recommender import CanonicalResourceRecommender, RecommendationRequest
from ..core.direct_file_loader import DirectFileResourceLoader
from ..core.types.mcp import Tool, ToolResult

logger = logging.getLogger(__name__)


def recommend_canonical_resources(
    use_case: str,
    description: str,
    security_level: Optional[str] = None,
    complexity_level: Optional[str] = None,
    constraints: Optional[List[str]] = None,
    existing_patterns: Optional[List[str]] = None
) -> ToolResult:
    """
    Recommend canonical DAML patterns, anti-patterns, and documentation based on user requirements.
    
    This tool acts as a "sentinel" that intelligently maps user requests to the most
    relevant canonical resources from the official DAML/Canton ecosystem.
    
    Args:
        use_case: The primary use case (e.g., "asset_management", "financial_instruments", "governance")
        description: Detailed description of what you're trying to build
        security_level: Required security level ("basic", "enhanced", "enterprise")
        complexity_level: Required complexity level ("beginner", "intermediate", "advanced")
        constraints: List of specific constraints or requirements
        existing_patterns: List of patterns you're already using (to avoid duplicates)
    
    Returns:
        ToolResult with recommended canonical resources and reasoning
    """
    try:
        logger.info(f"Recommending canonical resources for use case: {use_case}")
        
        # Load and structure canonical resources
        canonical_docs_path = Path(os.environ.get("CANONICAL_DOCS_PATH", "../../canonical-daml-docs"))
        loader = DirectFileResourceLoader(canonical_docs_path)
        raw_resources = loader.get_all_resources()
        
        # Structure the resources
        ingestion_engine = StructuredIngestionEngine()
        structured_resources = ingestion_engine.ingest_resources(raw_resources)
        
        # Create recommender
        recommender = CanonicalResourceRecommender(structured_resources)
        
        # Create recommendation request
        request = RecommendationRequest(
            use_case=use_case,
            description=description,
            security_level=security_level,
            complexity_level=complexity_level,
            constraints=constraints or [],
            existing_patterns=existing_patterns or []
        )
        
        # Get recommendations
        recommendations = recommender.recommend_resources(request)
        
        if not recommendations:
            return ToolResult(
                success=False,
                content="No relevant canonical resources found for your requirements. Try adjusting your use case or constraints.",
                metadata={
                    "use_case": use_case,
                    "available_use_cases": list(structured_resources.keys())
                }
            )
        
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
        
        return ToolResult(
            success=True,
            content=f"Found {len(recommendations)} relevant canonical resources for your {use_case} use case:",
            metadata={
                "recommendations": formatted_recommendations,
                "use_case": use_case,
                "total_canonical_resources": sum(len(resources) for resources in structured_resources.values()),
                "available_use_cases": list(structured_resources.keys())
            }
        )
        
    except Exception as e:
        logger.error(f"Error recommending canonical resources: {e}")
        return ToolResult(
            success=False,
            content=f"Failed to recommend canonical resources: {str(e)}",
            metadata={"error": str(e)}
        )


def get_canonical_resource_overview() -> ToolResult:
    """
    Get an overview of available canonical resources organized by use case.
    
    Returns:
        ToolResult with overview of canonical resources by use case
    """
    try:
        logger.info("Getting canonical resource overview")
        
        # Load and structure canonical resources
        canonical_docs_path = Path(os.environ.get("CANONICAL_DOCS_PATH", "../../canonical-daml-docs"))
        loader = DirectFileResourceLoader(canonical_docs_path)
        raw_resources = loader.get_all_resources()
        
        # Structure the resources
        ingestion_engine = StructuredIngestionEngine()
        structured_resources = ingestion_engine.ingest_resources(raw_resources)
        
        # Create recommender for overview
        recommender = CanonicalResourceRecommender(structured_resources)
        overview = recommender.get_use_case_overview()
        
        return ToolResult(
            success=True,
            content="Canonical resource overview by use case:",
            metadata={
                "overview": overview,
                "total_resources": sum(len(resources) for resources in structured_resources.values()),
                "use_cases": list(structured_resources.keys())
            }
        )
        
    except Exception as e:
        logger.error(f"Error getting canonical resource overview: {e}")
        return ToolResult(
            success=False,
            content=f"Failed to get canonical resource overview: {str(e)}",
            metadata={"error": str(e)}
        )


# MCP Tool definitions
RECOMMEND_CANONICAL_RESOURCES_TOOL = Tool(
    name="recommend_canonical_resources",
    description="Recommend canonical DAML patterns, anti-patterns, and documentation based on user requirements. Acts as a 'sentinel' to intelligently map user requests to the most relevant canonical resources.",
    inputSchema={
        "type": "object",
        "properties": {
            "use_case": {
                "type": "string",
                "description": "The primary use case (e.g., 'asset_management', 'financial_instruments', 'governance', 'identity_management', 'supply_chain', 'basic_templates')"
            },
            "description": {
                "type": "string",
                "description": "Detailed description of what you're trying to build"
            },
            "security_level": {
                "type": "string",
                "enum": ["basic", "enhanced", "enterprise"],
                "description": "Required security level (optional)"
            },
            "complexity_level": {
                "type": "string",
                "enum": ["beginner", "intermediate", "advanced"],
                "description": "Required complexity level (optional)"
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of specific constraints or requirements (optional)"
            },
            "existing_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of patterns you're already using to avoid duplicates (optional)"
            }
        },
        "required": ["use_case", "description"]
    }
)

GET_CANONICAL_OVERVIEW_TOOL = Tool(
    name="get_canonical_resource_overview",
    description="Get an overview of available canonical resources organized by use case, security level, and complexity.",
    inputSchema={
        "type": "object",
        "properties": {},
        "required": []
    }
)
