"""Canton MCP Tools - Auto-discovery for tool registration"""

from .validate_daml_business_logic import ValidateDamlBusinessLogicTool
from .debug_authorization_failure import DebugAuthorizationFailureTool
from .suggest_authorization_pattern import SuggestAuthorizationPatternTool
from .recommend_canonical_resources_tool import RecommendCanonicalResourcesTool, GetCanonicalOverviewTool

__all__ = [
    "ValidateDamlBusinessLogicTool",
    "DebugAuthorizationFailureTool",
    "SuggestAuthorizationPatternTool",
    "RecommendCanonicalResourcesTool",
    "GetCanonicalOverviewTool",
]

