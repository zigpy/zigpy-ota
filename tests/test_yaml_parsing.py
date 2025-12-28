"""Tests for YAML metadata parsing."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from zigpy_ota.actions.metadata.yaml_parsing import parse_metadata_file
from zigpy_ota.actions.pr.prepare_files import parse_optional_metadata
from zigpy_ota.models.yaml_metadata import ThirdPartyDownload, YamlMetadataThirdParty


def dump_yaml(data: dict[str, Any]) -> str:
    """Helper to dump dict to YAML string using ruamel.yaml."""
    yaml = YAML()
    stream = io.StringIO()
    yaml.dump(data, stream)
    return stream.getvalue()


def test_parse_metadata_file_normalizes_model_names_string_to_tuple(
    tmp_path: Path,
) -> None:
    """Test that model_names as a string is converted to a tuple."""
    yaml_path = tmp_path / "test.yaml"
    yaml_content = {
        "file_name": "test.zigbee",
        "source_file_name": "original.zigbee",
        "source_url": "https://example.com",
        "model_names": "single_model",
    }
    yaml_path.write_text(dump_yaml(yaml_content))

    result = parse_metadata_file(yaml_path)

    assert result is not None
    assert result.model_names is not None
    assert isinstance(result.model_names, tuple)
    assert result.model_names == ("single_model",)


def test_parse_metadata_file_normalizes_manufacturer_names_string_to_tuple(
    tmp_path: Path,
) -> None:
    """Test that manufacturer_names as a string is converted to a tuple."""
    yaml_path = tmp_path / "test.yaml"
    yaml_content = {
        "file_name": "test.zigbee",
        "source_file_name": "original.zigbee",
        "source_url": "https://example.com",
        "manufacturer_names": "ACME Corp",
    }
    yaml_path.write_text(dump_yaml(yaml_content))

    result = parse_metadata_file(yaml_path)

    assert result is not None
    assert result.manufacturer_names is not None
    assert isinstance(result.manufacturer_names, tuple)
    assert result.manufacturer_names == ("ACME Corp",)


def test_parse_metadata_file_converts_list_to_tuple(tmp_path: Path) -> None:
    """Test that model_names and manufacturer_names as lists are converted to tuples."""
    yaml_path = tmp_path / "test.yaml"
    yaml_content = {
        "file_name": "test.zigbee",
        "source_file_name": "original.zigbee",
        "source_url": "https://example.com",
        "model_names": ["model1", "model2"],
        "manufacturer_names": ["ACME Corp", "Widgets Inc"],
    }
    yaml_path.write_text(dump_yaml(yaml_content))

    result = parse_metadata_file(yaml_path)

    assert result is not None
    assert result.model_names == ("model1", "model2")
    assert result.manufacturer_names == ("ACME Corp", "Widgets Inc")


def test_parse_optional_metadata_normalizes_model_names_string_to_tuple() -> None:
    """Test that optional metadata model_names as a string is converted to a tuple."""
    yaml_string = """
model_names: single_model
min_hardware_version: 1
"""
    result = parse_optional_metadata(yaml_string)

    assert "model_names" in result
    assert isinstance(result["model_names"], tuple)
    assert result["model_names"] == ("single_model",)


def test_parse_optional_metadata_normalizes_manufacturer_names_string_to_tuple() -> (
    None
):
    """Test that optional metadata manufacturer_names as a string is converted to a tuple."""
    yaml_string = """
manufacturer_names: ACME Corp
min_hardware_version: 1
"""
    result = parse_optional_metadata(yaml_string)

    assert "manufacturer_names" in result
    assert isinstance(result["manufacturer_names"], tuple)
    assert result["manufacturer_names"] == ("ACME Corp",)


def test_parse_optional_metadata_converts_list_to_tuple() -> None:
    """Test that optional metadata lists are converted to tuples."""
    yaml_string = """
model_names: [model1, model2]
manufacturer_names: [ACME Corp, Widgets Inc]
"""
    result = parse_optional_metadata(yaml_string)

    assert result["model_names"] == ("model1", "model2")
    assert result["manufacturer_names"] == ("ACME Corp", "Widgets Inc")


def test_parse_optional_metadata_handles_mixed_types() -> None:
    """Test that optional metadata handles mix of strings and lists correctly."""
    yaml_string = """
model_names: single_model
manufacturer_names: [ACME Corp, Widgets Inc]
specificity: 5
"""
    result = parse_optional_metadata(yaml_string)

    assert result["model_names"] == ("single_model",)
    assert result["manufacturer_names"] == ("ACME Corp", "Widgets Inc")
    assert result["specificity"] == 5


def test_third_party_metadata_creation_success() -> None:
    """Test that YamlMetadataThirdParty can be created with all required fields."""
    third_party_download = ThirdPartyDownload(
        manufacturer_id=4107,
        image_type=268,
        file_version=16781568,
        file_size=123456,
        checksum_sha3_256="abc123",
        checksum_sha512="def456",
    )
    metadata = YamlMetadataThirdParty(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
        source_url="https://example.com/test.zigbee",
        third_party_download=third_party_download,
    )

    assert isinstance(metadata, YamlMetadataThirdParty)
    assert metadata.file_name == "test.zigbee"
    assert metadata.source_file_name == "original.zigbee"
    assert metadata.source_url == "https://example.com/test.zigbee"
    assert metadata.third_party_download.manufacturer_id == 4107
    assert metadata.third_party_download.image_type == 268
    assert metadata.third_party_download.file_version == 16781568
    assert metadata.third_party_download.file_size == 123456
    assert metadata.third_party_download.checksum_sha3_256 == "abc123"
    assert metadata.third_party_download.checksum_sha512 == "def456"


def test_third_party_from_dict_missing_source_url() -> None:
    """Test that creating YamlMetadataThirdParty fails when source_url is missing."""
    data = {
        "file_name": "test.zigbee",
        "source_file_name": "original.zigbee",
        "third_party_download": {
            "manufacturer_id": 4107,
            "image_type": 268,
            "file_version": 16781568,
            "file_size": 123456,
            "checksum_sha3_256": "abc123",
            "checksum_sha512": "def456",
        },
    }

    with pytest.raises(KeyError, match="source_url"):
        YamlMetadataThirdParty.from_dict(data)


def test_third_party_from_dict_missing_checksum() -> None:
    """Test that creating YamlMetadataThirdParty fails when checksum_sha3_256 is missing."""
    data = {
        "file_name": "test.zigbee",
        "source_file_name": "original.zigbee",
        "source_url": "https://example.com/test.zigbee",
        "third_party_download": {
            "manufacturer_id": 4107,
            "image_type": 268,
            "file_version": 16781568,
            "file_size": 123456,
        },
    }

    with pytest.raises(KeyError, match="checksum_sha3_256"):
        YamlMetadataThirdParty.from_dict(data)


def test_parse_optional_metadata_channel_field() -> None:
    """Test that channel field is parsed from optional metadata."""
    yaml_string = """
channel: beta
model_names: test_model
"""
    result = parse_optional_metadata(yaml_string)

    assert "channel" in result
    assert result["channel"] == "beta"


def test_parse_optional_metadata_channel_dev() -> None:
    """Test that channel: dev is parsed from optional metadata."""
    yaml_string = """
channel: dev
"""
    result = parse_optional_metadata(yaml_string)

    assert "channel" in result
    assert result["channel"] == "dev"


def test_parse_metadata_file_with_channel(tmp_path: Path) -> None:
    """Test that channel field is parsed from YAML metadata file."""
    yaml_path = tmp_path / "test.yaml"
    yaml_content = {
        "file_name": "test.zigbee",
        "source_file_name": "original.zigbee",
        "source_url": "https://example.com",
        "channel": "beta",
    }
    yaml_path.write_text(dump_yaml(yaml_content))

    result = parse_metadata_file(yaml_path)

    assert result is not None
    assert result.channel == "beta"
