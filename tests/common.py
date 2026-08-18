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


# Mirrors zigbee-herdsman's ZigbeeOtaImageMeta interface (src/controller/tstype.ts),
# the authoritative shape for z2m index entries. additionalProperties is False so
# a renamed or unexpected key in our z2m output fails loudly instead of being
# silently ignored by zigbee-herdsman.
Z2M_INDEX_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "fileName": {"type": "string"},
            "fileVersion": {"type": "integer"},
            "fileSize": {"type": "integer"},
            "url": {"type": "string"},
            "imageType": {"type": "integer"},
            "manufacturerCode": {"type": "integer"},
            "sha512": {"type": "string"},
            "otaHeaderString": {"type": "string"},
            "force": {"type": "boolean"},
            "hardwareVersionMin": {"type": "integer"},
            "hardwareVersionMax": {"type": "integer"},
            "modelId": {"type": "string"},
            "manufacturerName": {"type": "array", "items": {"type": "string"}},
            "minFileVersion": {"type": "integer"},
            "maxFileVersion": {"type": "integer"},
            "originalUrl": {"type": "string"},
            "releaseNotes": {"type": "string"},
        },
        # Fields our z2m output always emits (herdsman itself requires fewer)
        "required": [
            "fileName",
            "fileVersion",
            "fileSize",
            "url",
            "imageType",
            "manufacturerCode",
            "sha512",
            "otaHeaderString",
        ],
        "additionalProperties": False,
    },
}


def validate_z2m_index_schema(z2m_index_data: list[Any]) -> None:
    """Validate z2m index data against zigbee-herdsman's index entry shape."""
    try:
        jsonschema.validate(instance=z2m_index_data, schema=Z2M_INDEX_SCHEMA)
    except jsonschema.ValidationError as e:
        pytest.fail(
            f"z2m index JSON does not match ZigbeeOtaImageMeta shape: {e.message}\nPath: {list(e.path)}"
        )
