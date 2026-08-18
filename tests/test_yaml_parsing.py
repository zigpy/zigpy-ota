"""Tests for YAML metadata parsing."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from ruamel.yaml import YAML

from zigpy_ota.actions.metadata.yaml_parsing import (
    parse_metadata_file,
    parse_metadata_files,
)
from zigpy_ota.actions.pr.prepare_files import parse_optional_metadata
from zigpy_ota.models.yaml_metadata import (
    ThirdPartyDownload,
    YamlMetadataFile,
    YamlMetadataThirdParty,
)


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


@pytest.mark.parametrize(
    "yaml_string",
    [
        pytest.param(
            "model_names:[TEST]\nmanufacturer_names:[TEST]",
            id="list_no_space",
        ),
        pytest.param(
            "model_names:TEST\nmanufacturer_names:TEST",
            id="scalar_no_space",
        ),
    ],
)
def test_parse_optional_metadata_missing_space_after_colon(
    yaml_string: str,
) -> None:
    """Test that missing space after colon in optional metadata is handled."""
    result = parse_optional_metadata(yaml_string)

    assert result["model_names"] == ("TEST",)
    assert result["manufacturer_names"] == ("TEST",)


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


def test_vacuous_version_constraints_normalized() -> None:
    """min=0 / max=0xFFFFFFFF are dropped by the model (issue-form path)."""
    result = YamlMetadataFile(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
        source_url="https://example.com",
        min_current_file_version=0,
        max_current_file_version=0xFFFFFFFF,
    )

    assert result.min_current_file_version is None
    assert result.max_current_file_version is None
    # Dropped fields are not written to the generated YAML either
    assert "min_current_file_version" not in result.to_dict()
    assert "max_current_file_version" not in result.to_dict()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_current_file_version", 0),
        ("max_current_file_version", 0xFFFFFFFF),
    ],
)
def test_vacuous_version_constraints_rejected_in_yaml(
    tmp_path: Path, field: str, value: int
) -> None:
    """Committed YAML with vacuous constraints fails parsing."""
    yaml_path = tmp_path / "test.yaml"
    yaml_content = {
        "file_name": "test.zigbee",
        "source_file_name": "original.zigbee",
        "source_url": "https://example.com",
        field: value,
    }
    yaml_path.write_text(dump_yaml(yaml_content))

    with pytest.raises(ValueError, match="can never exclude a device"):
        parse_metadata_file(yaml_path)

    # Strict by default, skipped with --allow-invalid-yaml
    with pytest.raises(ValueError, match="can never exclude a device"):
        parse_metadata_files(
            tmp_path,
            fail_on_filename_mismatch=False,
            fail_on_missing_ota=False,
            fail_on_invalid_yaml=True,
        )
    result = parse_metadata_files(
        tmp_path,
        fail_on_filename_mismatch=False,
        fail_on_missing_ota=False,
        fail_on_invalid_yaml=False,
    )
    assert result == {}


def test_meaningful_version_constraints_kept(tmp_path: Path) -> None:
    """Non-vacuous version constraints are preserved unchanged."""
    yaml_path = tmp_path / "test.yaml"
    yaml_content = {
        "file_name": "test.zigbee",
        "source_file_name": "original.zigbee",
        "source_url": "https://example.com",
        "min_current_file_version": 1,
        "max_current_file_version": 0xFFFFFFFE,
    }
    yaml_path.write_text(dump_yaml(yaml_content))

    result = parse_metadata_file(yaml_path)

    assert result is not None
    assert result.min_current_file_version == 1
    assert result.max_current_file_version == 0xFFFFFFFE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_current_file_version", "100"),
        ("max_current_file_version", "0xFFFFFFFF"),
        ("min_hardware_version", "1"),
        ("specificity", True),
    ],
)
def test_non_integer_constraints_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    """Quoted numbers (and booleans) in numeric fields fail parsing loudly."""
    yaml_path = tmp_path / "test.yaml"
    yaml_content = {
        "file_name": "test.zigbee",
        "source_file_name": "original.zigbee",
        "source_url": "https://example.com",
        field: value,
    }
    yaml_path.write_text(dump_yaml(yaml_content))

    with pytest.raises(ValueError, match="must be an integer"):
        parse_metadata_file(yaml_path)


def test_non_integer_constraints_rejected_on_construction() -> None:
    """Booleans are rejected at model construction too."""
    with pytest.raises(TypeError, match="specificity must be an integer"):
        YamlMetadataFile(
            file_name="test.zigbee",
            source_file_name="original.zigbee",
            specificity=True,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("value", ["4107", True])
def test_third_party_non_integer_fields_rejected(value: object) -> None:
    """Quoted numbers/booleans in third_party_download numeric fields fail."""
    with pytest.raises(TypeError, match="manufacturer_id must be an integer"):
        ThirdPartyDownload(
            manufacturer_id=value,  # type: ignore[arg-type]
            image_type=268,
            file_version=16781568,
            file_size=123456,
            checksum_sha3_256="abc123",
            checksum_sha512="def456",
        )


def test_parse_optional_metadata_strictness() -> None:
    """Invalid issue-form metadata fails with submitter-facing messages."""
    # Malformed YAML no longer silently drops all constraints
    with pytest.raises(ValueError, match="Could not parse the optional metadata"):
        parse_optional_metadata("model_names: [unclosed")

    # Unknown channel fails clearly ('stable' worked while 'beta' crashed later)
    with pytest.raises(ValueError, match="channel must be one of"):
        parse_optional_metadata("channel: nightly")

    # Non-string name entries are rejected instead of serialized as-is
    with pytest.raises(ValueError, match="must be a name or a list of names"):
        parse_optional_metadata("model_names: 5")

    # Out-of-range values are rejected (uint32 for versions, uint16 for hw)
    with pytest.raises(ValueError, match="must be between 0 and"):
        parse_optional_metadata("min_current_file_version: -1")
    with pytest.raises(ValueError, match="must be between 0 and"):
        parse_optional_metadata("max_hardware_version: 0x10000")


def test_parse_optional_metadata_drops_empty_values() -> None:
    """A field left empty (stray trailing colon) is treated as absent.

    Previously 'min_current_file_version:' parsed as None and suppressed the
    auto-computed minimum via the key-presence check.
    """
    result = parse_optional_metadata("min_current_file_version:\nmodel_names: [a]")
    assert "min_current_file_version" not in result
    assert result["model_names"] == ("a",)


def test_parse_optional_metadata_channel_coerced_to_enum() -> None:
    """A valid channel becomes the Channel enum (not a bare string)."""
    from zigpy_ota.models.yaml_metadata import Channel

    result = parse_optional_metadata("channel: beta")
    assert result["channel"] is Channel.BETA


def test_parse_optional_metadata_more_strictness() -> None:
    """Shape errors, vacuous constraints, and non-bool disabled are rejected."""
    # A non-mapping root (e.g. a copied '-' bullet) no longer silently drops
    # all constraints
    with pytest.raises(ValueError, match="must be 'field: value' lines"):
        parse_optional_metadata("- model_names: [Hue Lamp]")

    # Vacuous constraints are rejected like in committed YAML (min=0 also
    # silently voided the auto-computed minimum)
    with pytest.raises(ValueError, match="can never exclude a device"):
        parse_optional_metadata("min_current_file_version: 0")
    with pytest.raises(ValueError, match="can never exclude a device"):
        parse_optional_metadata("max_current_file_version: 0xFFFFFFFF")

    # YAML 1.2 parses no/off as strings, and any non-empty string is truthy
    with pytest.raises(ValueError, match="disabled must be true or false"):
        parse_optional_metadata("disabled: no")
    with pytest.raises(ValueError, match="disabled must be true or false"):
        parse_optional_metadata('disabled: "false"')
    assert parse_optional_metadata("disabled: true") == {"disabled": True}

    # Empty names match no device while still boosting specificity
    with pytest.raises(ValueError, match="empty names"):
        parse_optional_metadata("model_names: []")
    with pytest.raises(ValueError, match="empty names"):
        parse_optional_metadata('model_names: [""]')


def test_yaml_file_non_bool_disabled_rejected(tmp_path: Path) -> None:
    """Committed YAML with a non-boolean disabled value fails parsing."""
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text(
        dump_yaml(
            {
                "file_name": "test.zigbee",
                "source_file_name": "original.zigbee",
                "disabled": "no",
            }
        )
    )

    with pytest.raises(ValueError, match="disabled must be true or false"):
        parse_metadata_file(yaml_path)


def test_parse_optional_metadata_empty_sentinels() -> None:
    """Common 'left empty on purpose' spellings mean no metadata, not a rejection."""
    assert parse_optional_metadata("none") == {}
    assert parse_optional_metadata("N/A") == {}
    assert parse_optional_metadata("# just a comment") == {}


def test_yaml_file_empty_names_rejected(tmp_path: Path) -> None:
    """Committed YAML with empty names fails parsing (parity with the issue form)."""
    yaml_path = tmp_path / "test.yaml"
    yaml_path.write_text(
        dump_yaml(
            {
                "file_name": "test.zigbee",
                "source_file_name": "original.zigbee",
                "model_names": [""],
            }
        )
    )

    with pytest.raises(ValueError, match="non-empty names"):
        parse_metadata_file(yaml_path)
