"""
DAML Policy Checker

Simple anti-pattern detection using canonical resources.
Checks DAML code against known anti-patterns and suggests safe alternatives.
"""

import logging
import re
from typing import List, Optional

from ..core.resources.base import AntiPatternResource, PatternResource
from .types import PolicyCheckResult

logger = logging.getLogger(__name__)


async def check_against_policies(
    code: str,
    anti_patterns: List[AntiPatternResource],
    safe_patterns: List[PatternResource],
) -> PolicyCheckResult:
    """
    Check DAML code against canonical anti-patterns.
    
    Simple pattern detection based on anti-pattern detection_pattern fields.
    Uses straightforward heuristics to identify known vulnerabilities.
    
    Args:
        code: DAML source code to check
        anti_patterns: List of canonical anti-patterns to check against
        safe_patterns: List of safe patterns to suggest as alternatives
        
    Returns:
        PolicyCheckResult with match information and suggested alternatives
    """
    logger.info(f"Checking code against {len(anti_patterns)} anti-patterns")
    
    # Check each anti-pattern
    for anti_pattern in anti_patterns:
        match_result = _check_single_anti_pattern(code, anti_pattern)
        
        if match_result["matches"]:
            logger.warning(
                f"Code matches anti-pattern: {anti_pattern.name} "
                f"(confidence: {match_result['confidence']:.0%})"
            )
            
            # Find relevant safe alternatives
            suggested = _suggest_alternatives(
                anti_pattern, safe_patterns, match_result["reasons"]
            )
            
            return PolicyCheckResult(
                matches_anti_pattern=True,
                matched_anti_pattern_name=anti_pattern.name,
                match_reasoning=match_result["reasoning"],
                suggested_alternatives=[p.name for p in suggested],
                llm_response=_format_policy_block_message(
                    anti_pattern, suggested, match_result
                ),
            )
    
    logger.info("✅ Code passed all anti-pattern checks")
    
    return PolicyCheckResult(
        matches_anti_pattern=False,
        llm_response="Code does not match any known anti-patterns",
    )


def _check_single_anti_pattern(
    code: str, anti_pattern: AntiPatternResource
) -> dict:
    """
    Check if code matches a single anti-pattern.
    
    Uses detection patterns and structural analysis from anti-pattern definition.
    
    Returns:
        Dict with keys: matches (bool), confidence (float), reasons (list), reasoning (str)
    """
    reasons = []
    confidence_scores = []
    
    content = anti_pattern.content
    detection_patterns = content.get("detection_pattern", [])
    
    # Check each detection pattern from the anti-pattern YAML
    for pattern_desc in detection_patterns:
        if _matches_detection_pattern(code, pattern_desc):
            reasons.append(pattern_desc)
            confidence_scores.append(0.8)  # High confidence for explicit patterns
    
    # Check for missing signatory (common anti-pattern)
    if "signatory" in anti_pattern.name.lower() or "missing-signatory" in anti_pattern.name:
        if _has_missing_signatory(code):
            reasons.append("Template defined without signatory clause")
            confidence_scores.append(0.9)
    
    # Check for excessive authority patterns
    if "authority" in anti_pattern.name.lower() or "excessive" in anti_pattern.name.lower():
        if _has_excessive_authority(code):
            reasons.append("Multiple parties as signatories without proper constraints")
            confidence_scores.append(0.7)
    
    # Calculate overall confidence
    if confidence_scores:
        avg_confidence = sum(confidence_scores) / len(confidence_scores)
    else:
        avg_confidence = 0.0
    
    # Match if we have reasons and confidence above threshold
    matches = bool(reasons) and avg_confidence >= 0.6
    
    reasoning = "; ".join(reasons) if reasons else "No match"
    
    return {
        "matches": matches,
        "confidence": avg_confidence,
        "reasons": reasons,
        "reasoning": reasoning,
    }


def _matches_detection_pattern(code: str, pattern_desc: str) -> bool:
    """
    Check if code matches a detection pattern description.
    
    Simple keyword and structure matching based on pattern description.
    """
    code_lower = code.lower()
    pattern_lower = pattern_desc.lower()
    
    # Extract key phrases from pattern description
    if "without signatory" in pattern_lower:
        return _has_template_without_signatory(code)
    
    if "missing signatory" in pattern_lower or "signatory clauses" in pattern_lower:
        return _has_template_without_signatory(code)
    
    if "controllers not in signatory" in pattern_lower:
        return _has_controller_not_signatory(code)
    
    if "multi-party" in pattern_lower and "incomplete" in pattern_lower:
        return _has_incomplete_multiparty(code)
    
    # Default: check if key terms appear in wrong context
    return False


def _has_missing_signatory(code: str) -> bool:
    """Check if code has template without signatory declaration."""
    # Look for template definition
    has_template = re.search(r"template\s+\w+", code)
    if not has_template:
        return False
    
    # Look for signatory declaration
    has_signatory = re.search(r"\bsignatory\b", code)
    
    return has_template and not has_signatory


def _has_template_without_signatory(code: str) -> bool:
    """Check if template is defined but signatory is missing."""
    return _has_missing_signatory(code)


def _has_controller_not_signatory(code: str) -> bool:
    """Check if controller is not in signatory list."""
    # This is a simplified check - full implementation would parse the auth model
    has_controller = re.search(r"\bcontroller\b", code)
    has_signatory = re.search(r"\bsignatory\b", code)
    
    # If we have controller but no signatory, that's a problem
    return has_controller and not has_signatory


def _has_incomplete_multiparty(code: str) -> bool:
    """Check for incomplete multi-party authorization."""
    # Look for multiple parties without proper signatory
    has_multiple_parties = len(re.findall(r":\s*Party", code)) > 1
    has_signatory = re.search(r"\bsignatory\b", code)
    
    return has_multiple_parties and not has_signatory


def _has_excessive_authority(code: str) -> bool:
    """Check for excessive authority patterns."""
    # Look for all parties being signatories (authority explosion)
    signatory_match = re.search(r"signatory\s+(.+)", code)
    if not signatory_match:
        return False
    
    signatory_text = signatory_match.group(1).lower()
    
    # Check for patterns like "signatory admin, users" or multiple parties
    has_multiple = "," in signatory_text or len(signatory_text.split()) > 2
    
    return has_multiple


def _suggest_alternatives(
    anti_pattern: AntiPatternResource,
    safe_patterns: List[PatternResource],
    match_reasons: List[str],
) -> List[PatternResource]:
    """
    Suggest safe alternative patterns based on anti-pattern match.
    
    Uses tag matching and problem domain to find relevant safe patterns.
    """
    suggestions = []
    
    anti_pattern_tags = set(anti_pattern.metadata.tags)
    
    for pattern in safe_patterns:
        pattern_tags = set(pattern.metadata.tags)
        
        # Calculate tag overlap
        overlap = anti_pattern_tags & pattern_tags
        overlap_score = len(overlap) / max(len(anti_pattern_tags), 1)
        
        # Prioritize patterns that solve the same problem
        if overlap_score > 0.3:  # At least 30% tag overlap
            suggestions.append(pattern)
        
        # Also suggest patterns that address signatory issues
        if "signatory" in match_reasons[0].lower() if match_reasons else False:
            if "signatory" in pattern.name.lower() or "authorization" in pattern_tags:
                if pattern not in suggestions:
                    suggestions.append(pattern)
    
    # If no specific matches, return all safe patterns as fallback
    if not suggestions and safe_patterns:
        suggestions = safe_patterns[:3]  # Return top 3
    
    return suggestions[:5]  # Limit to 5 suggestions


def _format_policy_block_message(
    anti_pattern: AntiPatternResource,
    suggested_patterns: List[PatternResource],
    match_result: dict,
) -> str:
    """
    Format a human-readable policy block message.
    
    Explains why code was blocked and suggests alternatives.
    """
    lines = [
        f"❌ BLOCKED: Code matches anti-pattern '{anti_pattern.name}'",
        "",
        f"Reason: {match_result['reasoning']}",
        "",
        "Why this is problematic:",
        anti_pattern.content.get("why_problematic", "Security or correctness violation"),
        "",
    ]
    
    if suggested_patterns:
        lines.append("✅ Suggested safe alternatives:")
        for pattern in suggested_patterns:
            lines.append(f"  - {pattern.name}: {pattern.metadata.description}")
        lines.append("")
    
    lines.append(
        f"See anti-pattern documentation: canton://canonical/anti-patterns/{anti_pattern.name}"
    )
    
    return "\n".join(lines)

