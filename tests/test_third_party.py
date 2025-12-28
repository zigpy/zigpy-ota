"""Tests for third-party download feature."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from zigpy_ota.actions.issue.issue_parsing import parse_issue_file_to_model
from zigpy_ota.actions.metadata.merging import merge_metadata
from zigpy_ota.actions.metadata.ota_parsing import parse_third_party_yaml_to_ota
from zigpy_ota.models.ota_metadata import OtaMetadata
from zigpy_ota.models.yaml_metadata import (
    ThirdPartyDownload,
    YamlMetadataFile,
    YamlMetadataThirdParty,
)


def test_parse_issue_with_third_party_flag() -> None:
    """Test that issue parsing correctly extracts third_party_download flag."""
    issue_path = Path("tests/data/gh_issues/issue_hue_third_party.md")
    issue_data = parse_issue_file_to_model(issue_path)

    assert issue_data.third_party_download is True
    assert issue_data.manufacturer_name == "Hue"
    assert issue_data.ota_image_url is not None
    assert "otau.meethue.com" in issue_data.ota_image_url


def test_parse_issue_without_third_party_flag() -> None:
    """Test that third_party_download defaults to False when not checked."""
    issue_path = Path("tests/data/gh_issues/issue_hue_old.md")
    issue_data = parse_issue_file_to_model(issue_path)

    assert issue_data.third_party_download is False


def test_parse_third_party_yaml_without_validation(tmp_path: Path) -> None:
    """Test parsing third-party YAML without downloading/validating."""
    # Create a mock third-party YAML with checksum and file_size
    yaml_content = """# OTA metadata for test.zigbee
file_name: test.zigbee
source_file_name: original.zigbee
source_url: https://example.com/test.zigbee
third_party_download:
  manufacturer_id: 4107
  image_type: 268
  file_version: 16781568
  file_size: 123456
  checksum_sha3_256: 1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef
  checksum_sha512: 0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000dead
release_notes: |
  - Test release
"""
    yaml_file = tmp_path / "test.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    # Parse without validation
    metadata = parse_third_party_yaml_to_ota(yaml_file, validate=False)

    assert metadata is not None
    assert metadata.manufacturer_id == 4107
    assert metadata.image_type == 268
    assert metadata.file_version == 16781568
    # Without validation, use values from YAML
    assert (
        metadata.checksum_sha3_256
        == "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    )
    assert (
        metadata.checksum_sha512
        == "0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000dead"
    )
    assert metadata.file_size == 123456


def test_parse_third_party_yaml_missing_checksum_raises_error(tmp_path: Path) -> None:
    """Test that parsing third-party YAML without checksum/file_size raises ValueError."""
    # Create a YAML without checksum and file_size (invalid format)
    yaml_content = """# OTA metadata for test.zigbee
file_name: test.zigbee
source_file_name: original.zigbee
source_url: https://example.com/test.zigbee
third_party_download:
  manufacturer_id: 4107
  image_type: 268
  file_version: 16781568
release_notes: |
  - Test release
"""
    yaml_file = tmp_path / "test.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    # Parse without validation - should raise ValueError for missing required fields
    with pytest.raises(ValueError, match="Missing required fields"):
        parse_third_party_yaml_to_ota(yaml_file, validate=False)


def test_parse_third_party_yaml_with_validation(tmp_path: Path) -> None:
    """Test parsing third-party YAML with download and validation (mocked download)."""
    # Use real OTA file from test data
    ota_file = Path(
        "tests/data/ota_files/fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee"
    )
    ota_data = ota_file.read_bytes()

    yaml_content = """# OTA metadata for test.zigbee
file_name: fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee
source_file_name: fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee
source_url: https://example.com/firmware/fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee
third_party_download:
  manufacturer_id: 4107
  image_type: 268
  file_version: 16786688
  file_size: 126
  checksum_sha3_256: 7104c0da6f0dd13cb212484e46f472216afcbf31f7e3ed40f51c68fc8978e890
  checksum_sha512: 3563f9adbeaa4130252e39b741a7ff37e8e4aebd6e1d4886e2ed97f28f1c4686206782ab02246595313863639f583d9446ca63ad0af699850e1201e2db6dcd83
"""
    yaml_file = tmp_path / "test.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    # Mock the download_ota_file function to return the real OTA file content
    with patch(
        "zigpy_ota.actions.metadata.ota_parsing.download_ota_file"
    ) as mock_download:
        mock_download.return_value = ota_data

        # Parse WITH validation - checksum and size will be calculated from real file
        metadata = parse_third_party_yaml_to_ota(yaml_file, validate=True)

    assert metadata is not None
    assert metadata.manufacturer_id == 4107
    assert metadata.image_type == 268
    assert metadata.file_version == 16786688
    assert (
        metadata.checksum_sha3_256
        == "7104c0da6f0dd13cb212484e46f472216afcbf31f7e3ed40f51c68fc8978e890"
    )
    assert (
        metadata.checksum_sha512
        == "3563f9adbeaa4130252e39b741a7ff37e8e4aebd6e1d4886e2ed97f28f1c4686206782ab02246595313863639f583d9446ca63ad0af699850e1201e2db6dcd83"
    )
    assert metadata.file_size == 126


def test_parse_third_party_yaml_validation_checksum_mismatch(tmp_path: Path) -> None:
    """Test that validation fails when checksum doesn't match (mocked download)."""
    # Use real OTA file from test data
    ota_file = Path(
        "tests/data/ota_files/fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee"
    )
    ota_data = ota_file.read_bytes()

    # Create a YAML with INCORRECT checksum (different from actual file)
    yaml_content = """# OTA metadata for test.zigbee
file_name: fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee
source_file_name: fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee
source_url: https://example.com/firmware/fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee
third_party_download:
  manufacturer_id: 4107
  image_type: 268
  file_version: 16781568
  file_size: 267324
  checksum_sha3_256: 0000000000000000000000000000000000000000000000000000000000000000
  checksum_sha512: 0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000dead
"""
    yaml_file = tmp_path / "test.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    # Mock the download_ota_file function to return the real OTA file content
    with patch(
        "zigpy_ota.actions.metadata.ota_parsing.download_ota_file"
    ) as mock_download:
        mock_download.return_value = ota_data

        # Validation should fail - real checksum won't match the incorrect one in YAML
        with pytest.raises(ValueError, match="Checksum SHA3-256 mismatch"):
            parse_third_party_yaml_to_ota(yaml_file, validate=True)


def test_parse_third_party_yaml_validation_file_size_mismatch(tmp_path: Path) -> None:
    """Test that validation fails when file size doesn't match (mocked download)."""
    # Use real OTA file from test data
    ota_file = Path(
        "tests/data/ota_files/fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee"
    )
    ota_data = ota_file.read_bytes()

    # Create a YAML with INCORRECT file size (but correct checksum)
    # Real file is 126 bytes, but YAML says 12345
    yaml_content = """# OTA metadata for test.zigbee
file_name: fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee
source_file_name: fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee
source_url: https://example.com/firmware/fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee
third_party_download:
  manufacturer_id: 4107
  image_type: 268
  file_version: 16781568
  file_size: 12345
  checksum_sha3_256: 7104c0da6f0dd13cb212484e46f472216afcbf31f7e3ed40f51c68fc8978e890
  checksum_sha512: 3563f9adbeaa4130252e39b741a7ff37e8e4aebd6e1d4886e2ed97f28f1c4686206782ab02246595313863639f583d9446ca63ad0af699850e1201e2db6dcd83
"""
    yaml_file = tmp_path / "test.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    # Mock the download_ota_file function to return the real OTA file content
    with patch(
        "zigpy_ota.actions.metadata.ota_parsing.download_ota_file"
    ) as mock_download:
        mock_download.return_value = ota_data

        # Validation should fail - real file size (126) won't match YAML (12345)
        with pytest.raises(ValueError, match="File size mismatch"):
            parse_third_party_yaml_to_ota(yaml_file, validate=True)


def test_merge_metadata_inconsistency_strict_mode() -> None:
    """Test that merge_metadata raises error when third-party YAML exists but local OTA file also present."""
    # Create a third-party YAML metadata
    yaml_metadata: dict[str, YamlMetadataFile | YamlMetadataThirdParty] = {
        "signify/test.zigbee": YamlMetadataThirdParty(
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
            release_notes="Test release",
        )
    }

    # Create OTA metadata from a local file (is_from_third_party_yaml=False)
    # This represents the inconsistent state: YAML says third-party but local file exists
    ota_metadata = {
        "signify/test.zigbee": OtaMetadata(
            manufacturer_id=4107,
            image_type=268,
            file_version=16781568,
            file_size=123456,
            checksum_sha3_256="abc123",
            checksum_sha512="def456",
            is_from_third_party_yaml=False,  # Local file exists!
        )
    }

    # With fail_on_inconsistent_yaml=True (strict mode, default), should raise ValueError
    with pytest.raises(
        ValueError, match="Repository inconsistency detected for 1 OTA file"
    ):
        merge_metadata(
            yaml_metadata,
            ota_metadata,
            github_ref="main",
            fail_on_missing_yaml=False,
            fail_on_inconsistent_yaml=True,  # Strict mode
        )


def test_merge_metadata_inconsistency_non_strict_mode(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that merge_metadata logs warning but continues when inconsistency detected in non-strict mode."""
    # Create a third-party YAML metadata
    yaml_metadata: dict[str, YamlMetadataFile | YamlMetadataThirdParty] = {
        "signify/test.zigbee": YamlMetadataThirdParty(
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
            release_notes="Test release",
        )
    }

    # Create OTA metadata from a local file (is_from_third_party_yaml=False)
    ota_metadata = {
        "signify/test.zigbee": OtaMetadata(
            manufacturer_id=4107,
            image_type=268,
            file_version=16781568,
            file_size=123456,
            checksum_sha3_256="abc123",
            checksum_sha512="def456",
            is_from_third_party_yaml=False,  # Local file exists!
        )
    }

    # With fail_on_inconsistent_yaml=False, should log warning but continue
    result = merge_metadata(
        yaml_metadata,
        ota_metadata,
        github_ref="main",
        fail_on_missing_yaml=False,
        fail_on_inconsistent_yaml=False,
    )

    # Should have created the merged metadata (treating as regular file)
    assert len(result) == 1
    assert "signify/test.zigbee" in result

    # Should use GitHub URL instead of third-party URL for inconsistent state
    index_meta = result["signify/test.zigbee"]
    assert "raw.githubusercontent.com" in index_meta.binary_url
    assert "example.com" not in index_meta.binary_url

    # Should have logged a warning
    assert "Inconsistency detected" in caplog.text
    assert "signify/test.zigbee" in caplog.text
    assert "Third-party downloads should not have local OTA files" in caplog.text
