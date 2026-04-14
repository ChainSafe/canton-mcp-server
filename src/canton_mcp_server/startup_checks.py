"""
Startup validation for Canton MCP Server.

Validates critical configuration at boot time. If validation fails,
the server crashes with an actionable error message instead of
starting in a broken state.
"""

import logging
from pathlib import Path

from .env import get_env, get_env_bool

logger = logging.getLogger(__name__)

# Feature flags → required env vars
REQUIRED_WHEN = {
    "ENABLE_LLM_ENRICHMENT": ["ANTHROPIC_API_KEY", "LLM_ENRICHMENT_MODEL"],
    "ENABLE_LLM_AUTH_EXTRACTION": ["ANTHROPIC_API_KEY", "LLM_ENRICHMENT_MODEL"],
    "CANTON_ENABLED": ["CANTON_PAYEE_PARTY", "CANTON_FACILITATOR_URL"],
    "BILLING_ENABLED": ["BILLING_PACKAGE_ID", "CANTON_LEDGER_URL"],
}

# In Docker/K8s, these must be explicitly set
REQUIRED_IN_ISOLATED = ["CHROMA_PERSIST_DIR"]


def validate_startup_config() -> dict:
    """
    Validate critical configuration at startup.

    Returns a readiness state dict for use by the /ready endpoint.
    Raises SystemExit with an actionable message if config is fatally broken.
    """
    readiness = {
        "llm_model_valid": None,
        "llm_model_name": None,
        "chromadb_ready": None,
        "chromadb_doc_count": 0,
    }

    # --- Step 1: Env var cross-validation ---
    missing = []
    for flag, required_vars in REQUIRED_WHEN.items():
        if get_env_bool(flag, False):
            for var in required_vars:
                val = get_env(var, "")
                if not val:
                    missing.append(f"  {var} (required because {flag}=true)")

    is_isolated = get_env_bool("IS_ISOLATED_ENVIRONMENT", False)
    if is_isolated:
        for var in REQUIRED_IN_ISOLATED:
            val = get_env(var, "")
            if not val:
                missing.append(f"  {var} (required in Docker/K8s — IS_ISOLATED_ENVIRONMENT=true)")

    if missing:
        msg = "Missing required environment variables:\n" + "\n".join(missing)
        logger.critical(msg)
        raise SystemExit(msg)

    # --- Step 2: ChromaDB path check ---
    chroma_dir = get_env("CHROMA_PERSIST_DIR", "")
    if chroma_dir:
        chroma_path = Path(chroma_dir)
        if chroma_path.exists():
            sqlite_file = chroma_path / "chroma.sqlite3"
            if sqlite_file.exists():
                readiness["chromadb_ready"] = True
                logger.info(f"ChromaDB index found at {chroma_dir}")
            else:
                readiness["chromadb_ready"] = False
                msg = f"CHROMA_PERSIST_DIR={chroma_dir} exists but contains no chroma.sqlite3 — pre-built index missing"
                if is_isolated:
                    logger.critical(msg)
                    raise SystemExit(msg)
                else:
                    logger.warning(f"{msg} (will build on first request)")
        else:
            readiness["chromadb_ready"] = False
            msg = f"CHROMA_PERSIST_DIR={chroma_dir} does not exist"
            if is_isolated:
                logger.critical(msg)
                raise SystemExit(msg)
            else:
                logger.warning(f"{msg} (will create on first request)")

    # --- Step 3: LLM model ping ---
    llm_enabled = get_env_bool("ENABLE_LLM_ENRICHMENT", False) or get_env_bool("ENABLE_LLM_AUTH_EXTRACTION", False)
    if llm_enabled:
        api_key = get_env("ANTHROPIC_API_KEY", "")
        model = get_env("LLM_ENRICHMENT_MODEL", "")
        readiness["llm_model_name"] = model

        if api_key and model:
            try:
                from anthropic import Anthropic
                client = Anthropic(api_key=api_key, timeout=10.0)
                client.messages.create(
                    model=model,
                    max_tokens=1,
                    messages=[{"role": "user", "content": "ping"}],
                )
                readiness["llm_model_valid"] = True
                logger.info(f"LLM model verified: {model}")
            except Exception as e:
                error_str = str(e)
                readiness["llm_model_valid"] = False
                if "not_found" in error_str.lower() or "404" in error_str:
                    msg = f"LLM model '{model}' not found — check LLM_ENRICHMENT_MODEL env var. Anthropic error: {error_str[:200]}"
                elif "authentication" in error_str.lower() or "401" in error_str:
                    msg = f"ANTHROPIC_API_KEY is invalid — check the key. Error: {error_str[:200]}"
                else:
                    msg = f"LLM model ping failed: {type(e).__name__}: {error_str[:200]}"
                logger.critical(msg)
                raise SystemExit(msg)
    else:
        logger.info("LLM enrichment disabled — skipping model validation")

    logger.info(f"Startup validation passed: {readiness}")
    return readiness
