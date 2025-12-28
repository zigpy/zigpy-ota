"""Utility functions for processing OTA files in pull requests."""

from __future__ import annotations

import logging

from zigpy_ota.actions.metadata.merging import parse_metadata_complete
from zigpy_ota.const import (
    DEFAULT_GITHUB_REF,
    FALLBACK_MANUFACTURER_DIRECTORY,
    IMAGES_PATH,
)
from zigpy_ota.models.index_metadata import IndexMetadata
from zigpy_ota.models.issue_model import IssueData
from zigpy_ota.models.ota_metadata import OtaMetadata
from zigpy_ota.utils.manufacturers import MANUFACTURER_ID_MAPPING, slugify_manufacturer

LOGGER = logging.getLogger(__name__)


def extract_download_info(issue_data: IssueData) -> tuple[str, str, str]:
    """Extract download URL, filename, and source URL from issue data.

    Args:
        issue_data: Issue data containing OTA file information

    Returns:
        Tuple of (download_url, filename, source_url)

    Raises:
        ValueError: If no OTA file source is provided or filename cannot be determined
    """
    if issue_data.ota_file:
        download_url = issue_data.ota_file.url
        filename = issue_data.ota_file.filename
        source_url = issue_data.ota_file.url
    elif issue_data.ota_image_url:
        download_url = issue_data.ota_image_url
        # Extract filename from URL
        filename = download_url.split("/")[-1].split("?")[0]
        if not filename or "." not in filename:
            raise ValueError(f"Could not determine filename from URL: {download_url}")
        source_url = issue_data.ota_image_url
    else:
        raise ValueError(
            "No OTA file source provided. Issue data must contain either "
            "ota_file or ota_image_url."
        )

    return download_url, filename, source_url


def extract_manufacturer_from_ota(ota_metadata: OtaMetadata) -> str | None:
    """Extract manufacturer name from OTA metadata.

    Args:
        ota_metadata: OTA metadata containing manufacturer_id

    Returns:
        Slugified manufacturer name if found in mapping, None otherwise
    """
    if (manufacturer_id := ota_metadata.manufacturer_id) in MANUFACTURER_ID_MAPPING:
        manufacturer = slugify_manufacturer(MANUFACTURER_ID_MAPPING[manufacturer_id])
        LOGGER.info(
            f"Manufacturer from OTA metadata: {manufacturer} (ID: {manufacturer_id})"
        )
        return manufacturer

    LOGGER.warning(
        f"Unknown manufacturer ID {manufacturer_id} not in MANUFACTURER_ID_MAPPING"
    )
    return None


def determine_manufacturer(manufacturer_from_ota: str | None) -> str:
    """Determine the manufacturer directory to use with fallback.

    Args:
        manufacturer_from_ota: Manufacturer name extracted from OTA file, or None

    Returns:
        Manufacturer directory name (uses fallback if input is None)
    """
    if manufacturer_from_ota:
        return manufacturer_from_ota

    LOGGER.info(
        "No manufacturer found in OTA, falling back to '%s'",
        FALLBACK_MANUFACTURER_DIRECTORY,
    )
    return FALLBACK_MANUFACTURER_DIRECTORY


def find_existing_images_with_same_type(
    manufacturer_directory: str, manufacturer_id: int, image_type: int
) -> dict[str, IndexMetadata]:
    """Find existing OTA images with the same manufacturer ID and image type.

    Args:
        manufacturer_directory: Manufacturer directory name
        manufacturer_id: Manufacturer ID to match
        image_type: Image type to match

    Returns:
        Dict mapping filenames to IndexMetadata for images matching the criteria
    """
    target_dir = IMAGES_PATH / manufacturer_directory
    if not target_dir.exists():
        return {}

    try:
        # Use DEFAULT_GITHUB_REF, as the generated URLs won't be used here anyway
        # and don't fail on any validation when checking existing images
        all_metadata = parse_metadata_complete(
            target_dir,
            DEFAULT_GITHUB_REF,
            validate_third_party=False,
            fail_on_missing_yaml=False,
            fail_on_inconsistent_yaml=False,
            fail_on_filename_mismatch=False,
            fail_on_missing_ota=False,
            fail_on_invalid_yaml=False,
        )
    except Exception as e:
        LOGGER.warning(f"Failed to parse metadata for {manufacturer_directory}: {e}")
        return {}

    images_to_delete: dict[str, IndexMetadata] = {}

    # Find images with matching manufacturer_id and image_type
    for filename, metadata in all_metadata.items():
        # IndexMetadata guarantees manufacturer_id and image_type are ints
        # TODO: check if newer(?)
        if (
            metadata.manufacturer_id == manufacturer_id
            and metadata.image_type == image_type
        ):
            file_path = target_dir / filename
            if file_path.exists():
                images_to_delete[filename] = metadata

    return images_to_delete


def delete_images(
    manufacturer_directory: str, images_to_delete: dict[str, IndexMetadata]
) -> None:
    """Delete the specified OTA images and their corresponding YAML metadata files.

    Args:
        manufacturer_directory: The manufacturer directory name
        images_to_delete: Dict mapping filenames to their metadata for images to delete
    """
    if not images_to_delete:
        LOGGER.info("No existing images with same type found to delete")
        return

    target_dir = IMAGES_PATH / manufacturer_directory
    deleted_files = []

    for filename, metadata in images_to_delete.items():
        file_path = target_dir / filename
        if file_path.exists():
            LOGGER.info(
                f"Deleting existing image with same type: {filename} "
                f"(manufacturer_id={metadata.manufacturer_id}, image_type={metadata.image_type})"
            )
            file_path.unlink()
            deleted_files.append(filename)

            # Delete the corresponding YAML metadata file if it exists
            yaml_path = file_path.with_suffix(file_path.suffix + ".yaml")
            if yaml_path.exists():
                LOGGER.info(f"Deleting metadata file: {yaml_path.name}")
                yaml_path.unlink()

    if deleted_files:
        LOGGER.info(f"Deleted {len(deleted_files)} existing image(s): {deleted_files}")


def delete_existing_images_with_same_type(
    manufacturer_directory: str, manufacturer_id: int, image_type: int
) -> None:
    """Delete existing OTA images with the same manufacturer ID and image type.

    Finds and deletes all images matching the criteria, along with their
    corresponding YAML metadata files.

    Args:
        manufacturer_directory: Manufacturer directory name
        manufacturer_id: Manufacturer ID to match
        image_type: Image type to match
    """
    images_to_delete = find_existing_images_with_same_type(
        manufacturer_directory, manufacturer_id, image_type
    )
    delete_images(manufacturer_directory, images_to_delete)
