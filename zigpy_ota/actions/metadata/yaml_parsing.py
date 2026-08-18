from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML, YAMLError

from zigpy_ota.models.yaml_metadata import (
    YamlMetadataFile,
    YamlMetadataThirdParty,
)
from zigpy_ota.utils.yaml_utils import normalize_metadata_fields, normalize_yaml_values

LOGGER = logging.getLogger(__name__)


def parse_metadata_files(
    images_folder_path: Path,
    fail_on_filename_mismatch: bool,
    fail_on_missing_ota: bool,
    fail_on_invalid_yaml: bool,
) -> dict[str, YamlMetadataFile | YamlMetadataThirdParty]:
    """Parse all YAML metadata files in the images directory and subdirectories.

    Recursively walks through the images folder and parses each .yaml file,
    validating that the file_name field matches the YAML filename and checking
    for corresponding OTA image files (unless it's a third-party download).

    Args:
        images_folder_path: Path to the images directory
        fail_on_filename_mismatch: If True, raise error when file_name field
            doesn't match the YAML filename
        fail_on_missing_ota: If True, raise error when a regular YAML metadata
            file has no corresponding OTA binary file
        fail_on_invalid_yaml: If True, raise error when YAML parsing fails or
            required fields are missing

    Returns:
        Dictionary mapping relative paths to YamlMetadataFile or YamlMetadataThirdParty
        (e.g., "signify/lamp.zigbee")

    Raises:
        ValueError: If fail_on_filename_mismatch is True and mismatch detected,
            or if fail_on_missing_ota is True and OTA binary is missing,
            or if fail_on_invalid_yaml is True and YAML is invalid
    """
    metadata: dict[str, YamlMetadataFile | YamlMetadataThirdParty] = {}
    filename_mismatches: list[str] = []
    missing_ota_files: list[str] = []
    invalid_yaml_files: list[str] = []

    for root, dirs, files in os.walk(images_folder_path):
        for file in files:
            if file.endswith(".yaml"):
                yaml_file_path = Path(root) / file

                try:
                    file_metadata = parse_metadata_file(yaml_file_path)
                except ValueError as e:
                    invalid_yaml_files.append(str(e))
                    if not fail_on_invalid_yaml:
                        LOGGER.warning(f"Skipping invalid YAML: {e}")
                    continue

                expected_file_name = file.removesuffix(".yaml")  # YAML w/o extension

                # Validate file_name field matches YAML filename
                if file_metadata.file_name != expected_file_name:
                    msg = (
                        f"{yaml_file_path}: file_name field '{file_metadata.file_name}' "
                        f"does not match YAML filename '{expected_file_name}'"
                    )
                    filename_mismatches.append(msg)
                    if not fail_on_filename_mismatch:
                        LOGGER.warning(f"Skipping {msg}")
                    continue

                # Check for corresponding OTA image (unless it's a third-party download)
                ota_image_path = Path(root) / expected_file_name

                # For regular OTA files, check that the binary file exists
                # Skip this check for third-party downloads (YamlMetadataThirdParty)
                if isinstance(file_metadata, YamlMetadataFile):
                    if not ota_image_path.exists():
                        msg = (
                            f"{yaml_file_path}: corresponding OTA image file "
                            f"'{ota_image_path.name}' not found"
                        )
                        missing_ota_files.append(msg)
                        if not fail_on_missing_ota:
                            LOGGER.warning(f"Skipping {msg}")
                        continue

                # Use relative path from images folder as key to handle duplicate filenames
                relative_path = ota_image_path.relative_to(images_folder_path)
                metadata[str(relative_path)] = file_metadata

    # TODO: Check if we want to keep errors like this or streamline everywhere?
    if filename_mismatches and fail_on_filename_mismatch:
        raise ValueError(
            f"Found {len(filename_mismatches)} YAML file(s) with mismatched file_name field:\n"
            + "\n".join(f"  - {msg}" for msg in filename_mismatches)
        )

    if missing_ota_files and fail_on_missing_ota:
        raise ValueError(
            f"Found {len(missing_ota_files)} YAML file(s) without corresponding OTA binary:\n"
            + "\n".join(f"  - {msg}" for msg in missing_ota_files)
        )

    if invalid_yaml_files and fail_on_invalid_yaml:
        raise ValueError(
            f"Found {len(invalid_yaml_files)} invalid YAML file(s):\n"
            + "\n".join(f"  - {msg}" for msg in invalid_yaml_files)
        )

    return metadata


def parse_metadata_file(
    file_path: Path,
) -> YamlMetadataFile | YamlMetadataThirdParty:
    """Parse a single metadata YAML file and return YamlMetadataFile or YamlMetadataThirdParty.

    Args:
        file_path: Path to the YAML metadata file

    Returns:
        YamlMetadataFile for regular OTA files, YamlMetadataThirdParty for third-party downloads

    Raises:
        ValueError: If YAML parsing fails or required fields are missing
    """
    yaml = YAML()

    with open(file_path, "r") as file:
        try:
            data: Any = yaml.load(file)
        except YAMLError as e:
            raise ValueError(f"{file_path}: YAML parsing error - {e}") from e

        if not isinstance(data, dict):
            raise ValueError(f"{file_path}: YAML file does not contain a dictionary")

        # Convert CommentedMap to regular dict and normalize special YAML types
        data = normalize_yaml_values(dict(data))

        # Normalize fields
        normalized_data = normalize_metadata_fields(data)

        # Reject vacuous constraints in committed YAML (the correct spelling of
        # "no constraint" is omitting the field). Issue-form submissions never
        # produce these: the model drops them before the YAML is generated.
        if normalized_data.get("min_current_file_version") == 0:
            raise ValueError(
                f"{file_path}: min_current_file_version=0 can never exclude a "
                "device - omit the field instead"
            )
        if normalized_data.get("max_current_file_version") == 0xFFFFFFFF:
            raise ValueError(
                f"{file_path}: max_current_file_version=0xFFFFFFFF can never "
                "exclude a device - omit the field instead"
            )

        # Create appropriate metadata type based on third_party_download presence
        try:
            if "third_party_download" in normalized_data:
                return YamlMetadataThirdParty.from_dict(normalized_data)
            else:
                return YamlMetadataFile.from_dict(normalized_data)
        except KeyError as e:
            raise ValueError(f"{file_path}: Missing required fields - {e}") from e
        except (TypeError, ValueError) as e:
            # e.g. non-integer constraint values, or an unknown channel value
            raise ValueError(f"{file_path}: Invalid metadata - {e}") from e
