"""
Canonical Resource Recommendation Tool

Acts as a "sentinel" to intelligently map user requests to the right canonical resources
from the structured ingestion system.
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .structured_ingestion import StructuredIngestionEngine, StructuredResource, SecurityLevel, ComplexityLevel

logger = logging.getLogger(__name__)


@dataclass
class RecommendationRequest:
    """Request for canonical resource recommendations."""
    use_case: str
    description: str
    security_level: Optional[str] = None
    complexity_level: Optional[str] = None
    constraints: Optional[List[str]] = None
    existing_patterns: Optional[List[str]] = None


@dataclass
class ResourceRecommendation:
    """A recommended canonical resource."""
    resource: StructuredResource
    relevance_score: float
    reasoning: str
    use_case_match: str


class CanonicalResourceRecommender:
    """
    Recommends canonical resources based on user requirements.
    
    Acts as a "sentinel" that intelligently maps user requests to the most
    relevant canonical patterns, anti-patterns, and documentation.
    """
    
    def __init__(self, structured_resources: Dict[str, List[StructuredResource]]):
        """
        Initialize the recommender with structured resources.
        
        Args:
            structured_resources: Resources organized by use case
        """
        self.structured_resources = structured_resources
        self.ingestion_engine = StructuredIngestionEngine()
        
        # Build search index for better recommendations
        self._build_search_index()
    
    def _build_search_index(self):
        """Build a search index for better recommendations."""
        self.search_index = {}
        
        for use_case, resources in self.structured_resources.items():
            for resource in resources:
                # Index by keywords
                for keyword in resource.keywords:
                    if keyword not in self.search_index:
                        self.search_index[keyword] = []
                    self.search_index[keyword].append(resource)
    
    def recommend_resources(self, request: RecommendationRequest) -> List[ResourceRecommendation]:
        """
        Recommend canonical resources based on user requirements.
        
        Args:
            request: User's requirements and constraints
            
        Returns:
            List of recommended resources with relevance scores
        """
        logger.info(f"Recommending resources for use case: {request.use_case}")
        
        recommendations = []
        
        # Get base resources for the use case
        base_resources = self.structured_resources.get(request.use_case, [])
        
        # Filter by security and complexity levels if specified
        filtered_resources = self._filter_by_requirements(base_resources, request)
        
        # Score and rank resources
        for resource in filtered_resources:
            score, reasoning = self._calculate_relevance_score(resource, request)
            if score > 0.3:  # Only recommend resources with decent relevance
                recommendations.append(ResourceRecommendation(
                    resource=resource,
                    relevance_score=score,
                    reasoning=reasoning,
                    use_case_match=request.use_case
                ))
        
        # Sort by relevance score
        recommendations.sort(key=lambda x: x.relevance_score, reverse=True)
        
        # Limit to top 5 recommendations
        return recommendations[:5]
    
    def _filter_by_requirements(self, resources: List[StructuredResource], request: RecommendationRequest) -> List[StructuredResource]:
        """Filter resources based on security and complexity requirements."""
        filtered = []
        
        for resource in resources:
            # Check security level
            if request.security_level:
                required_security = SecurityLevel(request.security_level)
                if resource.security_level.value != required_security.value:
                    # Allow higher security levels
                    if not self._is_higher_security_level(resource.security_level, required_security):
                        continue
            
            # Check complexity level
            if request.complexity_level:
                required_complexity = ComplexityLevel(request.complexity_level)
                if resource.complexity_level.value != required_complexity.value:
                    # Allow lower complexity levels
                    if not self._is_lower_complexity_level(resource.complexity_level, required_complexity):
                        continue
            
            filtered.append(resource)
        
        return filtered
    
    def _is_higher_security_level(self, resource_level: SecurityLevel, required_level: SecurityLevel) -> bool:
        """Check if resource security level is higher than required."""
        security_hierarchy = {
            SecurityLevel.BASIC: 1,
            SecurityLevel.ENHANCED: 2,
            SecurityLevel.ENTERPRISE: 3
        }
        return security_hierarchy[resource_level] >= security_hierarchy[required_level]
    
    def _is_lower_complexity_level(self, resource_level: ComplexityLevel, required_level: ComplexityLevel) -> bool:
        """Check if resource complexity level is lower than required."""
        complexity_hierarchy = {
            ComplexityLevel.BEGINNER: 1,
            ComplexityLevel.INTERMEDIATE: 2,
            ComplexityLevel.ADVANCED: 3
        }
        return complexity_hierarchy[resource_level] <= complexity_hierarchy[required_level]
    
    def _calculate_relevance_score(self, resource: StructuredResource, request: RecommendationRequest) -> tuple[float, str]:
        """Calculate relevance score for a resource."""
        score = 0.0
        reasoning_parts = []
        
        # Base score for use case match
        if request.use_case in resource.use_cases:
            score += 0.4
            reasoning_parts.append(f"Matches use case '{request.use_case}'")
        
        # Score based on description keywords
        description_keywords = self._extract_keywords_from_text(request.description)
        keyword_matches = sum(1 for keyword in description_keywords if keyword in resource.keywords)
        if keyword_matches > 0:
            keyword_score = min(0.3, keyword_matches * 0.1)
            score += keyword_score
            reasoning_parts.append(f"Matches {keyword_matches} keywords from description")
        
        # Score based on constraints
        if request.constraints:
            constraint_matches = self._check_constraint_matches(resource, request.constraints)
            if constraint_matches > 0:
                constraint_score = min(0.2, constraint_matches * 0.05)
                score += constraint_score
                reasoning_parts.append(f"Satisfies {constraint_matches} constraints")
        
        # Bonus for exact security/complexity match
        if request.security_level and resource.security_level.value == request.security_level:
            score += 0.1
            reasoning_parts.append(f"Exact security level match ({request.security_level})")
        
        if request.complexity_level and resource.complexity_level.value == request.complexity_level:
            score += 0.1
            reasoning_parts.append(f"Exact complexity level match ({request.complexity_level})")
        
        reasoning = "; ".join(reasoning_parts) if reasoning_parts else "Basic relevance"
        return score, reasoning
    
    def _extract_keywords_from_text(self, text: str) -> List[str]:
        """Extract keywords from text."""
        import re
        words = re.findall(r'\b\w+\b', text.lower())
        return [word for word in words if len(word) > 3 and word.isalpha()]
    
    def _check_constraint_matches(self, resource: StructuredResource, constraints: List[str]) -> int:
        """Check how many constraints the resource satisfies."""
        matches = 0
        resource_text = ' '.join(resource.keywords).lower() + ' ' + resource.content[:200].lower()
        
        for constraint in constraints:
            constraint_lower = constraint.lower()
            if any(word in resource_text for word in constraint_lower.split()):
                matches += 1
        
        return matches
    
    def get_use_case_overview(self) -> Dict[str, Any]:
        """Get an overview of available use cases and their resources."""
        overview = {}
        
        for use_case, resources in self.structured_resources.items():
            overview[use_case] = {
                "total_resources": len(resources),
                "security_levels": list(set(r.security_level.value for r in resources)),
                "complexity_levels": list(set(r.complexity_level.value for r in resources)),
                "sample_patterns": [r.name for r in resources[:3]]
            }
        
        return overview
