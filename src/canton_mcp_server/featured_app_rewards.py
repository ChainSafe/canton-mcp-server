"""
Featured App Activity Marker Emission

Creates FeaturedAppActivityMarker contracts on Canton ledger by exercising
the FeaturedAppRight_CreateActivityMarker choice. This is how featured apps
earn rewards — SV automation converts markers into AppRewardCoupons for CC minting.

Flow:
  1. At startup, query the ledger for the FeaturedAppRight contract (granted by DSO governance)
  2. After each billable tool call, exercise FeaturedAppRight_CreateActivityMarker
  3. SV automation handles marker → AppRewardCoupon → CC minting (automatic)

Non-blocking: marker creation never fails a tool call.
"""

import logging
import os
from typing import Optional

from canton_mcp_server.canton_billing import (
    CANTON_PROVIDER_PARTY,
    CANTON_USER_ID,
    _make_ledger_request,
    get_ledger_offset,
)

logger = logging.getLogger(__name__)

# Feature gate
FEATURED_APP_REWARDS_ENABLED = (
    os.getenv("FEATURED_APP_REWARDS_ENABLED", "false").lower() == "true"
)

# Cached FeaturedAppRight contract
_featured_app_right_cache: dict = {
    "contract_id": None,
    "template_id": None,
}


async def init_featured_app_right() -> bool:
    """
    Query the ledger for the FeaturedAppRight contract belonging to our provider party.
    Called at startup and on contract-not-found errors.

    Returns True if found, False otherwise.
    """
    if not CANTON_PROVIDER_PARTY:
        logger.warning("CANTON_PROVIDER_PARTY not set — cannot query FeaturedAppRight")
        return False

    try:
        offset = await get_ledger_offset()
        data = await _make_ledger_request(
            "POST",
            "/v2/state/active-contracts",
            {
                "filter": {
                    "filtersByParty": {
                        CANTON_PROVIDER_PARTY: {"cumulative": []},
                    },
                },
                "activeAtOffset": offset,
                "verbose": False,
            },
        )

        contracts = data if isinstance(data, list) else data.get("activeContracts", data.get("result", []))

        for c in contracts:
            # Canton JSON API v2 wraps contracts in contractEntry.JsActiveContract.createdEvent
            ce = c.get("contractEntry", {})
            ac = ce.get("JsActiveContract", {})
            event = ac.get("createdEvent", {}) or c.get("createdEvent", c)
            template_id = event.get("templateId", "")
            if "FeaturedAppRight" in template_id:
                contract_id = event.get("contractId", "")
                _featured_app_right_cache["contract_id"] = contract_id
                _featured_app_right_cache["template_id"] = template_id
                logger.info(
                    f"FeaturedAppRight contract found: {contract_id[:40]}... "
                    f"(template: {template_id})"
                )
                return True

        logger.warning(
            f"FeaturedAppRight not found for {CANTON_PROVIDER_PARTY}. "
            "Activity markers will not be emitted. "
            "Ensure the DSO has granted FeaturedAppRight to this party."
        )
        return False

    except Exception as e:
        logger.error(f"Failed to query FeaturedAppRight: {e}")
        return False


async def create_activity_marker(request_id: str) -> Optional[str]:
    """
    Exercise FeaturedAppRight_CreateActivityMarker to emit an activity marker.

    Args:
        request_id: Unique request ID (used for command deduplication)

    Returns:
        Contract ID of the created marker, or None on failure.
    """
    if not FEATURED_APP_REWARDS_ENABLED:
        return None

    contract_id = _featured_app_right_cache.get("contract_id")
    template_id = _featured_app_right_cache.get("template_id")

    if not contract_id or not template_id:
        return None

    try:
        data = await _make_ledger_request(
            "POST",
            "/v2/commands/submit-and-wait-for-transaction",
            {
                "commands": {
                    "userId": CANTON_USER_ID,
                    "commandId": f"activity-marker-{request_id}",
                    "actAs": [CANTON_PROVIDER_PARTY],
                    "readAs": [CANTON_PROVIDER_PARTY],
                    "commands": [
                        {
                            "ExerciseCommand": {
                                "templateId": template_id,
                                "contractId": contract_id,
                                "choice": "FeaturedAppRight_CreateActivityMarker",
                                "choiceArgument": {
                                    "beneficiaries": [
                                        {
                                            "beneficiary": CANTON_PROVIDER_PARTY,
                                            "weight": "1.0",
                                        }
                                    ],
                                },
                            }
                        }
                    ],
                }
            },
        )

        # Extract marker contract IDs from the exercise result
        events = data.get("transaction", {}).get("events", [])
        marker_cids = []
        for event in events:
            created = event.get("CreatedEvent") or event.get("createdEvent", {})
            if created.get("contractId") and "ActivityMarker" in created.get("templateId", ""):
                marker_cids.append(created["contractId"])

        if marker_cids:
            logger.info(f"ActivityMarker created: {marker_cids[0][:40]}...")
            return marker_cids[0]

        # Even without recognizing the marker template, success means it worked
        logger.info(f"FeaturedAppRight_CreateActivityMarker exercised for request {request_id}")
        return "exercised"

    except Exception as e:
        error_str = str(e)

        # Contract archived / not found — re-query and retry once
        if "CONTRACT_NOT_FOUND" in error_str or "not found" in error_str.lower():
            logger.warning("FeaturedAppRight contract may have been archived, re-querying...")
            found = await init_featured_app_right()
            if found:
                try:
                    return await create_activity_marker(f"{request_id}-retry")
                except Exception as retry_err:
                    logger.warning(f"ActivityMarker retry failed: {retry_err}")
            return None

        # Auth / permission errors — don't retry
        if "403" in error_str or "PERMISSION_DENIED" in error_str:
            logger.warning(f"ActivityMarker permission denied (FeaturedAppRight may have been revoked): {e}")
            return None

        logger.warning(f"ActivityMarker creation failed (non-fatal): {e}")
        return None
