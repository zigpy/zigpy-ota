"""Common test utilities and helper functions."""

from __future__ import annotations

from typing import Any

import jsonschema
import pytest
from zigpy.ota.json_schemas import REMOTE_PROVIDER_SCHEMA


def validate_ota_index_schema(ota_index_data: dict[str, Any]) -> None:
    """Validate OTA index data against zigpy's REMOTE_PROVIDER_SCHEMA."""
    try:
        jsonschema.validate(instance=ota_index_data, schema=REMOTE_PROVIDER_SCHEMA)
    except jsonschema.ValidationError as e:
        pytest.fail(
            f"OTA index JSON does not match REMOTE_PROVIDER_SCHEMA: {e.message}\nPath: {list(e.path)}"
        )
