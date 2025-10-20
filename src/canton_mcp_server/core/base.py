"""
Base classes for the MCP server framework.

This module defines the fundamental abstractions:
- Tool: Abstract base class for all MCP tools
- ToolContext: Execution context provided to tools

All tools must inherit from Tool and implement the execute() method.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Generic, Optional, Type

from .context import ToolContext
from .pricing import ToolPricing
from .types import ToolResponse, TParams, TResult


class Tool(ABC, Generic[TParams, TResult]):
    """
    Abstract base class for all MCP tools.

    Subclasses must define:
    - name: str - Tool name for MCP protocol
    - description: str - Human-readable description
    - params_model: Type[TParams] - Pydantic model for input validation
    - pricing: ToolPricing - Pricing configuration
    - execute(ctx) - Main tool logic

    Example:
        ```python
        @register_tool
        class MyTool(Tool[MyParams, MyResult]):
            name = "my_tool"
            description = "Does something cool"
            params_model = MyParams
            result_model = MyResult
            pricing = ToolPricing(type=PricingType.FREE)

            async def execute(self, ctx: ToolContext[MyParams]):
                result = await self.do_work(ctx.params)
                yield ctx.success(result)
        ```
    """

    # Metadata (must be overridden by subclasses)
    name: str
    description: str
    params_model: Type[TParams]
    result_model: Optional[Type[TResult]] = None

    # Pricing configuration (optional, defaults to FREE)
    pricing: Optional["ToolPricing"] = None

    def __init__(self):
        """Initialize tool with default free pricing if not specified"""
        if self.pricing is None:
            from .pricing import PricingType, ToolPricing

            self.pricing = ToolPricing(type=PricingType.FREE)

    @abstractmethod
    async def execute(
        self,
        ctx: "ToolContext[TParams, TResult]",  # Forward reference
    ) -> AsyncGenerator[ToolResponse, None]:
        """
        Execute the tool logic.

        This is the main method that tools must implement. It receives a
        ToolContext with validated parameters and result type, and should
        yield ToolResponse objects.

        Args:
            ctx: Tool execution context with validated params, result type, and helpers

        Yields:
            ToolResponse objects with results or progress updates

        Example:
            ```python
            async def execute(self, ctx: ToolContext[MyParams, MyResult]):
                # Access validated params (typed!)
                name = ctx.params.strategy_name

                # Send progress
                yield ctx.progress(50, 100, "Working...")

                # Do work and create typed result
                result = MyResult(items=42, status="done")

                # Return typed result
                yield ctx.structured(result)
            ```
        """
        result_name = self.result_model.__name__ if self.result_model else "Any"
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement execute() method. "
            f"Expected signature: async def execute(self, ctx: ToolContext[{self.params_model.__name__}, {result_name}]) -> AsyncGenerator[ToolResponse, None]"
        )

    async def cancel_execution(self, ctx: "ToolContext[TParams, TResult]"):
        """
        Optional cleanup hook called when execution is cancelled.

        Tools can override this to perform cleanup when cancellation occurs:
        - Close database connections
        - Save partial state
        - Release resources
        - Log cancellation details

        This is called by the framework BEFORE returning the cancellation error.
        The default implementation does nothing.

        Args:
            ctx: Tool execution context (same as execute)

        Example:
            ```python
            async def cancel_execution(self, ctx):
                # Clean up resources
                await self.close_connections()

                # Log cancellation
                logger.info(f"Tool cancelled after {ctx.request.get_duration()}s")

                # Save partial results
                await self.save_state(ctx.params)
            ```
        """
        # Default: no cleanup needed
        pass

    def get_input_schema(self) -> dict:
        """
        Generate JSON schema for tool input parameters.

        Automatically generates schema from the Pydantic params_model.
        This is used for MCP tools/list response.

        Returns:
            JSON schema dict compatible with MCP protocol
        """
        return self.params_model.model_json_schema()

    def get_output_schema(self) -> Optional[dict]:
        """
        Generate JSON schema for tool output (if result_model defined).

        Returns inlined schema without $defs and $ref for MCP compliance.

        Returns:
            JSON schema dict or None if no result_model specified
        """
        if self.result_model and hasattr(self.result_model, "model_json_schema"):
            schema = self.result_model.model_json_schema()
            return self._inline_schema_refs(schema)
        return None

    @staticmethod
    def _inline_schema_refs(schema: dict) -> dict:
        """
        Inline all $ref references and remove $defs for MCP compliance.

        Pydantic generates schemas with $defs and $ref for nested models,
        but MCP spec prefers inlined schemas for better compatibility.

        Args:
            schema: JSON schema with potential $defs and $ref

        Returns:
            Inlined JSON schema without $defs or $ref
        """
        import copy

        schema = copy.deepcopy(schema)
        defs = schema.pop("$defs", {})

        def resolve_ref(obj: dict, defs: dict) -> dict:
            """Recursively resolve $ref references"""
            if isinstance(obj, dict):
                if "$ref" in obj:
                    # Extract reference path (e.g., "#/$defs/BacktestResult")
                    ref_path = obj["$ref"]
                    if ref_path.startswith("#/$defs/"):
                        def_name = ref_path.split("/")[-1]
                        if def_name in defs:
                            # Replace $ref with actual definition
                            resolved = copy.deepcopy(defs[def_name])
                            # Recursively resolve nested refs
                            return resolve_ref(resolved, defs)
                    return obj
                else:
                    # Recursively process nested objects
                    return {k: resolve_ref(v, defs) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [resolve_ref(item, defs) for item in obj]
            else:
                return obj

        return resolve_ref(schema, defs)

