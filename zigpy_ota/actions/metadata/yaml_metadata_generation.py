from __future__ import annotations

import logging
import os
from pathlib import Path

from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import LiteralScalarString

from zigpy_ota.actions.metadata.yaml_parsing import parse_metadata_file
from zigpy_ota.const import (
    METADATA_EXAMPLE_RELEASE_NOTES,
    METADATA_EXAMPLE_URL,
)
from zigpy_ota.models.yaml_metadata import (
    BaseYamlMetadata,
    YamlMetadataFile,
    YamlMetadataThirdParty,
)
from zigpy_ota.utils.yaml_utils import create_yaml_instance

LOGGER = logging.getLogger(__name__)


def generate_metadata_for_image(
    image_file_path: Path,
    metadata: BaseYamlMetadata,
) -> None:
    """Generate metadata YAML file for a single image file.

    For third-party downloads, OTA metadata (manufacturer_id, image_type, file_version,
    checksum, file_size) must be provided since the image file won't be stored in the repo.

    Args:
        image_file_path: Path where the image file would be (for YAML file naming)
        metadata: BaseYamlMetadata object (YamlMetadataFile or YamlMetadataThirdParty)
    """
    yaml_file_path = image_file_path.with_suffix(image_file_path.suffix + ".yaml")
    LOGGER.info(f"Generating metadata file: {yaml_file_path}")

    # Ensure parent directory exists
    yaml_file_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to CommentedMap and add header comment
    cm = CommentedMap(metadata.to_dict())
    cm.yaml_set_start_comment("OTA metadata")

    # Include comments with third-party notice if applicable
    if isinstance(metadata, YamlMetadataThirdParty):
        cm.yaml_set_comment_before_after_key(
            "third_party_download",
            before="OTA image metadata required for third-party hosted images:",
        )

    # Use literal block style (|-) for release_notes
    if "release_notes" in cm and cm["release_notes"]:
        cm["release_notes"] = LiteralScalarString(cm["release_notes"])

    # Create YAML instance and write
    yaml = create_yaml_instance()

    with open(yaml_file_path, "w") as yaml_file:
        yaml.dump(cm, yaml_file)


def generate_stub_metadata_folder(
    images_folder_path: Path, include_examples: bool = False
) -> None:
    """Generate stub metadata YAML files for each image file in the images folder.

    Recursively walks through the images folder and creates stub YAML metadata
    files for each image file, skipping hidden files and existing YAML files.

    Args:
        images_folder_path: Path to the images directory
        include_examples: If True, include example source_url and release_notes
    """
    for root, dirs, files in os.walk(images_folder_path):
        LOGGER.info(f"Processing directory: {root}")
        for file in files:
            if file.startswith(".") or file.endswith(".yaml"):
                continue

            image_file_path = Path(root) / file
            # Create stub metadata, optionally with example values
            # source_file_name is the same as file_name for stub metadata
            stub_metadata = YamlMetadataFile(
                file_name=image_file_path.name,
                source_file_name=image_file_path.name,
                source_url=METADATA_EXAMPLE_URL if include_examples else None,
                release_notes=METADATA_EXAMPLE_RELEASE_NOTES
                if include_examples
                else None,
            )
            generate_metadata_for_image(image_file_path, stub_metadata)


def normalize_yaml_metadata_folder(images_folder_path: Path) -> int:
    """Normalize all YAML metadata files by re-parsing and re-writing them.

    This ensures consistent formatting and field ordering across all metadata files.

    Args:
        images_folder_path: Path to the images directory

    Returns:
        Number of YAML files processed
    """
    count = 0
    for root, dirs, files in os.walk(images_folder_path):
        for file in files:
            if not file.endswith(".yaml"):
                continue

            yaml_file_path = Path(root) / file

            try:
                metadata = parse_metadata_file(yaml_file_path)
            except ValueError as e:
                LOGGER.warning(f"Skipping invalid YAML file: {e}")
                continue

            # Derive the image file path from the YAML file path
            # (remove the .yaml extension to get the image path)
            image_file_path = yaml_file_path.with_suffix("")

            LOGGER.info(f"Normalizing: {yaml_file_path}")
            generate_metadata_for_image(image_file_path, metadata)

            count += 1

    return count
