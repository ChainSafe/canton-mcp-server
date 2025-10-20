"""
Utility functions for the MCP server
"""

import re
from typing import Any

# =============================================================================
# Case Conversion Utilities
# =============================================================================


def snake_to_camel(snake_str: str) -> str:
    """Convert snake_case to camelCase

    Args:
        snake_str: String in snake_case format

    Returns:
        String in camelCase format
    """
    # Handle special cases like _meta (preserve leading underscore)
    if snake_str.startswith("_"):
        return "_" + snake_to_camel(snake_str[1:])

    # Split by underscore and capitalize all parts except the first
    components = snake_str.split("_")
    return components[0] + "".join(word.capitalize() for word in components[1:])


def camel_to_snake(camel_str: str) -> str:
    """Convert camelCase to snake_case

    Args:
        camel_str: String in camelCase format

    Returns:
        String in snake_case format
    """
    # Handle special cases like _meta (preserve leading underscore)
    if camel_str.startswith("_"):
        return "_" + camel_to_snake(camel_str[1:])

    # Insert underscore before uppercase letters and convert to lowercase
    snake_str = re.sub(r"(?<!^)(?=[A-Z])", "_", camel_str).lower()
    return snake_str


def convert_keys_to_camel_case(obj: Any, exclude_null: bool = True) -> Any:
    """Recursively convert all dictionary keys from snake_case to camelCase

    Args:
        obj: Object to convert (dict, list, or primitive)
        exclude_null: If True, exclude keys with None/null values

    Returns:
        Object with camelCase keys and optionally filtered null values
    """
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            # Skip null/None values if exclude_null is True
            if exclude_null and value is None:
                continue
            result[snake_to_camel(key)] = convert_keys_to_camel_case(
                value, exclude_null
            )
        return result
    elif isinstance(obj, list):
        return [convert_keys_to_camel_case(item, exclude_null) for item in obj]
    else:
        return obj


def convert_keys_to_snake_case(
    obj: Any, exclude_paths: list[str] | None = None, _current_path: str = ""
) -> Any:
    """Recursively convert all dictionary keys from camelCase to snake_case

    Args:
        obj: Object to convert (dict, list, or primitive)
        exclude_paths: List of dot-notation paths to exclude from conversion
                      (e.g., ["params.arguments.signed_payload"])
        _current_path: Internal parameter for tracking recursion path

    Returns:
        Object with snake_case keys, except for excluded paths
    """
    if exclude_paths is None:
        exclude_paths = []

    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            snake_key = camel_to_snake(key)
            new_path = f"{_current_path}.{snake_key}" if _current_path else snake_key

            # Check if this path should be excluded from conversion
            if new_path in exclude_paths:
                # Keep original value without recursing (preserves internal structure)
                result[snake_key] = value
            else:
                # Recurse with conversion
                result[snake_key] = convert_keys_to_snake_case(
                    value, exclude_paths, new_path
                )
        return result
    elif isinstance(obj, list):
        return [
            convert_keys_to_snake_case(item, exclude_paths, _current_path)
            for item in obj
        ]
    else:
        return obj

