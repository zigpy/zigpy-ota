"""YAML utility functions for custom serialization and metadata normalization."""

from __future__ import annotations

from typing import Any

from ruamel.yaml import YAML


def create_yaml_instance() -> YAML:
    """Create a configured ruamel.yaml YAML instance.

    Returns:
        Configured YAML instance with proper indentation and string formatting.
    """
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.preserve_quotes = False
    yaml.width = 4096  # Prevent line wrapping of long strings
    yaml.indent(mapping=2, sequence=4, offset=2)

    # Use double quotes instead of single quotes when quoting is needed
    original_choose = yaml.Emitter.choose_scalar_style

    def choose_scalar_style_double(self: Any) -> Any:
        style = original_choose(self)
        return '"' if style == "'" else style

    yaml.Emitter.choose_scalar_style = choose_scalar_style_double

    return yaml


def normalize_yaml_values(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize ruamel.yaml special types to standard Python types.

    This converts HexInt, OctalInt, etc. to regular int values.

    Args:
        data: Dictionary with potentially ruamel.yaml special types

    Returns:
        Dictionary with normalized Python types
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, bool):
            # Keep booleans as booleans (bool is an int subclass): coercing
            # turned `disabled: true` into 1 and let a boolean in a numeric
            # field slip past the integer validation as 1/0
            result[key] = value
        elif isinstance(value, int):
            # Convert any int subclass (HexInt, OctalInt, etc.) to plain int
            result[key] = int(value)
        elif isinstance(value, dict):
            result[key] = normalize_yaml_values(value)
        elif isinstance(value, list):
            result[key] = [
                normalize_yaml_values(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def normalize_metadata_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize metadata fields in given dict when parsing from YAML.

    - Converts model_names and manufacturer_names from string/list to tuple
    - Converts release_notes from list to markdown-style string with dashes
    """
    # Convert single strings or lists to tuples
    for field in ("model_names", "manufacturer_names"):
        if field in data:
            if isinstance(data[field], str):
                data[field] = (data[field],)
            elif isinstance(data[field], list):
                data[field] = tuple(data[field])

    # Convert release_notes list to string
    if "release_notes" in data and isinstance(data["release_notes"], list):
        data["release_notes"] = "\n".join(f"- {item}" for item in data["release_notes"])

    return data
