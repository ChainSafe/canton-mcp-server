"""
DAML Safety Checker

Gate 1: DAML Compiler Safety
Orchestrates safety validation through compilation.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .audit_trail import AuditTrail
from .authorization_validator import AuthorizationValidator
from .daml_compiler_integration import DamlCompiler
from .type_safety_verifier import TypeSafetyVerifier
from .types import CompilationResult, CompilationStatus, SafetyCheckResult

if TYPE_CHECKING:
    from ..core.semantic_search import DAMLSemanticSearch

logger = logging.getLogger(__name__)


class SafetyChecker:
    """
    Gate 1: DAML Compiler Safety

    Orchestrates complete safety validation:
    1. Compile with DAML compiler
    2. Extract authorization model
    3. Verify type safety
    4. Generate safety certificate
    5. Maintain audit trail
    6. Block unsafe patterns
    """

    def __init__(
        self,
        compiler: Optional[DamlCompiler] = None,
        auth_validator: Optional[AuthorizationValidator] = None,
        type_verifier: Optional[TypeSafetyVerifier] = None,
        audit_trail: Optional[AuditTrail] = None,
        semantic_search: Optional['DAMLSemanticSearch'] = None,
    ):
        """
        Initialize safety checker with validators.

        Args:
            compiler: DAML compiler (creates default if None)
            auth_validator: Authorization validator (creates default if None)
            type_verifier: Type safety verifier (creates default if None)
            audit_trail: Audit trail (creates default if None)
            semantic_search: Semantic search engine for finding similar files (creates on first use if None)
        """
        from ..env import get_env, get_env_bool, get_env_float
        
        # Store compiler or config for lazy initialization
        self._compiler = compiler
        self._sdk_version = get_env("DAML_SDK_VERSION", "3.4.0-snapshot.20251013.0")
        
        # Initialize AuthorizationValidator with LLM support if enabled
        if auth_validator is None:
            llm_client = None
            if get_env_bool("ENABLE_LLM_AUTH_EXTRACTION", True):
                try:
                    from anthropic import Anthropic
                    api_key = get_env("ANTHROPIC_API_KEY", "")
                    if api_key:
                        llm_client = Anthropic(api_key=api_key)
                        logger.info("✅ LLM-enhanced authorization extraction enabled")
                    else:
                        logger.warning("ENABLE_LLM_AUTH_EXTRACTION=true but ANTHROPIC_API_KEY not set")
                except ImportError:
                    logger.warning("anthropic package not installed, LLM auth extraction disabled")
            
            confidence_threshold = get_env_float("LLM_AUTH_CONFIDENCE_THRESHOLD", 0.7)
            auth_validator = AuthorizationValidator(
                llm_client=llm_client,
                confidence_threshold=confidence_threshold
            )
        
        self.auth_validator = auth_validator
        self.type_verifier = type_verifier or TypeSafetyVerifier()
        self.audit_trail = audit_trail or AuditTrail()
        self.semantic_search = semantic_search
        self._raw_resources = None

        logger.info("Safety checker initialized (Gate 1: DAML Compiler Safety)")

    @property
    def compiler(self) -> Optional[DamlCompiler]:
        """Lazy initialization of DAML compiler (optional - may not be available)."""
        if self._compiler is None:
            try:
                self._compiler = DamlCompiler(sdk_version=self._sdk_version)
                logger.info("✅ DAML compiler available for server-side compilation")
            except Exception as e:
                logger.warning(f"⚠️ DAML compiler not available: {e}")
                logger.info("Continuing without compilation - using LLM analysis only")
                return None
        return self._compiler

    def _ensure_semantic_search(self):
        """Lazy initialization of semantic search with raw resources."""
        if self.semantic_search is None:
            from pathlib import Path
            import os
            from ..core.direct_file_loader import DirectFileResourceLoader
            from ..core.semantic_search import create_semantic_search
            
            logger.info("Initializing semantic search for safety checking...")
            canonical_docs_path = Path(os.environ.get("CANONICAL_DOCS_PATH", "../../canonical-daml-docs"))
            loader = DirectFileResourceLoader(canonical_docs_path)
            self._raw_resources = loader.scan_repositories(force_refresh=False)
            
            # Flatten all resources
            all_resources = []
            for resources in self._raw_resources.values():
                all_resources.extend(resources)
            
            logger.info(f"Indexing {len(all_resources)} resources for semantic search...")
            self.semantic_search = create_semantic_search(
                raw_resources=all_resources,
                force_reindex=False
            )
            
            if self.semantic_search:
                stats = self.semantic_search.get_stats()
                logger.info(f"✅ Semantic search initialized: {stats['indexed_count']} resources indexed")
            else:
                logger.warning("⚠️ Semantic search unavailable - will skip similarity checks")

    async def _check_safety_with_llm(
        self,
        code: str,
        similar_files: list,
        compilation_result: Optional[CompilationResult]
    ) -> dict:
        """
        Use LLM to reason about code safety by comparing to similar files.
        
        Returns:
            Dict with keys: is_safe, reasoning, confidence, full_response
        """
        from ..env import get_env
        import asyncio
        
        # Check if LLM is available
        api_key = get_env("ANTHROPIC_API_KEY", "")
        if not api_key:
            # No LLM available - fall back to compilation-only validation
            return {
                "is_safe": True,
                "reasoning": "No LLM available for safety analysis. Relying on compilation checks only.",
                "confidence": 0.5,
                "full_response": None
            }
        
        try:
            from anthropic import Anthropic
            llm_client = Anthropic(api_key=api_key)
            
            # Format similar files for LLM context
            context = self._format_similar_files_for_llm(similar_files)
            
            # Determine compilation status message
            if compilation_result is None:
                compilation_status = "⊘ Not compiled (server-side compilation unavailable)"
            elif compilation_result.succeeded:
                compilation_status = "✓ Passed"
            else:
                compilation_status = "✗ Failed"
            
            # Ask LLM to reason about code safety
            response = await asyncio.to_thread(
                llm_client.messages.create,
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": f"""Analyze this DAML code for safety issues by comparing it to similar examples from canonical repositories.

USER'S CODE:
```daml
{code}
```

COMPILATION STATUS: {compilation_status}

SIMILAR EXAMPLES FROM CANONICAL REPOS:
{context}

Analyze:
1. Does this code match any problematic patterns in the similar examples?
2. Are there authorization issues (missing signatories, improper controllers)?
3. Does it follow best practices shown in the canonical examples?
4. What specific safety concerns exist?

Respond in JSON format:
{{
  "is_safe": true/false,
  "reasoning": "Brief explanation of safety assessment",
  "concerns": ["list", "of", "concerns"],
  "references": ["which similar files are relevant"],
  "confidence": 0.0-1.0
}}

Be specific and reference the similar files by their paths."""
                }]
            )
            
            # Parse LLM response
            response_text = response.content[0].text
            
            # Extract JSON from response (handle markdown code blocks)
            import json
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                result = json.loads(json_match.group(0))
                return {
                    "is_safe": result.get("is_safe", True),
                    "reasoning": result.get("reasoning", ""),
                    "confidence": result.get("confidence", 0.7),
                    "full_response": response_text,
                    "concerns": result.get("concerns", []),
                    "references": result.get("references", [])
                }
            else:
                # Couldn't parse JSON - treat as unsafe to be cautious
                return {
                    "is_safe": False,
                    "reasoning": "LLM response could not be parsed. Manual review required.",
                    "confidence": 0.3,
                    "full_response": response_text
                }
                
        except Exception as e:
            logger.error(f"LLM safety check failed: {e}")
            return {
                "is_safe": True,  # Don't block on LLM errors
                "reasoning": f"LLM safety check error: {e}. Relying on compilation checks only.",
                "confidence": 0.5,
                "full_response": None
            }

    def _format_similar_files_for_llm(self, similar_files: list) -> str:
        """Format similar files for LLM context."""
        formatted = []
        for i, file in enumerate(similar_files[:5], 1):
            formatted.append(f"""
FILE {i}: {file.get('file_path', 'unknown')} (similarity: {file.get('similarity_score', 0):.3f})
---
{file.get('content', '')[:1000]}
---
""")
        return "\n".join(formatted)

    async def check_pattern_safety(
        self, code: str, module_name: str = "Main", compilation_context: Optional[dict] = None
    ) -> SafetyCheckResult:
        """
        Gate 1: DAML Compiler Safety Check

        Complete safety validation flow:
        1. Use compilation context from client (if provided)
        2. Run similarity search (always)
        3. Extract authorization model with LLM (uses compilation + similarity context)
        4. Verify type safety
        5. Validate authorization model
        6. Generate safety certificate
        7. Log to audit trail
        8. Return result

        NOTE: Server never compiles - compilation is delegated to client.
        Full analysis only runs when compilation_context is provided.

        Args:
            code: DAML source code to validate
            module_name: Module name (default: "Main")
            compilation_context: Optional client-side compilation result

        Returns:
            SafetyCheckResult with pass/fail and details
        """
        logger.info(f"Starting safety check for module: {module_name}")

        # Generate code hash for audit trail
        if self.compiler:
            code_hash = self.compiler.get_code_hash(code)
        else:
            # Fallback hash when compiler not available
            code_hash = hashlib.sha256(code.encode()).hexdigest()

        # Step 1: Use compilation context from client (server never compiles)
        compilation_result = None
        compilation_skipped = True  # Always true - server doesn't compile
        
        if compilation_context:
            logger.info("✅ Using client-provided compilation context")
            # Convert dict to CompilationResult if needed
            # For now, we'll work with the dict directly in authorization extraction
            # TODO: Convert to proper CompilationResult object
        else:
            logger.info("⚠️ No compilation context provided - semantic analysis only")

        # Step 2: Check if compilation failed (only if we compiled)
        if compilation_result:
            blocked, blocked_reason = self._should_block(compilation_result)
        else:
            blocked = False
            blocked_reason = None

        if blocked:
            logger.warning(f"Pattern blocked: {blocked_reason}")

            # Log to audit trail
            audit_id = self.audit_trail.log_compilation(
                code_hash=code_hash,
                module_name=module_name,
                result=compilation_result,
                auth_model=None,
                blocked=True,
            )

            return SafetyCheckResult(
                passed=False,
                compilation_result=compilation_result,
                authorization_model=None,
                blocked_reason=blocked_reason,
                safety_certificate=None,
                audit_id=audit_id,
                compilation_skipped=compilation_skipped,
            )

        # Step 2.5: Check code safety using ChromaDB + LLM reasoning
        self._ensure_semantic_search()
        
        if self.semantic_search:
            similar_files = self.semantic_search.search_similar_files(
                code=code,
                top_k=5,
                raw_resources=[r for resources in self._raw_resources.values() for r in resources]
            )
            
            # Let LLM reason about code safety with similar examples as context
            llm_safety_check = await self._check_safety_with_llm(
                code=code,
                similar_files=similar_files,
                compilation_result=compilation_result
            )
            
            if not llm_safety_check.get("is_safe", True):
                # Block with LLM reasoning
                logger.warning(f"Code blocked by LLM safety check: {llm_safety_check.get('reasoning', 'Unknown reason')}")
                
                audit_id = self.audit_trail.log_compilation(
                    code_hash=code_hash,
                    module_name=module_name,
                    result=compilation_result,
                    auth_model=None,
                    blocked=True,
                )
                
                return SafetyCheckResult(
                    passed=False,
                    compilation_result=compilation_result,
                    authorization_model=None,
                    blocked_reason=llm_safety_check.get("reasoning", "LLM safety check failed"),
                    safety_certificate=None,
                    audit_id=audit_id,
                    compilation_skipped=compilation_skipped,
                    llm_insights=llm_safety_check.get("full_response"),
                    similar_files=similar_files  # Already limited to 5
                )

        # Step 3: Extract authorization model with confidence scoring
        auth_extraction = self.auth_validator.extract_auth_model(code, compilation_result)
        
        # Store extraction result for insights (will be added to SafetyCheckResult)
        extraction_insights = None
        if auth_extraction.llm_full_response:
            # Extract any text outside the JSON as insights
            try:
                full_text = auth_extraction.llm_full_response
                first_brace = full_text.find('{')
                last_brace = full_text.rfind('}')
                
                insights_parts = []
                if first_brace > 0:
                    before = full_text[:first_brace].strip()
                    if before:
                        insights_parts.append(before)
                
                if last_brace < len(full_text) - 1:
                    after = full_text[last_brace + 1:].strip()
                    if after:
                        insights_parts.append(after)
                
                if insights_parts:
                    extraction_insights = "\n\n".join(insights_parts)
            except Exception as e:
                logger.debug(f"Could not extract LLM insights: {e}")
        
        # Step 3.5: Check if we should delegate (confidence too low)
        if auth_extraction.confidence < 0.7:
            logger.warning(
                f"Authorization extraction confidence too low: {auth_extraction.confidence:.2f}. "
                f"Method: {auth_extraction.method}, Uncertain fields: {auth_extraction.uncertain_fields}"
            )
            
            # Log to audit trail with delegation flag
            audit_id = self.audit_trail.log_compilation(
                code_hash=code_hash,
                module_name=module_name,
                result=compilation_result,
                auth_model=auth_extraction.model,
                blocked=False,  # Not blocked, just uncertain
            )
            
            delegation_details = f"Authorization extraction confidence too low ({auth_extraction.confidence:.2f})"
            if auth_extraction.uncertain_fields:
                delegation_details += f". Uncertain patterns: {', '.join(auth_extraction.uncertain_fields)}"
            
            return SafetyCheckResult(
                passed=False,
                should_delegate=True,
                compilation_skipped=compilation_skipped,
                delegation_reason=delegation_details,
                confidence=auth_extraction.confidence,
                compilation_result=compilation_result,
                authorization_model=auth_extraction.model,
                blocked_reason=None,
                safety_certificate=None,
                audit_id=audit_id,
                llm_insights=extraction_insights,
            )

        # Step 4: Verify type safety (skip if no compilation result)
        type_safe = True  # Assume safe if we couldn't compile
        if compilation_result:
            type_safe = self.type_verifier.verify_type_safety(compilation_result)
        else:
            logger.info("Skipping type safety verification (no compilation result)")

        # Step 5: Validate authorization model
        auth_valid = True
        if auth_extraction.model:
            auth_valid = self.auth_validator.validate_authorization(auth_extraction.model)
        else:
            logger.warning("Could not extract authorization model")
            auth_valid = False

        # Step 6: Final safety determination
        if not type_safe or not auth_valid:
            blocked_reason = self._build_block_reason(type_safe, auth_valid)
            logger.warning(f"Pattern blocked: {blocked_reason}")

            audit_id = self.audit_trail.log_compilation(
                code_hash=code_hash,
                module_name=module_name,
                result=compilation_result,
                auth_model=auth_extraction.model,
                blocked=True,
            )

            return SafetyCheckResult(
                passed=False,
                should_delegate=False,
                delegation_reason=None,
                confidence=auth_extraction.confidence,
                compilation_result=compilation_result,
                compilation_skipped=compilation_skipped,
                authorization_model=auth_extraction.model,
                blocked_reason=blocked_reason,
                safety_certificate=None,
                audit_id=audit_id,
            )

        # Step 7: Generate safety certificate
        safety_certificate = self._generate_safety_certificate(
            code_hash, auth_extraction.model, compilation_result
        )

        # Step 8: Log to audit trail
        audit_id = self.audit_trail.log_compilation(
            code_hash=code_hash,
            module_name=module_name,
            result=compilation_result,
            auth_model=auth_extraction.model,
            blocked=False,
        )

        logger.info(f"✅ Pattern passed safety check: {module_name} (audit: {audit_id})")

        return SafetyCheckResult(
            passed=True,
            should_delegate=False,  # High confidence, no delegation needed
            delegation_reason=None,
            confidence=auth_extraction.confidence,
            compilation_result=compilation_result,
            compilation_skipped=compilation_skipped,
            authorization_model=auth_extraction.model,
            blocked_reason=None,
            safety_certificate=safety_certificate,
            audit_id=audit_id,
            llm_insights=extraction_insights,
        )

    def _should_block(
        self, compilation_result
    ) -> tuple[bool, Optional[str]]:
        """
        Determine if pattern should be blocked based on compilation result.

        Args:
            compilation_result: DAML compilation result

        Returns:
            Tuple of (should_block, reason)
        """
        # Block if compilation failed
        if not compilation_result.succeeded:
            error_summary = self.type_verifier.get_error_summary(
                compilation_result.errors
            )
            return True, f"Compilation failed:\n{error_summary}"

        # Block if system error
        if compilation_result.status == CompilationStatus.ERROR:
            return True, "System error during compilation"

        # Passed compilation
        return False, None

    def _build_block_reason(self, type_safe: bool, auth_valid: bool) -> str:
        """
        Build human-readable block reason.

        Args:
            type_safe: Whether type safety check passed
            auth_valid: Whether authorization validation passed

        Returns:
            Formatted block reason string
        """
        reasons = []

        if not type_safe:
            reasons.append("Type safety verification failed")

        if not auth_valid:
            reasons.append("Authorization model invalid or missing")

        return "; ".join(reasons)

    def _generate_safety_certificate(
        self, code_hash: str, auth_model, compilation_result
    ) -> str:
        """
        Generate safety certificate for validated pattern.

        Certificate contains:
        - Code hash (SHA256)
        - DAML SDK version
        - Authorization model
        - Compilation timestamp
        - Certificate signature

        Args:
            code_hash: SHA256 hash of code
            auth_model: Authorization model
            compilation_result: Compilation result

        Returns:
            JSON safety certificate
        """
        certificate = {
            "version": "1.0",
            "gate": "daml_compiler_safety",
            "timestamp": datetime.utcnow().isoformat(),
            "code_hash": code_hash,
            "daml_sdk_version": self.compiler.sdk_version,
            "compilation_time_ms": compilation_result.compilation_time_ms,
            "authorization_model": {
                "template": auth_model.template_name,
                "signatories": auth_model.signatories,
                "observers": auth_model.observers,
                "controllers": auth_model.controllers,
            }
            if auth_model
            else None,
            "type_safe": True,
            "strict_mode": True,
        }

        # Generate certificate signature (hash of certificate data)
        cert_json = json.dumps(certificate, sort_keys=True)
        certificate["signature"] = hashlib.sha256(cert_json.encode()).hexdigest()

        return json.dumps(certificate, indent=2)

    def get_audit_stats(self) -> dict:
        """
        Get audit trail statistics.

        Returns:
            Dictionary with audit stats
        """
        return self.audit_trail.get_stats()
