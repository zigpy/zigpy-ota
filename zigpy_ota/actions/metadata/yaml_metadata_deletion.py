import logging
import os
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def delete_metadata(images_folder_path: Path) -> None:
    """Delete all YAML metadata files in the images folder and subdirectories.

    Recursively walks through the images folder and deletes all .yaml files,
    skipping hidden files (those starting with '.').

    Args:
        images_folder_path: Path to the images directory
    """
    for root, dirs, files in os.walk(images_folder_path):
        LOGGER.info(f"Processing directory: {root}")
        for file in files:
            if file.startswith(".") or not file.endswith(".yaml"):
                continue

            yaml_file_path = Path(root) / file
            LOGGER.info(f"Deleting metadata file: {yaml_file_path}")
            yaml_file_path.unlink(missing_ok=True)
