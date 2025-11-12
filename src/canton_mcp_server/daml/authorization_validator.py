"""
DAML Authorization Model Validator

Extracts and validates authorization models from DAML templates.
Supports confidence scoring and LLM fallback for complex patterns.
"""

import json
import logging
import re
from typing import Dict, List, Optional

from .types import AuthorizationModel, AuthorizationExtractionResult, CompilationResult

logger = logging.getLogger(__name__)


class AuthorizationValidator:
    """
    Extract and validate DAML authorization models.

    Parses DAML code to extract:
    - Signatories
    - Observers
    - Controllers (per choice)
    
    Supports confidence scoring and LLM fallback for complex patterns.
    """

    def __init__(self, llm_client=None, confidence_threshold: float = 0.7):
        """
        Initialize authorization validator.
        
        Args:
            llm_client: Optional Anthropic client for LLM fallback
            confidence_threshold: Minimum confidence to avoid delegation (default: 0.7)
        """
        self.llm_client = llm_client
        self.confidence_threshold = confidence_threshold

    def extract_auth_model(
        self, code: str, compilation_result: CompilationResult
    ) -> AuthorizationExtractionResult:
        """
        Extract authorization model from DAML code using LLM-primary approach.
        
        PRIMARY PATH: Use LLM for robust, reliable extraction
        FALLBACK PATH: Use regex patterns when LLM unavailable (degraded mode)

        Only works if compilation succeeded (code is syntactically valid).

        Args:
            code: DAML source code
            compilation_result: Result of compilation

        Returns:
            AuthorizationExtractionResult with model and confidence score
        """
        # Only extract from successfully compiled code
        if not compilation_result.succeeded:
            logger.debug("Skipping auth extraction - compilation failed")
            return AuthorizationExtractionResult(
                model=None,
                confidence=0.0,
                method="compilation_failed",
                uncertain_fields=[],
                reasoning="Compilation failed"
            )

        # PRIMARY PATH: Use LLM if available
        if self.llm_client:
            logger.info("🤖 Using LLM for authorization extraction (primary path)")
            llm_result = self._extract_with_llm(code, None)
            
            if llm_result.confidence >= 0.85:
                logger.info(f"✅ LLM extraction succeeded (confidence: {llm_result.confidence:.2f})")
                return llm_result
            else:
                logger.warning(
                    f"⚠️  LLM extraction uncertain (confidence: {llm_result.confidence:.2f}), "
                    f"falling back to regex"
                )
                # Fall through to regex as last resort

        # FALLBACK PATH: Use regex patterns (degraded mode)
        logger.info("🔧 Using regex for authorization extraction (degraded mode - LLM unavailable)")
        
        try:
            # Extract template name
            template_name = self._extract_template_name(code)
            if not template_name:
                logger.warning("Could not extract template name from code")
                return AuthorizationExtractionResult(
                    model=None,
                    confidence=0.0,
                    method="regex_failed",
                    uncertain_fields=[],
                    reasoning="Could not extract template name. Enable LLM for better extraction."
                )

            # Extract authorization declarations with regex
            signatories = self._parse_signatories(code)
            observers = self._parse_observers(code)
            controllers = self._parse_controllers(code)

            auth_model = AuthorizationModel(
                template_name=template_name,
                signatories=signatories,
                observers=observers,
                controllers=controllers,
            )

            # In degraded mode, check for complex patterns that regex can't handle
            has_complex_patterns = (
                "<>" in code or  # List concatenation
                ("::" in code and "signatory" in code) or  # List cons in signatories
                "if" in code and "then" in code  # Conditional expressions
            )
            
            if has_complex_patterns:
                logger.warning(
                    "⚠️  Detected complex DAML patterns that regex cannot reliably parse. "
                    "Enable LLM (ANTHROPIC_API_KEY + ENABLE_LLM_AUTH_EXTRACTION=true) for full coverage."
                )
                return AuthorizationExtractionResult(
                    model=auth_model,
                    confidence=0.5,  # Low confidence in degraded mode with complex patterns
                    method="regex_degraded_complex",
                    uncertain_fields=["Complex patterns detected: enable LLM for accurate extraction"],
                    reasoning=(
                        "Regex extraction in degraded mode with complex patterns. "
                        "Enable LLM for reliable extraction of list operations and expressions."
                    )
                )
            
            # Simple patterns - regex should be fine
            logger.info(
                f"Extracted auth model for {template_name}: "
                f"{len(signatories)} signatories, {len(observers)} observers, "
                f"{len(controllers)} choices (regex degraded mode)"
            )
            
            return AuthorizationExtractionResult(
                model=auth_model,
                confidence=0.8,  # Decent confidence for simple patterns in degraded mode
                method="regex_degraded_simple",
                uncertain_fields=[],
                reasoning="Regex extraction of simple patterns (degraded mode). Enable LLM for full coverage."
            )

        except Exception as e:
            logger.error(f"Error extracting authorization model: {e}", exc_info=True)
            return AuthorizationExtractionResult(
                model=None,
                confidence=0.0,
                method="regex_failed",
                uncertain_fields=[],
                reasoning=f"Extraction error: {str(e)}. Enable LLM for better extraction."
            )

    def _extract_template_name(self, code: str) -> Optional[str]:
        """
        Extract template name from DAML code.

        Matches: template TemplateName
        """
        match = re.search(r"template\s+([A-Z][A-Za-z0-9_]*)", code)
        return match.group(1) if match else None

    def _parse_signatories(self, code: str) -> List[str]:
        """
        Extract signatory declarations from DAML code.

        Matches patterns:
        - signatory party
        - signatory [party1, party2]
        - signatory party1, party2
        """
        signatories = []

        # Pattern: signatory <parties>
        # Handles: signatory issuer
        #         signatory [issuer, owner]
        #         signatory issuer, owner
        pattern = r"signatory\s+(.+?)(?:\n|$)"

        for match in re.finditer(pattern, code, re.MULTILINE):
            parties_str = match.group(1).strip()

            # Remove brackets and split by comma
            parties_str = parties_str.strip("[]")
            parties = [p.strip() for p in parties_str.split(",")]

            signatories.extend([p for p in parties if p and not p.startswith("--")])

        # Deduplicate while preserving order
        seen = set()
        result = []
        for s in signatories:
            if s not in seen:
                seen.add(s)
                result.append(s)

        logger.debug(f"Parsed signatories: {result}")
        return result

    def _parse_observers(self, code: str) -> List[str]:
        """
        Extract observer declarations from DAML code.

        Matches patterns:
        - observer party
        - observer [party1, party2]
        """
        observers = []

        # Pattern: observer <parties>
        pattern = r"observer\s+(.+?)(?:\n|$)"

        for match in re.finditer(pattern, code, re.MULTILINE):
            parties_str = match.group(1).strip()

            # Remove brackets and split by comma
            parties_str = parties_str.strip("[]")
            parties = [p.strip() for p in parties_str.split(",")]

            observers.extend([p for p in parties if p and not p.startswith("--")])

        # Deduplicate while preserving order
        seen = set()
        result = []
        for o in observers:
            if o not in seen:
                seen.add(o)
                result.append(o)

        logger.debug(f"Parsed observers: {result}")
        return result

    def _parse_controllers(self, code: str) -> Dict[str, List[str]]:
        """
        Extract controller declarations from DAML choices.

        Matches patterns:
        - choice ChoiceName : ReturnType
            with ...
            controller party
        - choice ChoiceName : ReturnType
            controller [party1, party2]
        """
        controllers = {}

        # Pattern: choice <name> ... controller <parties>
        # Use regex with DOTALL to match across lines
        choice_pattern = r"choice\s+([A-Z][A-Za-z0-9_]*)\s*:.*?controller\s+(.+?)(?:do|where)"

        for match in re.finditer(choice_pattern, code, re.DOTALL):
            choice_name = match.group(1)
            controllers_str = match.group(2).strip()

            # Remove brackets, newlines, and split by comma
            controllers_str = controllers_str.strip("[]").replace("\n", " ")
            parties = [p.strip() for p in controllers_str.split(",")]

            # Filter out empty strings and comments
            parties = [p for p in parties if p and not p.startswith("--")]

            if parties:
                controllers[choice_name] = parties

        logger.debug(f"Parsed controllers: {controllers}")
        return controllers

    def _calculate_confidence(self, model: AuthorizationModel, code: str) -> tuple[float, List[str]]:
        """
        Calculate confidence score for extracted authorization model.
        
        Args:
            model: Extracted authorization model
            code: Original DAML code
            
        Returns:
            Tuple of (confidence_score, uncertain_fields)
        """
        if not model:
            return (0.0, ["No model extracted"])
        
        confidence = 1.0
        uncertain_fields = []
        
        # Reduce confidence for complex patterns we can't fully parse
        
        # Check for list concatenation (e.g., approvers <> observers)
        if "<>" in code:
            confidence *= 0.6
            uncertain_fields.append("list concatenation (<>)")
        
        # Check for list cons operator (e.g., requester :: approvers)
        if "::" in code and "signatory" in code:
            confidence *= 0.7
            uncertain_fields.append("list cons (::) in signatories")
        
        # Check for potential list fields as controllers
        for choice, controllers in model.controllers.items():
            for controller in controllers:
                # If controller name is plural, likely a list field
                if controller.endswith("s") or controller.endswith("ers"):
                    confidence *= 0.65
                    uncertain_fields.append(f"controller '{controller}' (likely list field)")
        
        # Check for potential list fields in observers
        for observer in model.observers:
            if observer.endswith("s") or observer.endswith("ers"):
                # Less penalty since observers are often list fields
                confidence *= 0.85
                uncertain_fields.append(f"observer '{observer}' (likely list field)")
        
        # Check for complex choice patterns
        if re.search(r"controller\s+\[", code):
            confidence *= 0.9
            uncertain_fields.append("explicit controller lists")
        
        return (max(confidence, 0.0), uncertain_fields)
    
    def _extract_with_llm(self, code: str, partial_model: Optional[AuthorizationModel]) -> AuthorizationExtractionResult:
        """
        Use LLM to extract authorization model from DAML code (primary method).
        
        Args:
            code: DAML source code
            partial_model: Unused (kept for compatibility)
            
        Returns:
            AuthorizationExtractionResult with LLM-extracted model
        """
        if not self.llm_client:
            return AuthorizationExtractionResult(
                model=None,
                confidence=0.0,
                method="llm_unavailable",
                uncertain_fields=[],
                reasoning="LLM client not available"
            )
        
        try:
            prompt = f"""You are a DAML code analyzer. Extract the authorization model from this DAML template.

DAML Code:
```daml
{code}
```

TASK: Extract authorization declarations from the template above.

RULES for extraction:
1. Extract field names, not values
2. For list operations:
   - "owner :: approvers" → ["owner", "approvers"]
   - "managers <> viewers" → ["managers", "viewers"]
   - "[party1, party2]" → ["party1", "party2"]
3. For controllers: Map each choice name to its controller field names
4. Extract ONLY the first template if multiple exist
5. If you see complex expressions (conditionals, function calls), include all referenced field names

EXAMPLES:

Example 1 - Simple:
```daml
template Simple
  with
    owner: Party
    viewer: Party
  where
    signatory owner
    observer viewer
```
Output: {{"template_name": "Simple", "signatories": ["owner"], "observers": ["viewer"], "controllers": {{}}, "confidence": 1.0}}

Example 2 - List operations:
```daml
template Complex
  with
    owner: Party
    managers: [Party]
    viewers: [Party]
  where
    signatory owner :: managers
    observer viewers
    choice Approve : ()
      controller managers
      do return ()
```
Output: {{"template_name": "Complex", "signatories": ["owner", "managers"], "observers": ["viewers"], "controllers": {{"Approve": ["managers"]}}, "confidence": 0.95}}

Example 3 - Concatenation:
```daml
template MultiParty
  with
    owner: Party
    approvers: [Party]
    watchers: [Party]
  where
    signatory owner
    observer approvers <> watchers
```
Output: {{"template_name": "MultiParty", "signatories": ["owner"], "observers": ["approvers", "watchers"], "controllers": {{}}, "confidence": 0.95}}

CONFIDENCE SCALE:
- 1.0: Simple, clear patterns
- 0.95: List operations (<>, ::)
- 0.9: Multiple choices
- 0.8: Complex but clear expressions
- 0.5: Ambiguous or unclear

OUTPUT FORMAT:
First, return the JSON object:

{{
  "template_name": "...",
  "signatories": [...],
  "observers": [...],
  "controllers": {{"ChoiceName": [...]}},
  "confidence": 0.95,
  "reasoning": "Brief explanation"
}}

Then, OPTIONALLY add additional insights after the JSON if you have valuable context to share:
- Explanation of complex patterns
- Why confidence is not 1.0
- Common DAML patterns identified
- Security considerations
- Best practices

IMPORTANT: For choice parameters (like "with approver: Party"), extract the FIELD that validates them, not the parameter name.
Example: If "controller approver" has "assertMsg (approver `elem` approvers)", the controller is "approvers" (the field).

If you see interesting patterns worth explaining, add a paragraph after the JSON explaining them. This helps developers understand their code better."""

            response = self.llm_client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,
                temperature=0.0,  # Deterministic
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse LLM response
            content = response.content[0].text.strip()
            
            # Extract JSON from response (handle multiple formats)
            if "```json" in content:
                # Format: ```json\n{...}\n```
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                # Format: ```\n{...}\n```
                content = content.split("```")[1].split("```")[0]
            
            # Clean up content
            content = content.strip()
            
            # Find the JSON object (from first { to last })
            # This handles cases where LLM adds text before or after the JSON
            first_brace = content.find('{')
            last_brace = content.rfind('}')
            
            if first_brace == -1 or last_brace == -1:
                raise ValueError("No JSON object found in LLM response")
            
            json_content = content[first_brace:last_brace + 1]
            
            result = json.loads(json_content)
            
            model = AuthorizationModel(
                template_name=result.get("template_name", "Unknown"),
                signatories=result.get("signatories", []),
                observers=result.get("observers", []),
                controllers=result.get("controllers", {})
            )
            
            confidence = float(result.get("confidence", 0.5))
            reasoning = result.get("reasoning", "LLM extraction")
            
            # Extract any additional context before/after the JSON
            full_response = content  # Preserve full LLM response
            additional_context = ""
            
            # Text before JSON
            if first_brace > 0:
                before_text = content[:first_brace].strip()
                if before_text:
                    additional_context += before_text + "\n\n"
            
            # Text after JSON
            if last_brace < len(content) - 1:
                after_text = content[last_brace + 1:].strip()
                if after_text:
                    additional_context += after_text
            
            if additional_context:
                logger.info(f"🤖 LLM provided additional context: {additional_context[:200]}...")
            
            logger.info(f"🤖 LLM extraction: {model.template_name} (confidence={confidence:.2f}): {reasoning}")
            
            return AuthorizationExtractionResult(
                model=model,
                confidence=confidence,
                method="llm_primary",
                uncertain_fields=[],
                reasoning=reasoning,
                llm_full_response=full_response  # Preserve complete LLM output
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {e}", exc_info=True)
            return AuthorizationExtractionResult(
                model=None,
                confidence=0.0,
                method="llm_parse_failed",
                uncertain_fields=[],
                reasoning=f"LLM returned invalid JSON: {str(e)}"
            )
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}", exc_info=True)
            return AuthorizationExtractionResult(
                model=None,
                confidence=0.0,
                method="llm_failed",
                uncertain_fields=[],
                reasoning=f"LLM extraction error: {str(e)}"
            )

    def validate_authorization(self, auth_model: AuthorizationModel) -> bool:
        """
        Validate that authorization model is sound.

        Rules:
        1. At least one signatory is required
        2. All controllers must be signatories or observers
        3. No duplicate parties across roles (warning only)

        Args:
            auth_model: Authorization model to validate

        Returns:
            True if valid, False otherwise
        """
        # Rule 1: At least one signatory
        if not auth_model.signatories:
            logger.warning(
                f"Authorization model invalid: {auth_model.template_name} "
                "has no signatories"
            )
            return False

        # Rule 2: Controllers must be parties
        all_parties = set(auth_model.signatories + auth_model.observers)

        for choice, choice_controllers in auth_model.controllers.items():
            for controller in choice_controllers:
                if controller not in all_parties:
                    logger.warning(
                        f"Authorization model invalid: controller '{controller}' "
                        f"in choice '{choice}' is not a signatory or observer"
                    )
                    return False

        # Rule 3: Check for overlaps (warning only)
        signatory_set = set(auth_model.signatories)
        observer_set = set(auth_model.observers)
        overlap = signatory_set.intersection(observer_set)

        if overlap:
            logger.info(
                f"Note: Parties {overlap} are both signatories and observers. "
                "This is allowed but may be redundant."
            )

        logger.info(f"Authorization model valid for {auth_model.template_name}")
        return True





