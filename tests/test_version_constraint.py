"""Test for min_current_file_version auto-calculation logic.

Verifies that when SET_MIN_VERSION option is selected, the system correctly
sets min_current_file_version to the highest existing version that's still
lower than the new version being added.
"""

from __future__ import annotations

from unittest.mock import patch

from zigpy_ota.actions.pr.prepare_files import _check_and_delete_existing_images
from zigpy_ota.models.index_metadata import IndexMetadata
from zigpy_ota.models.issue_model import ExistingImagesHandling
from zigpy_ota.models.ota_metadata import OtaMetadata


def test_set_min_version_only_considers_lower_versions() -> None:
    """Test that SET_MIN_VERSION only uses versions lower than the new version.

    Scenario:
    - New image version: 0x01002500 (middle)
    - Existing images: 0x01001A02 (old), 0x01002602 (newest)
    - Expected: min_current_file_version = 0x01001A02 (not 0x01002602)

    This ensures we don't set min_current_file_version to a version higher
    than the new image, which would make no sense.
    """
    # Create mock metadata for existing images
    old_metadata = IndexMetadata(
        binary_url="https://example.com/old.zigbee",
        manufacturer_id=4107,
        image_type=268,
        file_version=0x01001A02,  # Old version
        file_size=100000,
        checksum_sha3_256="abc123",
        checksum_sha512="abc123def456",
        source_file_name="old.zigbee",
    )

    newest_metadata = IndexMetadata(
        binary_url="https://example.com/newest.zigbee",
        manufacturer_id=4107,
        image_type=268,
        file_version=0x01002602,  # Newest version (higher than new!)
        file_size=100000,
        checksum_sha3_256="def456",
        checksum_sha512="def456ghi789",
        source_file_name="newest.zigbee",
    )

    mock_existing_images = {
        "old.zigbee": old_metadata,
        "newest.zigbee": newest_metadata,
    }

    # OTA metadata for the new middle version
    new_ota_metadata = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=0x01002500,  # Middle version
        file_size=100000,
        checksum_sha3_256="new123",
        checksum_sha512="new123abc456",
    )

    with patch(
        "zigpy_ota.actions.pr.prepare_files.find_existing_images_with_same_type",
        return_value=mock_existing_images,
    ):
        images_to_delete, auto_min_version = _check_and_delete_existing_images(
            manufacturer_directory="signify",
            filename="middle.zigbee",
            existing_images_handling=ExistingImagesHandling.SET_MIN_VERSION,
            ota_metadata=new_ota_metadata,
        )

        # Should find both existing images
        assert len(images_to_delete) == 2
        assert "old.zigbee" in images_to_delete
        assert "newest.zigbee" in images_to_delete

        # Should set min version to old version (0x01001A02), NOT newest (0x01002602)
        assert auto_min_version == 0x01001A02, (
            f"Expected min_current_file_version to be 0x01001A02 (the highest version "
            f"below 0x01002500), but got 0x{auto_min_version:08X}"
        )


def test_set_min_version_with_all_higher_versions() -> None:
    """Test that SET_MIN_VERSION returns None when all existing versions are higher.

    Scenario:
    - New image version: 0x01001000 (oldest)
    - Existing images: 0x01001A02, 0x01002500, 0x01002602 (all higher)
    - Expected: min_current_file_version = None (no constraint needed)
    """
    existing_metadata = {
        "v1.zigbee": IndexMetadata(
            binary_url="https://example.com/v1.zigbee",
            manufacturer_id=4107,
            image_type=268,
            file_version=0x01001A02,
            file_size=100000,
            checksum_sha3_256="abc123",
            checksum_sha512="abc123def456",
            source_file_name="v1.zigbee",
        ),
        "v2.zigbee": IndexMetadata(
            binary_url="https://example.com/v2.zigbee",
            manufacturer_id=4107,
            image_type=268,
            file_version=0x01002500,
            file_size=100000,
            checksum_sha3_256="def456",
            checksum_sha512="def456ghi789",
            source_file_name="v2.zigbee",
        ),
        "v3.zigbee": IndexMetadata(
            binary_url="https://example.com/v3.zigbee",
            manufacturer_id=4107,
            image_type=268,
            file_version=0x01002602,
            file_size=100000,
            checksum_sha3_256="ghi789",
            checksum_sha512="ghi789jkl012",
            source_file_name="v3.zigbee",
        ),
    }

    # OTA metadata for the new oldest version
    new_ota_metadata = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=0x01001000,  # Oldest version
        file_size=100000,
        checksum_sha3_256="oldest123",
        checksum_sha512="oldest123abc456",
    )

    with patch(
        "zigpy_ota.actions.pr.prepare_files.find_existing_images_with_same_type",
        return_value=existing_metadata,
    ):
        images_to_delete, auto_min_version = _check_and_delete_existing_images(
            manufacturer_directory="signify",
            filename="oldest.zigbee",
            existing_images_handling=ExistingImagesHandling.SET_MIN_VERSION,
            ota_metadata=new_ota_metadata,
        )

        # Should find all existing images
        assert len(images_to_delete) == 3

        # Should NOT set min version since all existing versions are higher
        assert auto_min_version is None, (
            "Expected min_current_file_version to be None when all existing "
            f"versions are higher than the new version, but got 0x{auto_min_version:08X}"
        )


def test_set_min_version_with_all_lower_versions() -> None:
    """Test that SET_MIN_VERSION picks the highest when all are lower.

    Scenario:
    - New image version: 0x01003000 (newest)
    - Existing images: 0x01001A02, 0x01002500, 0x01002602 (all lower)
    - Expected: min_current_file_version = 0x01002602 (highest of all)
    """
    existing_metadata = {
        "v1.zigbee": IndexMetadata(
            binary_url="https://example.com/v1.zigbee",
            manufacturer_id=4107,
            image_type=268,
            file_version=0x01001A02,
            file_size=100000,
            checksum_sha3_256="abc123",
            checksum_sha512="abc123def456",
            source_file_name="v1.zigbee",
        ),
        "v2.zigbee": IndexMetadata(
            binary_url="https://example.com/v2.zigbee",
            manufacturer_id=4107,
            image_type=268,
            file_version=0x01002500,
            file_size=100000,
            checksum_sha3_256="def456",
            checksum_sha512="def456ghi789",
            source_file_name="v2.zigbee",
        ),
        "v3.zigbee": IndexMetadata(
            binary_url="https://example.com/v3.zigbee",
            manufacturer_id=4107,
            image_type=268,
            file_version=0x01002602,
            file_size=100000,
            checksum_sha3_256="ghi789",
            checksum_sha512="ghi789jkl012",
            source_file_name="v3.zigbee",
        ),
    }

    # OTA metadata for the new newest version
    new_ota_metadata = OtaMetadata(
        manufacturer_id=4107,
        image_type=268,
        file_version=0x01003000,  # Newest version
        file_size=100000,
        checksum_sha3_256="newest123",
        checksum_sha512="newest123abc456",
    )

    with patch(
        "zigpy_ota.actions.pr.prepare_files.find_existing_images_with_same_type",
        return_value=existing_metadata,
    ):
        images_to_delete, auto_min_version = _check_and_delete_existing_images(
            manufacturer_directory="signify",
            filename="newest.zigbee",
            existing_images_handling=ExistingImagesHandling.SET_MIN_VERSION,
            ota_metadata=new_ota_metadata,
        )

        # Should find all existing images
        assert len(images_to_delete) == 3

        # Should pick the highest existing version (0x01002602)
        assert auto_min_version == 0x01002602, (
            f"Expected min_current_file_version to be 0x01002602 (the highest "
            f"existing version), but got 0x{auto_min_version:08X}"
        )
