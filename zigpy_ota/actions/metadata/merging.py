from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from zigpy_ota.actions.metadata.ota_parsing import parse_ota_files
from zigpy_ota.actions.metadata.stale_validation import (
    compute_stale_images,
    is_dominated_by,
)
from zigpy_ota.actions.metadata.yaml_parsing import parse_metadata_files
from zigpy_ota.actions.metadata.z2m_utils import compute_max_file_versions
from zigpy_ota.const import get_github_raw_base_url
from zigpy_ota.models.index_metadata import IndexMetadata
from zigpy_ota.models.ota_metadata import OtaMetadata
from zigpy_ota.models.yaml_metadata import (
    Channel,
    YamlMetadataFile,
    YamlMetadataThirdParty,
)

LOGGER = logging.getLogger(__name__)


def _determine_binary_url(
    ota_key: str,
    yaml_value: YamlMetadataFile | YamlMetadataThirdParty,
    ota_value: OtaMetadata,
    github_raw_base_url: str,
) -> tuple[str, bool]:
    """Determine the binary URL for an OTA file and check for inconsistencies.

    Args:
        ota_key: Relative path to the OTA file
        yaml_value: YAML metadata for the file
        ota_value: OTA metadata for the file
        github_raw_base_url: Base URL for GitHub raw content

    Returns:
        Tuple of (binary_url, is_inconsistent)
        - binary_url: URL to use for downloading the binary
        - is_inconsistent: True if YAML indicates third-party but local OTA file exists
    """
    # Use third-party URL only if YAML claims third-party AND OTA metadata came from YAML
    if (
        isinstance(yaml_value, YamlMetadataThirdParty)
        and ota_value.is_from_third_party_yaml
    ):
        # Valid third-party: metadata came from YAML, use third-party URL
        return yaml_value.source_url, False

    # Regular file or inconsistent state: use GitHub URL
    binary_url = f"{github_raw_base_url}/{ota_key}"

    # Check for inconsistency: YAML claims third-party but OTA came from actual file
    is_inconsistent = isinstance(yaml_value, YamlMetadataThirdParty)

    return binary_url, is_inconsistent


def merge_metadata(
    yaml_metadata: dict[str, YamlMetadataFile | YamlMetadataThirdParty],
    ota_metadata: dict[str, OtaMetadata],
    github_ref: str,
    fail_on_missing_yaml: bool,
    fail_on_inconsistent_yaml: bool,
) -> dict[str, IndexMetadata]:
    """Merge OTA metadata with YAML metadata to create IndexMetadata.

    For regular OTA files: merges OtaMetadata with YamlMetadataFile.
    For third-party downloads: creates IndexMetadata from YamlMetadataThirdParty only.

    Args:
        yaml_metadata: Dictionary of parsed YAML metadata
        ota_metadata: Dictionary of parsed OTA binary metadata
        github_ref: Git reference (tag or branch) for constructing GitHub URLs
        fail_on_missing_yaml: If True, raise error on missing YAML files
        fail_on_inconsistent_yaml: If True, raise error when third-party YAML exists
            but local OTA file is also present (indicates repository inconsistency)

    Returns:
        Dictionary mapping paths to IndexMetadata for JSON index

    Raises:
        ValueError: If fail_on_missing_yaml is True and YAML is missing, or if
            fail_on_inconsistent_yaml is True and inconsistency is detected
    """
    missing_yaml_files: list[str] = []
    inconsistent_files: list[str] = []
    merged: dict[str, IndexMetadata] = {}

    # Construct the base URL using the provided github_ref (tag or branch)
    github_raw_base_url = get_github_raw_base_url(github_ref)

    # Process OTA files (both regular and third-party with parsed OTA metadata)
    for ota_key, ota_value in ota_metadata.items():
        # If corresponding YAML metadata exists for this OTA file
        if ota_key in yaml_metadata:
            yaml_value = yaml_metadata[ota_key]

            # Determine binary URL and check for inconsistencies
            binary_url, is_inconsistent = _determine_binary_url(
                ota_key, yaml_value, ota_value, github_raw_base_url
            )

            if is_inconsistent:
                inconsistent_files.append(ota_key)
                if not fail_on_inconsistent_yaml:
                    LOGGER.warning(
                        f"Inconsistency detected: YAML for {ota_key} indicates third-party download, "
                        f"but local OTA file exists. Third-party downloads should not have local OTA files. "
                        f"Treating as regular repository file and ignoring third-party flag."
                    )

            merged[ota_key] = IndexMetadata.from_ota_and_yaml(
                ota_value, yaml_value, binary_url
            )
        # If no corresponding YAML metadata found for this OTA file
        else:
            # TODO: Check if we want to keep warn or raise behavior like this here
            missing_yaml_files.append(ota_key)
            if not fail_on_missing_yaml:
                LOGGER.warning(f"No YAML metadata found for OTA file: {ota_key}")

    if missing_yaml_files and fail_on_missing_yaml:
        raise ValueError(
            f"Missing YAML metadata for {len(missing_yaml_files)} OTA file(s): "
            f"{', '.join(missing_yaml_files)}"
        )

    if inconsistent_files and fail_on_inconsistent_yaml:
        raise ValueError(
            f"Repository inconsistency detected for {len(inconsistent_files)} OTA file(s): "
            f"{', '.join(inconsistent_files)}. "
            f"Third-party YAML files should not have corresponding local OTA files."
        )

    return merged


def sort_metadata(metadata: dict[str, IndexMetadata]) -> dict[str, IndexMetadata]:
    """Sort metadata dictionary by keys alphabetically.

    Since OTA files are named using the format (see generate_ota_filename in
    zigpy_ota/actions/pr/prepare_files.py):
        <manufacturer_id>-<image_type>-<file_version>_<hash>.ota

    Alphabetic sorting by path effectively sorts by:
        1. Manufacturer directory name
        2. Manufacturer ID (hex)
        3. Image Type (hex)
        4. File Version (hex)

    Note: This sorting is redundant for zigpy and Z2M index generation, as
    prepare_metadata_for_zigpy and prepare_metadata_for_z2m do their own
    explicit sorting (with different file_version order). This function may
    be removed in the future.

    Args:
        metadata: Dictionary of IndexMetadata

    Returns:
        Sorted dictionary by path keys (e.g., "signify/100B-010C-01001A02_abc123.ota")
    """
    return dict(sorted(metadata.items()))


def _should_include_in_channel(index_meta: IndexMetadata, channel: Channel) -> bool:
    """Check if an image should be included based on channel filtering.

    Channel hierarchy (each level includes all previous levels):
    - STABLE: only stable images
    - BETA: stable + beta images
    - DEV: all images (stable + beta + dev)

    Args:
        index_meta: The IndexMetadata to check
        channel: The target channel

    Returns:
        True if the image should be included, False otherwise
    """
    # Dev channel includes everything
    if channel == Channel.DEV:
        return True

    # Beta channel includes stable and beta images
    if channel == Channel.BETA:
        return index_meta.channel in (Channel.STABLE, Channel.BETA)

    # Stable channel only includes stable images
    return index_meta.channel == Channel.STABLE


def _filter_metadata_by_channel(
    metadata: dict[str, IndexMetadata],
    channel: Channel,
    include_disabled: bool = False,
) -> dict[str, IndexMetadata]:
    """Filter metadata by disabled status and channel.

    Args:
        metadata: Dictionary of IndexMetadata
        channel: Release channel to filter by. Images are included based on
            channel hierarchy (DEV includes BETA includes STABLE).
        include_disabled: If True, include disabled images in output.
            If False (default), skip disabled images.

    Returns:
        Filtered dictionary of IndexMetadata
    """
    filtered: dict[str, IndexMetadata] = {}
    for image_path, index_meta in metadata.items():
        if not include_disabled and index_meta.disabled:
            LOGGER.info(f"Skipping disabled image: {image_path}")
            continue

        if not _should_include_in_channel(index_meta, channel):
            LOGGER.info(f"Skipping image for {channel.value} channel: {image_path}")
            continue

        filtered[image_path] = index_meta

    return filtered


def _sort_metadata_items(
    metadata: dict[str, IndexMetadata],
    reverse_file_version: bool = False,
) -> list[tuple[str, IndexMetadata]]:
    """Sort metadata items by directory, manufacturer_id, image_type, file_version.

    Args:
        metadata: Dictionary of IndexMetadata keyed by path
        reverse_file_version: If True, sort file_version descending (newest first).
            If False, sort file_version ascending (oldest first).

    Returns:
        Sorted list of (path, IndexMetadata) tuples
    """
    file_version_multiplier = -1 if reverse_file_version else 1
    return sorted(
        metadata.items(),
        key=lambda x: (
            x[0].split("/")[0],  # manufacturer directory from path
            x[1].manufacturer_id,
            x[1].image_type,
            file_version_multiplier * x[1].file_version,
        ),
    )


def prepare_metadata_for_zigpy(
    metadata: dict[str, IndexMetadata],
    channel: Channel,
) -> list[dict[str, Any]]:
    """Prepare metadata for saving to zigpy JSON file.

    Skips entries where disabled=True, filters by channel, and strips out
    internal fields.

    Images are sorted by (manufacturer_dir, manufacturer_id, image_type,
    file_version ascending) for consistent ordering regardless of filename
    format changes. Zigpy has its own logic to prefer newer versions.

    Args:
        metadata: Dictionary of IndexMetadata
        channel: Release channel to filter by. Images are included based on
            channel hierarchy (DEV includes BETA includes STABLE).

    Returns:
        List of dictionaries ready for JSON serialization
    """
    filtered_metadata = _filter_metadata_by_channel(metadata, channel)

    # Compute stale images (logs info for each stale image)
    compute_stale_images(filtered_metadata)

    sorted_items = _sort_metadata_items(filtered_metadata, reverse_file_version=False)
    return [index_meta.to_dict_zigpy() for image_path, index_meta in sorted_items]


def prepare_metadata_for_z2m(
    metadata: dict[str, IndexMetadata],
    channel: Channel,
) -> list[dict[str, Any]]:
    """Prepare metadata for saving to Zigbee2MQTT JSON file.

    Skips entries where disabled=True, filters by channel, and converts to z2m format.
    Stale images (dominated by newer images) are excluded entirely from Z2M output.
    Also computes max_current_file_version for images in version-constrained groups.

    For images with multiple model names, creates duplicate entries (one per model)
    since Z2M only accepts a single modelId per entry, unlike zigpy which accepts
    multiple.

    Images are sorted by (manufacturer_dir, manufacturer_id, image_type,
    file_version descending) because Z2M's getImageMeta() uses Array.find()
    which returns the first match. Within each (manufacturer_id, image_type)
    group, newest versions come first. Without this sorting, older versions
    would match first and potentially be rejected as "not an upgrade", with
    no fallback to newer versions.

    Args:
        metadata: Dictionary of IndexMetadata
        channel: Release channel to filter by. Images are included based on
            channel hierarchy (DEV includes BETA includes STABLE).

    Returns:
        List of dictionaries ready for JSON serialization in z2m format
    """
    filtered_metadata = _filter_metadata_by_channel(metadata, channel)

    # Compute stale images (logs info for each stale image)
    stale_paths = compute_stale_images(filtered_metadata)

    # Compute max_current_file_version on filtered metadata
    computed_max_versions = compute_max_file_versions(filtered_metadata)

    # Sort with reverse file_version order so Z2M's find() returns newest first
    sorted_items = _sort_metadata_items(filtered_metadata, reverse_file_version=True)

    prepared_metadata: list[dict[str, Any]] = []
    for image_path, index_meta in sorted_items:
        # Skip stale images from Z2M output entirely
        if image_path in stale_paths:
            continue

        entry = index_meta.to_dict_z2m()

        # Apply computed max_current_file_version if needed
        if image_path in computed_max_versions:
            entry["maxFileVersion"] = computed_max_versions[image_path]

        # Z2M only accepts a single modelId per entry, so we duplicate entries
        # for images with multiple model names
        if index_meta.model_names and len(index_meta.model_names) > 1:
            for model_name in index_meta.model_names:
                model_entry = entry.copy()
                model_entry["modelId"] = model_name
                prepared_metadata.append(model_entry)
        else:
            prepared_metadata.append(entry)

    return prepared_metadata


def prepare_metadata_for_markdown(
    metadata: dict[str, IndexMetadata],
    channel: Channel,
) -> list[tuple[str, IndexMetadata, bool, bool]]:
    """Prepare metadata for markdown output.

    Includes disabled images (with disabled flag), filters by channel.

    Images are sorted by (manufacturer_dir, manufacturer_id, image_type,
    file_version ascending) for consistent ordering.

    Args:
        metadata: Dictionary of IndexMetadata
        channel: Release channel to filter by. Images are included based on
            channel hierarchy (DEV includes BETA includes STABLE).

    Returns:
        List of (path, IndexMetadata, is_stale, is_disabled) tuples sorted for output
    """
    # Include disabled images for markdown (they'll be marked)
    filtered_metadata = _filter_metadata_by_channel(
        metadata, channel, include_disabled=True
    )

    # Compute stale images only on enabled images (for enabled->enabled staleness)
    enabled_metadata = {k: v for k, v in filtered_metadata.items() if not v.disabled}
    stale_paths = compute_stale_images(enabled_metadata)

    # Also check if disabled images would be stale relative to enabled images
    disabled_metadata = {k: v for k, v in filtered_metadata.items() if v.disabled}
    for disabled_path, disabled_meta in disabled_metadata.items():
        for enabled_meta in enabled_metadata.values():
            if is_dominated_by(disabled_meta, enabled_meta):
                stale_paths.add(disabled_path)
                break

    sorted_items = _sort_metadata_items(filtered_metadata, reverse_file_version=False)

    # Attach stale and disabled status to each item
    result = []
    for image_path, index_meta in sorted_items:
        is_stale = image_path in stale_paths
        is_disabled = index_meta.disabled
        result.append((image_path, index_meta, is_stale, is_disabled))

    return result


def save_metadata_to_zigpy_file(
    metadata: list[dict[str, Any]], output_file: Path
) -> None:
    """Save the parsed metadata to a zigpy JSON file.

    The output format matches zigpy's REMOTE_PROVIDER_SCHEMA:
    {
        "firmwares": [...]
    }
    """
    output_data = {"firmwares": metadata}
    output_file.write_text(json.dumps(output_data, indent=4) + "\n")


def save_metadata_to_z2m_file(
    metadata: list[dict[str, Any]], output_file: Path
) -> None:
    """Save the parsed metadata to a Zigbee2MQTT JSON file.

    The output format is a plain array of firmware objects.
    """
    output_file.write_text(json.dumps(metadata, indent=4) + "\n")


def parse_metadata_complete(
    images_folder_path: Path,
    github_ref: str,
    validate_third_party: bool,
    fail_on_missing_yaml: bool,
    fail_on_inconsistent_yaml: bool,
    fail_on_filename_mismatch: bool,
    fail_on_missing_ota: bool,
    fail_on_invalid_yaml: bool,
) -> dict[str, IndexMetadata]:
    """Main function to parse metadata files. Returns merged and sorted metadata.

    Args:
        images_folder_path: Path to images directory
        github_ref: Git reference for constructing GitHub URLs
        validate_third_party: If True, download and validate third-party OTA files
        fail_on_missing_yaml: If True, raise error on missing YAML files
        fail_on_inconsistent_yaml: If True, raise error when third-party YAML exists
            but local OTA file is also present
        fail_on_filename_mismatch: If True, raise error when YAML file_name field
            doesn't match the YAML filename
        fail_on_missing_ota: If True, raise error when a regular YAML metadata
            file has no corresponding OTA binary file
        fail_on_invalid_yaml: If True, raise error when YAML parsing fails or
            required fields are missing

    Returns:
        Dictionary mapping paths to IndexMetadata
    """
    yaml_metadata = parse_metadata_files(
        images_folder_path,
        fail_on_filename_mismatch,
        fail_on_missing_ota,
        fail_on_invalid_yaml,
    )
    ota_metadata = parse_ota_files(images_folder_path, validate_third_party)

    merged_metadata = merge_metadata(
        yaml_metadata,
        ota_metadata,
        github_ref,
        fail_on_missing_yaml,
        fail_on_inconsistent_yaml,
    )
    return sort_metadata(merged_metadata)


def parse_and_save_metadata(
    images_folder_path: Path,
    output_path: Path,
    github_ref: str,
    validate_third_party: bool,
    fail_on_missing_yaml: bool,
    fail_on_inconsistent_yaml: bool,
    fail_on_filename_mismatch: bool,
    fail_on_missing_ota: bool,
    fail_on_invalid_yaml: bool,
    channel: Channel,
) -> None:
    """Parse metadata files and save to zigpy output file.

    Args:
        images_folder_path: Path to images directory
        output_path: Path to output JSON file
        github_ref: Git reference for constructing GitHub URLs
        validate_third_party: If True, download and validate third-party OTA files
        fail_on_missing_yaml: If True, raise error on missing YAML files
        fail_on_inconsistent_yaml: If True, raise error when third-party YAML exists
            but local OTA file is also present
        fail_on_filename_mismatch: If True, raise error when YAML file_name field
            doesn't match the YAML filename
        fail_on_missing_ota: If True, raise error when a regular YAML metadata
            file has no corresponding OTA binary file
        fail_on_invalid_yaml: If True, raise error when YAML parsing fails or
            required fields are missing
        channel: Release channel to filter by
    """
    # TODO: Currently unused. Use/refactor/remove?
    merged_metadata = parse_metadata_complete(
        images_folder_path,
        github_ref,
        validate_third_party,
        fail_on_missing_yaml,
        fail_on_inconsistent_yaml,
        fail_on_filename_mismatch,
        fail_on_missing_ota,
        fail_on_invalid_yaml,
    )
    prepared_metadata = prepare_metadata_for_zigpy(merged_metadata, channel)

    save_metadata_to_zigpy_file(prepared_metadata, output_path)
    LOGGER.info(
        f"Parsed metadata saved to {output_path} ({len(prepared_metadata)} entries)"
    )
