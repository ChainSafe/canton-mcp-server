"""
Structured Ingestion System

Categorizes and indexes canonical resources by use case, complexity, and security level
instead of serving a massive blob of 3,667 files.
"""

import logging
import re
from typing import Dict, List, Any, Optional, Set
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security complexity levels for DAML patterns."""
    BASIC = "basic"           # Single party, simple authorization
    ENHANCED = "enhanced"     # Multi-party, audit trails
    ENTERPRISE = "enterprise" # Complex governance, compliance


class ComplexityLevel(Enum):
    """Complexity levels for DAML patterns."""
    BEGINNER = "beginner"     # Simple templates, basic choices
    INTERMEDIATE = "intermediate"  # Multi-party, state machines
    ADVANCED = "advanced"     # Complex workflows, governance


@dataclass
class UseCaseCategory:
    """Represents a use case category for DAML patterns."""
    name: str
    description: str
    keywords: List[str]
    security_level: SecurityLevel
    complexity_level: ComplexityLevel


@dataclass
class StructuredResource:
    """A canonical resource with structured metadata."""
    name: str
    file_path: str
    content: str
    file_type: str
    use_cases: List[str]
    security_level: SecurityLevel
    complexity_level: ComplexityLevel
    keywords: List[str]
    related_patterns: List[str]
    canonical_hash: str
    source_repo: str
    source_commit: str


class StructuredIngestionEngine:
    """
    Ingests canonical resources and structures them by use case and complexity.
    """
    
    def __init__(self):
        """Initialize the structured ingestion engine."""
        
        # Define use case categories
        self.use_cases = {
            "asset_management": UseCaseCategory(
                name="Asset Management",
                description="Patterns for managing digital assets, transfers, and ownership",
                keywords=["asset", "transfer", "ownership", "custody", "vault"],
                security_level=SecurityLevel.ENHANCED,
                complexity_level=ComplexityLevel.INTERMEDIATE
            ),
            "financial_instruments": UseCaseCategory(
                name="Financial Instruments",
                description="Patterns for financial products, settlements, and clearing",
                keywords=["settlement", "clearing", "payment", "bond", "equity", "derivative"],
                security_level=SecurityLevel.ENTERPRISE,
                complexity_level=ComplexityLevel.ADVANCED
            ),
            "governance": UseCaseCategory(
                name="Governance",
                description="Patterns for organizational governance and decision making",
                keywords=["governance", "voting", "approval", "consensus", "board"],
                security_level=SecurityLevel.ENTERPRISE,
                complexity_level=ComplexityLevel.ADVANCED
            ),
            "identity_management": UseCaseCategory(
                name="Identity Management",
                description="Patterns for identity verification and access control",
                keywords=["identity", "authentication", "authorization", "access", "permission"],
                security_level=SecurityLevel.ENHANCED,
                complexity_level=ComplexityLevel.INTERMEDIATE
            ),
            "supply_chain": UseCaseCategory(
                name="Supply Chain",
                description="Patterns for supply chain tracking and provenance",
                keywords=["supply", "chain", "provenance", "tracking", "logistics"],
                security_level=SecurityLevel.ENHANCED,
                complexity_level=ComplexityLevel.INTERMEDIATE
            ),
            "basic_templates": UseCaseCategory(
                name="Basic Templates",
                description="Simple templates for learning and basic use cases",
                keywords=["template", "simple", "basic", "hello", "example"],
                security_level=SecurityLevel.BASIC,
                complexity_level=ComplexityLevel.BEGINNER
            )
        }
        
        # Security level indicators
        self.security_indicators = {
            SecurityLevel.BASIC: ["single", "simple", "basic", "hello", "example"],
            SecurityLevel.ENHANCED: ["multi", "party", "approval", "audit", "tracking"],
            SecurityLevel.ENTERPRISE: ["governance", "compliance", "settlement", "clearing", "regulatory"]
        }
        
        # Complexity indicators
        self.complexity_indicators = {
            ComplexityLevel.BEGINNER: ["simple", "basic", "hello", "example", "template"],
            ComplexityLevel.INTERMEDIATE: ["multi", "party", "state", "machine", "workflow"],
            ComplexityLevel.ADVANCED: ["complex", "governance", "settlement", "clearing", "compliance"]
        }
    
    def ingest_resources(self, raw_resources: List[Dict[str, Any]]) -> Dict[str, List[StructuredResource]]:
        """
        Ingest raw resources and structure them by use case.
        
        Args:
            raw_resources: List of raw resource dictionaries from DirectFileResourceLoader
            
        Returns:
            Dictionary mapping use cases to structured resources
        """
        logger.info(f"Structuring {len(raw_resources)} canonical resources...")
        
        structured_by_use_case = {use_case: [] for use_case in self.use_cases.keys()}
        
        for resource in raw_resources:
            try:
                structured = self._structure_resource(resource)
                if structured:
                    # Assign to relevant use cases
                    for use_case in structured.use_cases:
                        if use_case in structured_by_use_case:
                            structured_by_use_case[use_case].append(structured)
                    
                    # Always include in basic_templates if it's simple
                    if structured.complexity_level == ComplexityLevel.BEGINNER:
                        structured_by_use_case["basic_templates"].append(structured)
                        
            except Exception as e:
                logger.warning(f"Failed to structure resource {resource.get('name', 'unknown')}: {e}")
                continue
        
        # Log results
        for use_case, resources in structured_by_use_case.items():
            logger.info(f"Use case '{use_case}': {len(resources)} resources")
        
        return structured_by_use_case
    
    def _structure_resource(self, resource: Dict[str, Any]) -> Optional[StructuredResource]:
        """
        Structure a single resource with metadata.
        
        Args:
            resource: Raw resource dictionary
            
        Returns:
            Structured resource or None if structuring failed
        """
        name = resource.get("name", "")
        content = resource.get("content", "")
        file_path = resource.get("file_path", "")
        
        # Extract keywords from content and path
        keywords = self._extract_keywords(content, file_path, name)
        
        # Determine use cases
        use_cases = self._determine_use_cases(keywords, content)
        
        # Determine security level
        security_level = self._determine_security_level(keywords, content)
        
        # Determine complexity level
        complexity_level = self._determine_complexity_level(keywords, content)
        
        # Find related patterns
        related_patterns = self._find_related_patterns(keywords, content)
        
        return StructuredResource(
            name=name,
            file_path=file_path,
            content=content,
            file_type=resource.get("file_extension", ""),
            use_cases=use_cases,
            security_level=security_level,
            complexity_level=complexity_level,
            keywords=keywords,
            related_patterns=related_patterns,
            canonical_hash=resource.get("canonical_hash", ""),
            source_repo=resource.get("source_repo", ""),
            source_commit=resource.get("source_commit", "")
        )
    
    def _extract_keywords(self, content: str, file_path: str, name: str) -> List[str]:
        """Extract keywords from content, path, and name."""
        keywords = set()
        
        # Extract from file path
        path_parts = file_path.lower().split('/')
        keywords.update(path_parts)
        
        # Extract from name
        name_words = re.findall(r'\b\w+\b', name.lower())
        keywords.update(name_words)
        
        # Extract from content (first 1000 chars to avoid performance issues)
        content_sample = content[:1000].lower()
        content_words = re.findall(r'\b\w+\b', content_sample)
        
        # Filter for relevant keywords
        relevant_words = [word for word in content_words if len(word) > 3 and word.isalpha()]
        keywords.update(relevant_words[:20])  # Limit to top 20 words
        
        return list(keywords)
    
    def _determine_use_cases(self, keywords: List[str], content: str) -> List[str]:
        """Determine which use cases this resource belongs to."""
        use_cases = []
        keyword_text = ' '.join(keywords).lower()
        content_lower = content[:500].lower()  # Sample first 500 chars
        
        for use_case_name, use_case in self.use_cases.items():
            # Check if any keywords match
            keyword_matches = sum(1 for keyword in use_case.keywords if keyword in keyword_text)
            content_matches = sum(1 for keyword in use_case.keywords if keyword in content_lower)
            
            # If we have matches, include this use case
            if keyword_matches > 0 or content_matches > 0:
                use_cases.append(use_case_name)
        
        # Default to basic_templates if no matches
        if not use_cases:
            use_cases.append("basic_templates")
        
        return use_cases
    
    def _determine_security_level(self, keywords: List[str], content: str) -> SecurityLevel:
        """Determine the security level of the resource."""
        keyword_text = ' '.join(keywords).lower()
        content_lower = content[:500].lower()
        
        # Count matches for each security level
        level_scores = {}
        for level, indicators in self.security_indicators.items():
            score = sum(1 for indicator in indicators if indicator in keyword_text or indicator in content_lower)
            level_scores[level] = score
        
        # Return the level with highest score, default to BASIC
        if level_scores:
            return max(level_scores.items(), key=lambda x: x[1])[0]
        return SecurityLevel.BASIC
    
    def _determine_complexity_level(self, keywords: List[str], content: str) -> ComplexityLevel:
        """Determine the complexity level of the resource."""
        keyword_text = ' '.join(keywords).lower()
        content_lower = content[:500].lower()
        
        # Count matches for each complexity level
        level_scores = {}
        for level, indicators in self.complexity_indicators.items():
            score = sum(1 for indicator in indicators if indicator in keyword_text or indicator in content_lower)
            level_scores[level] = score
        
        # Return the level with highest score, default to BEGINNER
        if level_scores:
            return max(level_scores.items(), key=lambda x: x[1])[0]
        return ComplexityLevel.BEGINNER
    
    def _find_related_patterns(self, keywords: List[str], content: str) -> List[str]:
        """Find related patterns based on keywords and content."""
        # This is a simplified implementation
        # In a real system, you'd have more sophisticated pattern matching
        related = []
        
        keyword_text = ' '.join(keywords).lower()
        
        # Simple pattern matching based on common DAML patterns
        if "transfer" in keyword_text:
            related.extend(["multi-party-approval", "delegation"])
        if "approval" in keyword_text:
            related.extend(["simple-transfer", "governance"])
        if "governance" in keyword_text:
            related.extend(["multi-party-approval", "voting"])
        
        return related[:3]  # Limit to 3 related patterns
