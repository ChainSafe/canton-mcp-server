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
    """Iteratively convert all dictionary keys from snake_case to camelCase

    Args:
        obj: Object to convert (dict, list, or primitive)
        exclude_null: If True, exclude keys with None/null values

    Returns:
        Object with camelCase keys and optionally filtered null values
    """
    # Use an explicit stack to avoid deep recursion in async contexts
    # Each stack entry is (source, target_container, key_or_index)
    # We process the root and build the result iteratively.
    if not isinstance(obj, (dict, list)):
        return obj

    # Sentinel to identify unprocessed values
    _UNSET = object()

    # We'll use a work stack: each item is (value_to_process, parent, key)
    # After processing, we set parent[key] = converted_value
    root: Any = _UNSET
    # Stack items: (value, parent_ref, key_in_parent)
    stack: list[tuple[Any, Any, Any]] = [(obj, None, None)]

    while stack:
        current, parent, key = stack.pop()

        if isinstance(current, dict):
            result = {}
            # Place result in parent immediately so children can reference it
            if parent is None:
                root = result
            else:
                parent[key] = result
            for k, v in current.items():
                if exclude_null and v is None:
                    continue
                camel_key = snake_to_camel(k)
                if isinstance(v, (dict, list)):
                    stack.append((v, result, camel_key))
                else:
                    result[camel_key] = v
        elif isinstance(current, list):
            result_list: list[Any] = [None] * len(current)
            if parent is None:
                root = result_list
            else:
                parent[key] = result_list
            for i, item in enumerate(current):
                if isinstance(item, (dict, list)):
                    stack.append((item, result_list, i))
                else:
                    result_list[i] = item
        else:
            if parent is None:
                root = current
            else:
                parent[key] = current

    return root


def convert_keys_to_snake_case(
    obj: Any, exclude_paths: list[str] | None = None, _current_path: str = ""
) -> Any:
    """Iteratively convert all dictionary keys from camelCase to snake_case

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

    if not isinstance(obj, (dict, list)):
        return obj

    exclude_set = set(exclude_paths)

    root: Any = None
    # Stack items: (value, parent_ref, key_in_parent, current_path)
    stack: list[tuple[Any, Any, Any, str]] = [(obj, None, None, _current_path)]

    while stack:
        current, parent, key, path = stack.pop()

        if isinstance(current, dict):
            result = {}
            if parent is None:
                root = result
            else:
                parent[key] = result
            for k, v in current.items():
                snake_key = camel_to_snake(k)
                new_path = f"{path}.{snake_key}" if path else snake_key

                if new_path in exclude_set:
                    # Keep original value without recursing
                    result[snake_key] = v
                elif isinstance(v, (dict, list)):
                    stack.append((v, result, snake_key, new_path))
                else:
                    result[snake_key] = v
        elif isinstance(current, list):
            result_list: list[Any] = [None] * len(current)
            if parent is None:
                root = result_list
            else:
                parent[key] = result_list
            for i, item in enumerate(current):
                if isinstance(item, (dict, list)):
                    stack.append((item, result_list, i, path))
                else:
                    result_list[i] = item
        else:
            if parent is None:
                root = current
            else:
                parent[key] = current

    return root
