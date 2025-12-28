"""Tests for hardware version override functionality.

Verifies that min_hardware_version and max_hardware_version provided in YAML
metadata override the values extracted from OTA binary files.
"""

from __future__ import annotations

from zigpy_ota.actions.metadata.ota_parsing import verify_third_party_metadata
from zigpy_ota.models.index_metadata import IndexMetadata
from zigpy_ota.models.ota_metadata import OtaMetadata
from zigpy_ota.models.yaml_metadata import (
    ThirdPartyDownload,
    YamlMetadataFile,
    YamlMetadataThirdParty,
)


def test_hardware_version_override_both_versions() -> None:
    """Test that YAML min/max_hardware_version overrides OTA binary values."""
    # OTA metadata with hardware versions from binary
    ota = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=16781568,
        file_size=123456,
        checksum_sha3_256="abc123",
        checksum_sha512="def456",
        min_hardware_version=1,  # From OTA binary
        max_hardware_version=10,  # From OTA binary
    )

    # YAML metadata with different hardware versions (should override)
    yaml = YamlMetadataFile(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
        min_hardware_version=5,  # Override value
        max_hardware_version=15,  # Override value
    )

    # Merge metadata
    result = IndexMetadata.from_ota_and_yaml(
        ota, yaml, "https://example.com/test.zigbee"
    )

    # Verify YAML values override OTA binary values
    assert result.min_hardware_version == 5, (
        "YAML min_hardware_version should override OTA binary value"
    )
    assert result.max_hardware_version == 15, (
        "YAML max_hardware_version should override OTA binary value"
    )


def test_hardware_version_override_only_min() -> None:
    """Test that YAML min_hardware_version overrides OTA, but max stays from OTA."""
    ota = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=16781568,
        file_size=123456,
        checksum_sha3_256="abc123",
        checksum_sha512="def456",
        min_hardware_version=1,
        max_hardware_version=10,
    )

    yaml = YamlMetadataFile(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
        min_hardware_version=5,  # Override only min
    )

    result = IndexMetadata.from_ota_and_yaml(
        ota, yaml, "https://example.com/test.zigbee"
    )

    assert result.min_hardware_version == 5, "YAML should override min_hardware_version"
    assert result.max_hardware_version == 10, "OTA max_hardware_version should be kept"


def test_hardware_version_override_only_max() -> None:
    """Test that YAML max_hardware_version overrides OTA, but min stays from OTA."""
    ota = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=16781568,
        file_size=123456,
        checksum_sha3_256="abc123",
        checksum_sha512="def456",
        min_hardware_version=1,
        max_hardware_version=10,
    )

    yaml = YamlMetadataFile(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
        max_hardware_version=15,  # Override only max
    )

    result = IndexMetadata.from_ota_and_yaml(
        ota, yaml, "https://example.com/test.zigbee"
    )

    assert result.min_hardware_version == 1, "OTA min_hardware_version should be kept"
    assert result.max_hardware_version == 15, (
        "YAML should override max_hardware_version"
    )


def test_hardware_version_no_override_uses_ota_values() -> None:
    """Test that when YAML doesn't specify hardware versions, OTA values are used."""
    ota = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=16781568,
        file_size=123456,
        checksum_sha3_256="abc123",
        checksum_sha512="def456",
        min_hardware_version=1,
        max_hardware_version=10,
    )

    yaml = YamlMetadataFile(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
        # No hardware versions specified
    )

    result = IndexMetadata.from_ota_and_yaml(
        ota, yaml, "https://example.com/test.zigbee"
    )

    assert result.min_hardware_version == 1, "Should use OTA min_hardware_version"
    assert result.max_hardware_version == 10, "Should use OTA max_hardware_version"


def test_hardware_version_ota_missing_yaml_provides() -> None:
    """Test that YAML can add hardware versions when OTA binary doesn't have them."""
    ota = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=16781568,
        file_size=123456,
        checksum_sha3_256="abc123",
        checksum_sha512="def456",
        # No hardware versions in OTA binary
    )

    yaml = YamlMetadataFile(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
        min_hardware_version=5,
        max_hardware_version=15,
    )

    result = IndexMetadata.from_ota_and_yaml(
        ota, yaml, "https://example.com/test.zigbee"
    )

    assert result.min_hardware_version == 5, (
        "YAML should provide min_hardware_version when OTA doesn't have it"
    )
    assert result.max_hardware_version == 15, (
        "YAML should provide max_hardware_version when OTA doesn't have it"
    )


def test_hardware_version_both_missing() -> None:
    """Test that when both OTA and YAML lack hardware versions, they remain None."""
    ota = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=16781568,
        file_size=123456,
        checksum_sha3_256="abc123",
        checksum_sha512="def456",
    )

    yaml = YamlMetadataFile(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
    )

    result = IndexMetadata.from_ota_and_yaml(
        ota, yaml, "https://example.com/test.zigbee"
    )

    assert result.min_hardware_version is None, (
        "min_hardware_version should be None when not in OTA or YAML"
    )
    assert result.max_hardware_version is None, (
        "max_hardware_version should be None when not in OTA or YAML"
    )


def test_hardware_version_override_zero_value() -> None:
    """Test that hardware version 0 in YAML is valid and overrides non-zero OTA value."""
    ota = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=16781568,
        file_size=123456,
        checksum_sha3_256="abc123",
        checksum_sha512="def456",
        min_hardware_version=1,
        max_hardware_version=10,
    )

    yaml = YamlMetadataFile(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
        min_hardware_version=0,  # Zero is a valid hardware version
    )

    result = IndexMetadata.from_ota_and_yaml(
        ota, yaml, "https://example.com/test.zigbee"
    )

    assert result.min_hardware_version == 0, (
        "YAML value of 0 should override OTA value (0 is valid)"
    )
    assert result.max_hardware_version == 10, "OTA max should be preserved"


def test_hardware_version_third_party_from_yaml() -> None:
    """Test that third-party downloads can specify hardware versions in YAML."""
    # Third-party YAML with hardware versions
    yaml = YamlMetadataThirdParty(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
        source_url="https://example.com/test.zigbee",
        third_party_download=ThirdPartyDownload(
            manufacturer_id=4107,
            image_type=268,
            file_version=16781568,
            file_size=123456,
            checksum_sha3_256="abc123",
            checksum_sha512="def456",
        ),
        min_hardware_version=5,
        max_hardware_version=15,
    )

    # Create OTA metadata from third-party YAML
    ota = OtaMetadata.from_third_party_yaml(yaml)

    # Merge to create index metadata
    result = IndexMetadata.from_ota_and_yaml(
        ota, yaml, "https://example.com/test.zigbee"
    )

    assert result.min_hardware_version == 5, (
        "Third-party download should use YAML hardware versions"
    )
    assert result.max_hardware_version == 15, (
        "Third-party download should use YAML hardware versions"
    )
    assert result.third_party_download is True, "Should be marked as third-party"


def test_third_party_validation_allows_hardware_version_override() -> None:
    """Test that third-party validation allows hardware version overrides.

    This verifies that YAML can override hardware versions for third-party
    downloads, just like it can for local OTA files.
    """
    from pathlib import Path

    # OTA binary has hardware versions 1 and 10
    ota_from_binary = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=16781568,
        file_size=123456,
        checksum_sha3_256="abc123",
        checksum_sha512="def456",
        min_hardware_version=1,  # From actual OTA file
        max_hardware_version=10,  # From actual OTA file
    )

    # YAML wants to override with different hardware versions
    yaml = YamlMetadataThirdParty(
        file_name="test.zigbee",
        source_file_name="original.zigbee",
        source_url="https://example.com/test.zigbee",
        third_party_download=ThirdPartyDownload(
            manufacturer_id=4107,
            image_type=268,
            file_version=16781568,
            file_size=123456,
            checksum_sha3_256="abc123",
            checksum_sha512="def456",
        ),
        min_hardware_version=5,  # Different from binary (override)
        max_hardware_version=15,  # Different from binary (override)
    )

    # Validation should succeed - hardware versions can be overridden
    verify_third_party_metadata(ota_from_binary, yaml, Path("test.yaml"))

    # Now verify the final merged metadata uses YAML values
    ota_from_yaml = OtaMetadata.from_third_party_yaml(yaml)
    result = IndexMetadata.from_ota_and_yaml(
        ota_from_yaml, yaml, "https://example.com/test.zigbee"
    )

    # YAML hardware versions should be used, not the ones from the binary
    assert result.min_hardware_version == 5, (
        "YAML should override binary hardware version for third-party"
    )
    assert result.max_hardware_version == 15, (
        "YAML should override binary hardware version for third-party"
    )
