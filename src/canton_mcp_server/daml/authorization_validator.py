"""
DAML Authorization Model Validator

Extracts and validates authorization models from DAML templates.
"""

import logging
import re
from typing import Dict, List, Optional

from .types import AuthorizationModel, CompilationResult

logger = logging.getLogger(__name__)


class AuthorizationValidator:
    """
    Extract and validate DAML authorization models.

    Parses DAML code to extract:
    - Signatories
    - Observers
    - Controllers (per choice)
    """

    def extract_auth_model(
        self, code: str, compilation_result: CompilationResult
    ) -> Optional[AuthorizationModel]:
        """
        Extract authorization model from DAML code.

        Only works if compilation succeeded (code is syntactically valid).

        Args:
            code: DAML source code
            compilation_result: Result of compilation

        Returns:
            AuthorizationModel if extracted, None if extraction failed
        """
        # Only extract from successfully compiled code
        if not compilation_result.succeeded:
            logger.debug("Skipping auth extraction - compilation failed")
            return None

        try:
            # Extract template name
            template_name = self._extract_template_name(code)
            if not template_name:
                logger.warning("Could not extract template name from code")
                return None

            # Extract authorization declarations
            signatories = self._parse_signatories(code)
            observers = self._parse_observers(code)
            controllers = self._parse_controllers(code)

            auth_model = AuthorizationModel(
                template_name=template_name,
                signatories=signatories,
                observers=observers,
                controllers=controllers,
            )

            logger.info(
                f"Extracted auth model for {template_name}: "
                f"{len(signatories)} signatories, {len(observers)} observers, "
                f"{len(controllers)} choices"
            )

            return auth_model

        except Exception as e:
            logger.error(f"Error extracting authorization model: {e}", exc_info=True)
            return None

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

