"""Prepare changes for creating a GitHub PR for OTA submission."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML, YAMLError

from zigpy_ota.actions.metadata.name_utils import generate_ota_filename
from zigpy_ota.actions.metadata.ota_parsing import parse_and_validate_ota_bytes
from zigpy_ota.actions.metadata.yaml_metadata_generation import (
    generate_metadata_for_image,
)
from zigpy_ota.actions.metadata.yaml_parsing import parse_metadata_file
from zigpy_ota.actions.pr.const import SUPPORTED_OPTIONAL_METADATA_FIELDS
from zigpy_ota.actions.pr.download_utils import (
    IMAGES_PATH,
    download_ota_file,
    extract_ota_from_zip,
    save_ota_file,
)
from zigpy_ota.actions.pr.pr_utils import (
    delete_images,
    determine_manufacturer,
    extract_download_info,
    extract_manufacturer_from_ota,
    find_existing_images_with_same_type,
)
from zigpy_ota.models.index_metadata import IndexMetadata
from zigpy_ota.models.issue_model import ExistingImagesHandling, IssueData
from zigpy_ota.models.ota_metadata import OtaMetadata
from zigpy_ota.models.pr_result import PrepareResult
from zigpy_ota.models.yaml_metadata import (
    BaseYamlMetadata,
    ThirdPartyDownload,
    YamlMetadataFile,
    YamlMetadataThirdParty,
)
from zigpy_ota.utils.yaml_utils import normalize_metadata_fields, normalize_yaml_values

LOGGER = logging.getLogger(__name__)


def parse_optional_metadata(optional_metadata_yaml: str | None) -> dict[str, Any]:
    """Parse optional metadata from YAML string.

    Filters out unsupported fields and normalizes model_names and manufacturer_names
    to lists.

    Args:
        optional_metadata_yaml: YAML string containing optional metadata, or None

    Returns:
        Dictionary of parsed and filtered metadata, empty dict if parsing fails
    """
    if not optional_metadata_yaml or not optional_metadata_yaml.strip():
        return {}

    # Fix missing space after colon (e.g. "model_names:[TEST]" -> "model_names: [TEST]")
    optional_metadata_yaml = re.sub(
        r"^(\w+):(\S)", r"\1: \2", optional_metadata_yaml, flags=re.MULTILINE
    )

    try:
        yaml = YAML()
        parsed = yaml.load(optional_metadata_yaml)
        if not isinstance(parsed, dict):
            LOGGER.warning(
                f"Optional metadata is not a dictionary, ignoring: {type(parsed)}"
            )
            return {}

        # Convert CommentedMap to regular dict and normalize special YAML types
        parsed = normalize_yaml_values(dict(parsed))

        # Check for unsupported fields
        unsupported_fields = set(parsed.keys()) - SUPPORTED_OPTIONAL_METADATA_FIELDS
        if unsupported_fields:
            LOGGER.warning(
                f"Ignoring unsupported optional metadata fields: {sorted(unsupported_fields)}"
            )

        filtered = {
            key: value
            for key, value in parsed.items()
            if key in SUPPORTED_OPTIONAL_METADATA_FIELDS
        }

        # Normalize metadata fields
        filtered = normalize_metadata_fields(filtered)

        if filtered:
            LOGGER.info(f"Parsed optional metadata: {filtered}")

        return filtered

    except YAMLError as e:
        # TODO: raise (but earlier, so OTA file isn't created yet)
        #  or handle error better? Easy to miss right now if optional metadata is bad.
        LOGGER.error(f"Failed to parse optional metadata YAML: {e}")
        return {}


def _download_and_extract_ota_file(issue_data: IssueData) -> tuple[bytes, str, str]:
    """Download and extract OTA file from issue data.

    Handles downloading from URL and extracting from ZIP if necessary.
    In the future, this could be extended to support local file paths
    or have another function with the same signature for local files.

    Args:
        issue_data: Issue data containing OTA file info and metadata

    Returns:
        Tuple of (ota_content, filename, source_url)
    """
    # Extract download information from issue
    download_url, filename, source_url = extract_download_info(issue_data)

    LOGGER.info(f"Downloading OTA file: {filename}")
    LOGGER.info(f"Download URL: {download_url}")
    ota_content = download_ota_file(download_url)

    # If the file came from a GitHub issue attachment, it may be a ZIP file
    # containing the actual OTA file due to GitHub upload limitations
    if issue_data.ota_file:
        extracted = extract_ota_from_zip(ota_content)
        if extracted:
            ota_content, extracted_filename = extracted
            LOGGER.info(
                f"Extracted OTA file from ZIP: {extracted_filename} "
                f"(original: {filename})"
            )
            filename = extracted_filename

    return ota_content, filename, source_url


def _check_and_delete_existing_images(
    manufacturer_directory: str,
    filename: str,
    existing_images_handling: ExistingImagesHandling,
    ota_metadata: OtaMetadata,
) -> tuple[dict[str, IndexMetadata], int | None]:
    """Check for and optionally delete existing images with the same manufacturer and type.

    Args:
        manufacturer_directory: Directory name for the manufacturer
        filename: Current filename to exclude from deletion
        existing_images_handling: How to handle existing images (from dropdown selection)
        ota_metadata: OTA metadata of the new image being added

    Returns:
        Tuple of:
        - Dictionary of images that were found (and potentially deleted)
        - Highest file version from existing images that's lower than new image version
          (only set when SET_MIN_VERSION option is selected)
    """
    images_to_delete: dict[str, IndexMetadata] = {}
    highest_version: int | None = None

    try:
        all_images_to_delete = find_existing_images_with_same_type(
            manufacturer_directory,
            ota_metadata.manufacturer_id,
            ota_metadata.image_type,
        )

        # Exclude the current file if it exists (we're replacing it anyway)
        images_to_delete = {
            fname: metadata
            for fname, metadata in all_images_to_delete.items()
            if fname != filename
        }

        # Handle based on user selection
        if existing_images_handling == ExistingImagesHandling.REPLACE:
            if images_to_delete:
                LOGGER.info(
                    f"Replace existing enabled. Deleting {len(images_to_delete)} image(s)"
                )
                delete_images(manufacturer_directory, images_to_delete)
        elif existing_images_handling == ExistingImagesHandling.SET_MIN_VERSION:
            if images_to_delete:
                # Find the highest file version from existing images that's still lower than new version
                versions_below_new = [
                    metadata.file_version
                    for metadata in images_to_delete.values()
                    if metadata.file_version < ota_metadata.file_version
                ]
                if versions_below_new:
                    highest_version = max(versions_below_new)
                    LOGGER.info(
                        f"Keeping {len(images_to_delete)} existing image(s). "
                        f"Setting min_current_file_version to highest existing version below new version: "
                        f"0x{highest_version:08X} (new version: 0x{ota_metadata.file_version:08X})"
                    )
                else:
                    LOGGER.info(
                        f"Keeping {len(images_to_delete)} existing image(s). "
                        f"No existing versions are lower than new version (0x{ota_metadata.file_version:08X}), "
                        f"not setting min_current_file_version"
                    )
        elif existing_images_handling == ExistingImagesHandling.KEEP_ALL:
            if images_to_delete:
                LOGGER.info(
                    f"Keeping all {len(images_to_delete)} existing image(s) without version constraints"
                )
    except Exception as e:
        LOGGER.warning(f"Failed to check/delete existing images: {e}")

    return images_to_delete, highest_version


def _handle_file_replacement(
    ota_target_path: Path,
    ota_content: bytes,
    manufacturer_directory: str,
    filename: str,
    third_party_download: bool,
) -> tuple[Path, bool, bool]:
    """Handle file replacement logic for both third-party and regular files.

    Args:
        ota_target_path: Target path where the OTA file would be stored
        ota_content: Binary content of the OTA file
        manufacturer_directory: Directory name for the manufacturer
        filename: Name of the OTA file
        third_party_download: Whether this is a third-party download

    Returns:
        Tuple of (image_path, file_existed, replaced_third_party)
    """
    file_existed = ota_target_path.exists()
    replaced_third_party = False

    if third_party_download:
        LOGGER.info("Third-party download enabled - skipping image file save")

        # Use the ota_target_path as image_path (file won't be created)
        image_path = ota_target_path

        # If local file exists, delete it since we're replacing with third-party
        if file_existed:
            LOGGER.info(
                f"Local file {filename} exists and will be replaced by third-party download"
            )
            image_path.unlink()
    else:
        # Check if a third-party YAML exists (being replaced by local file)
        yaml_file_path = ota_target_path.with_suffix(ota_target_path.suffix + ".yaml")
        if not file_existed and yaml_file_path.exists():
            # YAML exists but file doesn't - check if it's a third-party YAML
            try:
                existing_yaml = parse_metadata_file(yaml_file_path)
            except ValueError as e:
                LOGGER.warning(f"Failed to parse existing YAML {yaml_file_path}: {e}")
                existing_yaml = None
            if isinstance(existing_yaml, YamlMetadataThirdParty):
                # Mark that we're replacing a third-party download with local file
                file_existed = True
                replaced_third_party = True
                LOGGER.info(
                    f"Third-party YAML for {filename} exists and will be replaced by local file"
                )
            else:
                # YAML exists without OTA file, but it's not a third-party YAML
                # This is an inconsistent state - regular YAMLs should have corresponding OTA files
                LOGGER.warning(
                    f"Found YAML file {yaml_file_path.name} without corresponding OTA file, "
                    "but it's not marked as third-party. This may indicate a repository inconsistency."
                )

        image_path = save_ota_file(ota_content, manufacturer_directory, filename)

    return image_path, file_existed, replaced_third_party


def _inject_auto_min_version(
    optional_metadata: dict[str, Any],
    auto_min_version: int | None,
) -> dict[str, Any]:
    """Inject auto-calculated min_current_file_version if applicable.

    Args:
        optional_metadata: Optional metadata dict
        auto_min_version: Auto-calculated minimum version (may be None)

    Returns:
        Updated optional_metadata dict
    """
    if auto_min_version is None:
        return optional_metadata

    # Only set if not already specified by user
    if "min_current_file_version" not in optional_metadata:
        optional_metadata["min_current_file_version"] = auto_min_version
        LOGGER.info(f"Automatically set min_current_file_version to {auto_min_version}")
    else:
        # TODO: Raise ValueError instead?
        #  -> We now create a warning in the PR markdown. See if we want to keep that.
        LOGGER.warning(
            f"User specified min_current_file_version ({optional_metadata['min_current_file_version']}) "
            f"overrides automatic value ({auto_min_version})"
        )

    return optional_metadata


def _create_yaml_metadata(
    image_path: Path,
    source_url: str,
    source_file_name: str,
    ota_metadata: OtaMetadata,
    optional_metadata: dict[str, Any],
    issue_data: IssueData,
) -> BaseYamlMetadata:
    """Create appropriate YAML metadata object based on third_party_download flag.

    Args:
        image_path: Path where the image file is (or would be for third-party)
        source_url: URL for the release/download
        source_file_name: Original filename from the source URL/upload
        ota_metadata: OTA metadata extracted from the image
        optional_metadata: Optional metadata fields from the issue
        issue_data: Issue data containing flags and metadata

    Returns:
        YamlMetadataThirdParty or YamlMetadataFile object
    """
    if issue_data.third_party_download:
        # For third-party downloads, use checksums and file_size from ota_metadata
        third_party_download = ThirdPartyDownload(
            manufacturer_id=ota_metadata.manufacturer_id,
            image_type=ota_metadata.image_type,
            file_version=ota_metadata.file_version,
            file_size=ota_metadata.file_size,
            checksum_sha3_256=ota_metadata.checksum_sha3_256,
            checksum_sha512=ota_metadata.checksum_sha512,
            header_string=ota_metadata.header_string,
        )
        return YamlMetadataThirdParty(
            file_name=image_path.name,
            source_url=source_url,
            source_file_name=source_file_name,
            release_notes=issue_data.release_notes,
            third_party_download=third_party_download,
            **optional_metadata,
        )
    else:
        return YamlMetadataFile(
            file_name=image_path.name,
            source_url=source_url,
            source_file_name=source_file_name,
            release_notes=issue_data.release_notes,
            **optional_metadata,
        )


def prepare_pr(issue_data: IssueData) -> PrepareResult:
    """Prepare changes for creating a GitHub PR.

    Downloads the OTA file, validates it, saves it to the images folder (unless
    third-party download), and generates metadata YAML. Optionally deletes existing
    images with the same type based on the existing_images_handling setting.

    Args:
        issue_data: Issue data containing OTA file info and metadata

    Returns:
        PrepareResult with paths, filenames, and information about deleted/replaced images

    Raises:
        ValueError: If content is not a valid Zigbee OTA image or filename cannot be determined
    """
    # Download and extract OTA file
    ota_content, original_filename, source_url = _download_and_extract_ota_file(
        issue_data
    )

    # Validate that the content is a valid Zigbee OTA image
    # (done after potential ZIP extraction)
    ota_metadata = parse_and_validate_ota_bytes(ota_content)
    LOGGER.info("Successfully validated Zigbee OTA image")

    # Generate standardized filename from OTA metadata
    filename = generate_ota_filename(ota_metadata)
    LOGGER.info(f"Generated filename: {filename} (original: {original_filename})")

    # Extract manufacturer and get specific directory if it's a known one
    manufacturer_from_ota = extract_manufacturer_from_ota(ota_metadata)
    manufacturer_directory = determine_manufacturer(manufacturer_from_ota)

    # Check for existing images with same manufacturer ID and image type
    LOGGER.info(
        f"Checking for existing images with "
        f"manufacturer_id=0x{ota_metadata.manufacturer_id:04X}, "
        f"image_type=0x{ota_metadata.image_type:04X}"
    )
    images_to_delete, auto_min_version = _check_and_delete_existing_images(
        manufacturer_directory,
        filename,
        issue_data.existing_images_handling,
        ota_metadata,
    )

    # Handle file replacement logic
    ota_target_path = IMAGES_PATH / manufacturer_directory / filename
    image_path, file_existed, replaced_third_party = _handle_file_replacement(
        ota_target_path,
        ota_content,
        manufacturer_directory,
        filename,
        issue_data.third_party_download,
    )

    # Parse optional metadata and inject auto-calculated min_current_file_version if applicable
    optional_metadata = parse_optional_metadata(issue_data.optional_metadata)
    optional_metadata = _inject_auto_min_version(optional_metadata, auto_min_version)

    # Create YAML metadata object
    yaml_metadata = _create_yaml_metadata(
        image_path,
        source_url,
        original_filename,
        ota_metadata,
        optional_metadata,
        issue_data,
    )

    # Generate and write metadata YAML file
    generate_metadata_for_image(image_path, yaml_metadata)

    yaml_path = image_path.with_suffix(image_path.suffix + ".yaml")
    LOGGER.info(f"Generated metadata file: {yaml_path}")

    return PrepareResult(
        image_path=image_path if not issue_data.third_party_download else None,
        yaml_path=yaml_path,
        filename=filename,
        manufacturer_directory=manufacturer_directory,
        deletable_images=images_to_delete,
        existing_images_handling=issue_data.existing_images_handling,
        auto_min_version=auto_min_version,
        file_existed=file_existed,
        replaced_third_party=replaced_third_party,
        checklist=issue_data.checklist,
        ota_metadata=ota_metadata,
        yaml_metadata=yaml_metadata,
    )
