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
import threading
from typing import List, Optional
from pathlib import Path

from pydantic import Field, model_validator

from ..core import Tool, ToolContext, register_tool
from ..core.pricing import PricingType, ToolPricing
from ..core.types.models import MCPModel
from ..daml.safety_checker import SafetyChecker
from ..core.direct_file_loader import DirectFileResourceLoader
from ..core.semantic_search import DAMLSemanticSearch, create_semantic_search

logger = logging.getLogger(__name__)


class DamlReasonParams(MCPModel):
    """Parameters for DAML Reason tool"""

    business_intent: str = Field(
        description="What the developer wants to achieve with this DAML code"
    )
    query: Optional[str] = Field(
        default=None,
        description="The user's actual question or search query. Used for ChromaDB search when available."
    )

    @model_validator(mode="before")
    @classmethod
    def accept_query_alias(cls, data: dict) -> dict:
        """Accept 'query' as an alias for 'businessIntent'/'business_intent'.

        If both 'query' and 'businessIntent' are provided, keep query as a
        separate field and use businessIntent for business_intent.
        If only 'query' is provided, copy it to business_intent.
        """
        if isinstance(data, dict):
            if "business_intent" not in data and "businessIntent" not in data:
                query = data.get("query")
                if query:
                    data["business_intent"] = query
        return data

    daml_code: Optional[str] = Field(
        default=None,
        description="DAML code to analyze (optional - if not provided, only pattern recommendations returned)"
    )
    security_requirements: Optional[List[str]] = Field(
        default=None,
        description="Specific security requirements to check"
    )
    compilation_result: Optional[dict] = Field(
        default=None,
        description="Client-side compilation result (optional). Provide this after compiling locally to enable full LLM analysis."
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
    
    # Compilation status (when compilation not available on server)
    compilation_skipped: bool = Field(default=False, description="Whether compilation was skipped")
    compilation_instructions: Optional[str] = Field(default=None, description="Instructions to compile code client-side")
    
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
        type=PricingType.FIXED,
        base_price=0.1,  # Fixed price: 0.1 USD (converts to CC via facilitator)
    )

    def __init__(self):
        super().__init__()
        # Initialize SafetyChecker (loads anti-patterns internally via ResourceLoader)
        self.safety_checker = SafetyChecker()

        # Initialize semantic search components (simple and direct)
        canonical_docs_path = Path(os.environ.get("CANONICAL_DOCS_PATH", "../../canonical-daml-docs"))
        self.loader = DirectFileResourceLoader(canonical_docs_path)
        self._raw_resources = None
        self._semantic_search: Optional[DAMLSemanticSearch] = None
        self._semantic_search_lock = threading.Lock()

    def _ensure_semantic_search(self):
        """Ensure semantic search is initialized with raw resources."""
        if self._semantic_search is not None:
            return  # Fast path (no lock needed)

        with self._semantic_search_lock:
            if self._semantic_search is not None:
                return  # Double-check after acquiring lock
            logger.info("🔍 Initializing semantic search...")
            
            # Load raw resources directly from repos (no enrichment, no caching)
            raw_by_category = self.loader.scan_repositories(force_refresh=False)
            
            # Flatten all resources into a single list
            all_resources = []
            for category, resources in raw_by_category.items():
                all_resources.extend(resources)
            
            logger.info(f"📚 Loaded {len(all_resources)} raw resources from canonical repos")

            if not all_resources:
                logger.info("📦 No resources from file scan — will use pre-built ChromaDB index if available")

            # Initialize ChromaDB semantic search (indexes raw content directly)
            self._semantic_search = create_semantic_search(
                raw_resources=all_resources,
                force_reindex=False  # Persist across restarts
            )

            if self._semantic_search:
                stats = self._semantic_search.get_stats()
                count = stats['indexed_count']
                if count > 0 and not all_resources:
                    logger.info(f"✅ Using pre-built ChromaDB index: {count} resources")
                elif count > 0:
                    logger.info(f"✅ Semantic search ready: {count} resources indexed")
                else:
                    logger.warning("⚠️ ChromaDB index is empty — daml_reason will return 0 patterns")
            else:
                logger.warning("⚠️ Semantic search unavailable - falling back to basic recommendations")

            # Keep only lightweight metadata for search result lookups — drop full file
            # content from memory. Search results only need name, file_path, description.
            # On a 2GB box this saves ~100-200MB of Python object overhead.
            self._raw_resources = {
                category: [
                    {
                        "name": r.get("name", ""),
                        "file_path": r.get("file_path", ""),
                        "description": r.get("description", ""),
                        "source_repo": r.get("source_repo", ""),
                        "source_commit": r.get("source_commit", ""),
                        "canonical_hash": r.get("canonical_hash", ""),
                        "similarity_score": 0.0,
                    }
                    for r in resources
                ]
                for category, resources in raw_by_category.items()
            }

            # Free the loader's in-memory cache — full content is no longer needed
            self.loader._cached_resources = {}

            # Share with SafetyChecker so it doesn't create its own loader + ChromaDB copy
            self.safety_checker.semantic_search = self._semantic_search
            self.safety_checker._raw_resources = self._raw_resources

    async def execute(
        self, ctx: ToolContext[DamlReasonParams, DamlReasonResult]
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
        business_intent = ctx.params.business_intent
        daml_code = ctx.params.daml_code
        # Use query for ChromaDB search if available, fall back to business_intent
        search_text = ctx.params.query or business_intent

        # CASE 1: No code provided - just recommend patterns
        if not daml_code or daml_code.strip() == "":
            logger.info(f"No code provided, finding similar patterns for: {search_text}")

            # Initialize semantic search
            self._ensure_semantic_search()

            if self._semantic_search is None:
                yield ctx.structured(DamlReasonResult(
                    action="suggest_patterns",
                    valid=False,
                    business_intent=business_intent,
                    recommended_patterns=[],
                    reasoning="Semantic search unavailable - please provide DAML code for validation"
                ))
                return

            # Use search_text (query preferred) for ChromaDB similarity search
            similar_files = self._semantic_search.search_similar_files(
                code=search_text,
                top_k=5,
                raw_resources=[r for resources in self._raw_resources.values() for r in resources]
            )

            # Format recommendations (raw files, no enrichment)
            formatted_patterns = []
            for file in similar_files:
                formatted_patterns.append({
                    "name": file.get("name", "Unknown"),
                    "path": file.get("file_path", "Unknown"),
                    "score": file.get("similarity_score", 0.0),
                    "description": file.get("description", "")[:200]  # First 200 chars
                })

            # Synthesize a natural language answer using LLM (only when enrichment is enabled)
            from ..env import get_env, get_env_bool
            api_key = get_env("ANTHROPIC_API_KEY", "")
            if api_key and similar_files and get_env_bool("ENABLE_LLM_ENRICHMENT", False):
                logger.info(f"Synthesizing answer for query: {search_text}")
                llm_answer = await self._synthesize_answer(search_text, similar_files, api_key)
                yield ctx.structured(DamlReasonResult(
                    action="suggest_patterns",
                    valid=True,
                    confidence=0.8,
                    llm_insights=llm_answer,
                    business_intent=business_intent,
                    recommended_patterns=formatted_patterns,
                    reasoning=f"Answered using {len(formatted_patterns)} relevant documentation sources."
                ))
            else:
                # Fallback: return raw results (no API key or no results)
                yield ctx.structured(DamlReasonResult(
                    action="suggest_patterns",
                    valid=False,
                    business_intent=business_intent,
                    recommended_patterns=formatted_patterns,
                    reasoning=f"Found {len(formatted_patterns)} similar patterns using semantic search. Review these examples for your use case."
                ))
            return

        # CASE 2: Code provided - run safety check (with compilation context if available)
        logger.info(f"Validating DAML code for: {business_intent}")

        if ctx.params.compilation_result:
            logger.info("Compilation result provided - running full analysis with LLM")
        else:
            logger.info("No compilation result - running semantic analysis")
        
        # Ensure semantic search is injected before safety checker needs it
        self._ensure_semantic_search()

        # Run Gate 1 safety check with compilation context
        module_name = self._extract_module_name(daml_code) or "Main"
        try:
            safety_result = await self.safety_checker.check_pattern_safety(
                daml_code,
                module_name=module_name,
                compilation_context=ctx.params.compilation_result
            )
        except RuntimeError as e:
            logger.error(f"Safety check failed: {e}")
            yield ctx.structured(DamlReasonResult(
                action="delegate",
                valid=False,
                confidence=0.0,
                issues=[],
                business_intent=business_intent,
                delegation_reason="Service temporarily unavailable — analysis requires LLM connectivity",
                reasoning="Safety check could not complete. Ensure ANTHROPIC_API_KEY is set and ENABLE_LLM_ENRICHMENT=true.",
            ))
            return
        
        # CASE 2a: Validation passed with high confidence
        if safety_result.passed and not safety_result.should_delegate:
            logger.info(f"✅ Code validation passed (confidence: {safety_result.confidence:.2f})")
            
            # Prepare compilation instructions if compilation was skipped
            compilation_instructions = None
            if safety_result.compilation_skipped:
                compilation_instructions = """⚠️ Server-side compilation not available. For additional validation:

1. **Compile locally:**
   ```bash
   daml build
   ```

2. **If compilation fails**, send the error messages back for analysis.

3. **If compilation succeeds**, your code passes type checking and you can proceed with deployment.

**Note:** The analysis above is based on LLM reasoning and pattern matching without compilation."""
            
            yield ctx.structured(DamlReasonResult(
                action="approved",
                valid=True,
                confidence=safety_result.confidence,
                issues=[],
                suggestions=["Consider compiling locally for additional type-safety verification"] if safety_result.compilation_skipped else [],
                llm_insights=safety_result.llm_insights,
                business_intent=business_intent,
                recommended_patterns=[],
                compilation_skipped=safety_result.compilation_skipped,
                compilation_instructions=compilation_instructions,
                reasoning=f"Code validated successfully with {safety_result.confidence:.0%} confidence. "
                         f"Authorization model extracted and verified. "
                         f"{'(LLM-based analysis without compilation) ' if safety_result.compilation_skipped else ''}"
                         f"Ready to use."
            ))
            return
        
        # CASE 2b: Low confidence - delegate
        if safety_result.should_delegate:
            logger.warning(f"⚠️  Delegation required: {safety_result.delegation_reason}")
            
            compilation_instructions = None
            if safety_result.compilation_skipped:
                compilation_instructions = """For better analysis, compile your code locally:

```bash
cd /path/to/your/project
daml build
```

Send back any compilation errors for detailed analysis."""
            
            yield ctx.structured(DamlReasonResult(
                action="delegate",
                valid=False,
                confidence=safety_result.confidence,
                issues=[f"Analysis uncertain: {safety_result.delegation_reason}"],
                suggestions=["Compile locally and send back errors", "Simplify the authorization model", "Use canonical patterns", "Request manual review"],
                llm_insights=safety_result.llm_insights,
                business_intent=business_intent,
                delegation_reason=safety_result.delegation_reason,
                compilation_skipped=safety_result.compilation_skipped,
                compilation_instructions=compilation_instructions,
                reasoning="Code complexity exceeds reliable analysis threshold. "
                         f"{'Server-side compilation not available. ' if safety_result.compilation_skipped else ''}"
                         "Consider simplifying or using canonical patterns."
            ))
            return
        
        # CASE 2c: Validation failed - provide issues + pattern recommendations
        logger.warning(f"❌ Code validation failed: {safety_result.blocked_reason}")
        
        issues = []
        if safety_result.blocked_reason:
            issues.append(safety_result.blocked_reason)
        
        # Add compilation errors if available (defensive check)
        if safety_result.compilation_result:
            if hasattr(safety_result.compilation_result, 'succeeded') and not safety_result.compilation_result.succeeded:
                for error in safety_result.compilation_result.errors:
                    issues.append(str(error))
        
        # Use similar_files already found by SafetyChecker — never re-query
        formatted_patterns = []
        for file in (safety_result.similar_files or [])[:5]:
            formatted_patterns.append({
                "name": file.get("name", "Unknown"),
                "path": file.get("file_path", "Unknown"),
                "score": file.get("similarity_score", 0.0),
                "description": file.get("description", "")[:200]
            })
        
        # Prepare compilation instructions if compilation was skipped
        compilation_instructions = None
        if safety_result.compilation_skipped:
            compilation_instructions = """To get detailed compilation errors, compile locally:

```bash
cd /path/to/your/project
daml build
```

This will provide specific line-by-line errors that can help identify the issues."""
            
        yield ctx.structured(DamlReasonResult(
            action="suggest_edits",
            valid=False,
            confidence=safety_result.confidence,
            issues=issues,
            suggestions=["Review the similar patterns below", "Compile locally for detailed errors", "Fix authorization model issues", "Ensure all signatories are defined"],
            llm_insights=safety_result.llm_insights,
            business_intent=business_intent,
            recommended_patterns=formatted_patterns,
            compilation_skipped=safety_result.compilation_skipped,
            compilation_instructions=compilation_instructions,
            reasoning=f"Code validation failed. "
                     f"{'(LLM-based analysis without compilation) ' if safety_result.compilation_skipped else ''}"
                     f"Found {len(formatted_patterns)} similar patterns that might help fix the issues."
        ))

    async def _synthesize_answer(
        self,
        query: str,
        similar_files: list,
        api_key: str,
    ) -> str:
        """Call Claude Haiku to synthesize a natural language answer from ChromaDB results.

        Uses the same pattern as SafetyChecker._check_safety_with_llm().
        """
        import asyncio

        try:
            from anthropic import Anthropic
            llm_client = Anthropic(api_key=api_key)

            # Build context from similar files
            context_parts = []
            for i, f in enumerate(similar_files[:5], 1):
                name = f.get("name", "unknown")
                path = f.get("file_path", "unknown")
                score = f.get("similarity_score", 0.0)
                desc = f.get("description", "")[:500]
                content = f.get("content", "")[:2000]
                entry = f"### Source {i}: {name}\nPath: {path}\nRelevance: {score:.3f}\nDescription: {desc}"
                if content:
                    entry += f"\nContent:\n```\n{content}\n```"
                context_parts.append(entry)

            context = "\n\n".join(context_parts)

            response = await asyncio.to_thread(
                llm_client.messages.create,
                model="claude-3-5-haiku-20241022",
                max_tokens=1500,
                messages=[{
                    "role": "user",
                    "content": f"""You are a DAML expert assistant. Answer the user's question using the documentation excerpts below.

USER'S QUESTION:
{query}

RELEVANT DOCUMENTATION:
{context}

Instructions:
- Give a clear, helpful answer to the question
- Reference specific documentation sources when relevant
- If the documentation doesn't fully answer the question, say so and provide what you can
- Use code examples from the sources when helpful
- Be concise but thorough"""
                }]
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"LLM synthesis failed: {e}")
            return f"Could not synthesize answer: {e}. Raw results are included in recommended_patterns."

    def _extract_module_name(self, daml_code: str) -> Optional[str]:
        """Extract module name from DAML code"""
        match = re.search(r'^\s*module\s+([\w.]+)\s+where', daml_code, re.MULTILINE)
        return match.group(1) if match else None

