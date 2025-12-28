"""OTA file renaming utilities.

Provides functionality to rename OTA files to the standardized format:
<manufacturer_id>-<image_type>-<file_version>_<hash>.ota
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, replace
from pathlib import Path

from zigpy_ota.actions.metadata.name_utils import generate_ota_filename
from zigpy_ota.actions.metadata.ota_parsing import parse_ota_file
from zigpy_ota.actions.metadata.yaml_metadata_generation import (
    generate_metadata_for_image,
)
from zigpy_ota.actions.metadata.yaml_parsing import parse_metadata_file
from zigpy_ota.models.ota_metadata import OtaMetadata
from zigpy_ota.models.yaml_metadata import YamlMetadataThirdParty

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True, slots=True)
class RenameResult:
    """Result of a single file rename operation."""

    original_path: Path
    new_path: Path | None = None  # None if skipped or error
    yaml_updated: bool = False
    skipped: bool = False
    error: str | None = None


@dataclass(frozen=True, kw_only=True, slots=True)
class RenameSummary:
    """Summary of rename operations on a folder."""

    renamed: int
    already_correct: int
    errors: int
    results: tuple[RenameResult, ...]


def rename_ota_file(
    file_path: Path,
    dry_run: bool = False,
) -> RenameResult:
    """Rename a single OTA file to the standardized format.

    Also updates the corresponding YAML metadata file with the new filename,
    and sets source_file_name to the original filename if not already set.

    Args:
        file_path: Path to the OTA file to rename
        dry_run: If True, don't actually rename files

    Returns:
        RenameResult with details of the operation
    """
    original_filename = file_path.name

    # Try to parse the OTA file
    ota_metadata = parse_ota_file(file_path)
    if ota_metadata is None:
        return RenameResult(
            original_path=file_path,
            error="Not a valid OTA file",
        )

    # Generate standardized filename
    new_filename = generate_ota_filename(ota_metadata)

    # Check if rename is needed
    if original_filename == new_filename:
        return RenameResult(
            original_path=file_path,
            new_path=file_path,
            skipped=True,
        )

    new_file_path = file_path.parent / new_filename

    if dry_run:
        return RenameResult(
            original_path=file_path,
            new_path=new_file_path,
        )

    # Check if target already exists
    if new_file_path.exists() and new_file_path != file_path:
        return RenameResult(
            original_path=file_path,
            error="Target file already exists",
        )

    # Rename the OTA file
    LOGGER.info(f"Renaming {file_path.name} -> {new_filename}")
    file_path.rename(new_file_path)

    # Handle YAML file if it exists
    yaml_updated = False
    yaml_path = file_path.with_suffix(file_path.suffix + ".yaml")
    if yaml_path.exists():
        try:
            yaml_updated = _update_yaml_for_rename(
                yaml_path, new_file_path, original_filename, new_filename
            )
        except ValueError as e:
            LOGGER.warning(f"Failed to update YAML for {file_path.name}: {e}")

    return RenameResult(
        original_path=file_path,
        new_path=new_file_path,
        yaml_updated=yaml_updated,
    )


def rename_third_party_yaml(
    yaml_path: Path,
    dry_run: bool = False,
) -> RenameResult:
    """Rename a third-party YAML file to the standardized format.

    For third-party downloads, there is no OTA binary file - only the YAML
    metadata file exists. This function renames the YAML file based on the
    metadata contained within it.

    Args:
        yaml_path: Path to the third-party YAML file
        dry_run: If True, don't actually rename files

    Returns:
        RenameResult with details of the operation
    """
    try:
        yaml_metadata = parse_metadata_file(yaml_path)
    except ValueError as e:
        return RenameResult(
            original_path=yaml_path,
            error=f"Invalid YAML: {e}",
        )

    # Only process third-party YAML files
    if not isinstance(yaml_metadata, YamlMetadataThirdParty):
        return RenameResult(
            original_path=yaml_path,
            error="Not a third-party YAML file",
        )

    # Create OtaMetadata from the third-party YAML
    ota_metadata = OtaMetadata.from_third_party_yaml(yaml_metadata)

    # Generate standardized filename
    new_ota_filename = generate_ota_filename(ota_metadata)
    new_yaml_filename = new_ota_filename + ".yaml"

    original_filename = yaml_path.name
    # The "virtual" OTA filename is the YAML filename without .yaml
    original_ota_filename = yaml_path.stem  # removes last suffix

    # Check if rename is needed
    if original_filename == new_yaml_filename:
        return RenameResult(
            original_path=yaml_path,
            new_path=yaml_path,
            skipped=True,
        )

    new_yaml_path = yaml_path.parent / new_yaml_filename

    if dry_run:
        return RenameResult(
            original_path=yaml_path,
            new_path=new_yaml_path,
            yaml_updated=True,
        )

    # Check if target already exists
    if new_yaml_path.exists() and new_yaml_path != yaml_path:
        return RenameResult(
            original_path=yaml_path,
            error="Target file already exists",
        )

    # Update the YAML metadata with new filename
    if (
        yaml_metadata.source_file_name == yaml_metadata.file_name
        or not yaml_metadata.source_file_name
    ):
        updated_metadata = replace(
            yaml_metadata,
            file_name=new_ota_filename,
            source_file_name=original_ota_filename,
        )
    else:
        updated_metadata = replace(yaml_metadata, file_name=new_ota_filename)

    # Write the updated metadata to the new path
    # Note: generate_metadata_for_image expects the OTA path, not YAML path
    new_ota_path = yaml_path.parent / new_ota_filename
    generate_metadata_for_image(new_ota_path, updated_metadata)

    # Remove old YAML file
    if yaml_path != new_yaml_path:
        yaml_path.unlink()

    LOGGER.info(f"Renamed third-party YAML: {original_filename} -> {new_yaml_filename}")

    return RenameResult(
        original_path=yaml_path,
        new_path=new_yaml_path,
        yaml_updated=True,
    )


def _update_yaml_for_rename(
    yaml_path: Path,
    new_file_path: Path,
    original_filename: str,
    new_filename: str,
) -> bool:
    """Update YAML metadata file for a renamed OTA file.

    Args:
        yaml_path: Path to the existing YAML file
        new_file_path: New path for the OTA file
        original_filename: Original OTA filename (before rename)
        new_filename: New OTA filename (after rename)

    Returns:
        True if YAML was updated successfully

    Raises:
        ValueError: If YAML parsing fails
    """
    # Parse the YAML metadata
    yaml_metadata = parse_metadata_file(yaml_path)

    # Update the file_name field
    # Also set source_file_name to original filename if not already set
    # (or if it was the same as file_name, meaning it was stub metadata)
    if (
        yaml_metadata.source_file_name == yaml_metadata.file_name
        or not yaml_metadata.source_file_name
    ):
        updated_metadata = replace(
            yaml_metadata,
            file_name=new_filename,
            source_file_name=original_filename,
        )
    else:
        updated_metadata = replace(yaml_metadata, file_name=new_filename)

    # Calculate new YAML path
    new_yaml_path = new_file_path.with_suffix(new_file_path.suffix + ".yaml")

    # Write the updated metadata
    generate_metadata_for_image(new_file_path, updated_metadata)

    # Remove old YAML file if it has a different path
    if yaml_path != new_yaml_path:
        yaml_path.unlink()

    LOGGER.info(f"Updated YAML: {new_yaml_path.name}")
    return True


def rename_ota_files_in_folder(
    images_path: Path,
    dry_run: bool = False,
) -> RenameSummary:
    """Rename all OTA files in a folder to the standardized format.

    Scans the folder recursively for OTA files and third-party YAML files,
    and renames them to: <manufacturer_id>-<image_type>-<file_version>_<hash>.ota

    Args:
        images_path: Path to the images folder
        dry_run: If True, don't actually rename files

    Returns:
        RenameSummary with counts and details of all operations
    """
    results: list[RenameResult] = []
    renamed_count = 0
    skipped_count = 0
    error_count = 0

    # Collect all files first to avoid issues with renaming during iteration
    ota_files: list[Path] = []
    yaml_only_files: list[Path] = []

    for root, _dirs, files in os.walk(images_path):
        for file in files:
            # Skip hidden files
            if file.startswith("."):
                continue

            file_path = Path(root) / file

            if file.endswith(".yaml"):
                # Check if this YAML has a corresponding OTA file
                # The OTA file would be the YAML filename without .yaml
                ota_path = file_path.with_suffix("")  # Remove .yaml
                if not ota_path.exists():
                    # This is a YAML-only file (potentially third-party)
                    yaml_only_files.append(file_path)
            else:
                # This is a potential OTA file
                ota_files.append(file_path)

    # Process OTA files
    for file_path in ota_files:
        result = rename_ota_file(file_path, dry_run=dry_run)
        results.append(result)

        if result.error:
            error_count += 1
        elif result.skipped:
            skipped_count += 1
        else:
            renamed_count += 1

    # Process third-party YAML files (YAML without corresponding OTA binary)
    for yaml_path in yaml_only_files:
        result = rename_third_party_yaml(yaml_path, dry_run=dry_run)

        # Skip non-third-party YAML files silently (not an error)
        if result.error == "Not a third-party YAML file":
            continue

        results.append(result)

        if result.error:
            error_count += 1
        elif result.skipped:
            skipped_count += 1
        else:
            renamed_count += 1

    return RenameSummary(
        renamed=renamed_count,
        already_correct=skipped_count,
        errors=error_count,
        results=tuple(results),
    )
