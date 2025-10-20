"""
Pricing system for MCP tools.

This module provides flexible pricing configurations:
- FREE: No payment required
- FIXED: Same price every time
- DYNAMIC: Price varies based on parameters

Tools declare pricing configuration and the framework handles
verification and settlement automatically.
"""

from enum import Enum
from typing import Callable, Optional

from pydantic import BaseModel


class PricingType(str, Enum):
    """Pricing model types"""

    FREE = "free"
    FIXED = "fixed"
    DYNAMIC = "dynamic"


class ToolPricing(BaseModel):
    """
    Pricing configuration for a tool.

    Defines how much a tool costs to execute. The framework uses this
    to calculate payment requirements and verify payments.

    Examples:
        ```python
        # Free tool
        pricing = ToolPricing(type=PricingType.FREE)

        # Fixed price
        pricing = ToolPricing(
            type=PricingType.FIXED,
            base_price=0.25
        )

        # Dynamic pricing based on parameters
        pricing = ToolPricing(
            type=PricingType.DYNAMIC,
            base_price=0.10,
            calculator=lambda p: 0.10 + (p.end_date - p.start_date).days * 0.001,
            free_tier={"max_days": 7}
        )
        ```

    Attributes:
        type: Pricing model type (FREE, FIXED, DYNAMIC)
        base_price: Base price in USD (for FIXED and DYNAMIC)
        calculator: Optional function to calculate dynamic price
        free_tier: Optional free tier limits
    """

    type: PricingType
    base_price: float = 0.0
    calculator: Optional[Callable] = None
    free_tier: Optional[dict] = None

    class Config:
        arbitrary_types_allowed = True

    def calculate_price(self, params: BaseModel) -> float:
        """
        Calculate price for given parameters.

        Args:
            params: Validated tool parameters

        Returns:
            Price in USD
        """
        if self.type == PricingType.FREE:
            return 0.0

        elif self.type == PricingType.FIXED:
            return self.base_price

        elif self.type == PricingType.DYNAMIC:
            if self.calculator:
                try:
                    return self.calculator(params)
                except Exception as e:
                    # Fall back to base price if calculator fails
                    import logging

                    logging.getLogger(__name__).warning(
                        f"Price calculator failed: {e}, using base_price"
                    )
                    return self.base_price
            return self.base_price

        return 0.0

