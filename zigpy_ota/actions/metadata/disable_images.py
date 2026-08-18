"""Enable or disable OTA images by editing their YAML metadata files."""

from __future__ import annotations

import logging
from pathlib import Path

from zigpy_ota.utils.yaml_utils import create_yaml_instance

LOGGER = logging.getLogger(__name__)


def set_images_disabled(yaml_files: list[Path], *, disabled: bool) -> list[Path]:
    """Set or remove the ``disabled`` field in OTA metadata YAML files.

    Disabled images are excluded from the generated JSON indexes but stay in the
    repository (see the ``disabled`` YAML field). Comments and formatting in the
    YAML files are preserved.

    Args:
        yaml_files: YAML metadata files to edit
        disabled: True to set ``disabled: true``, False to remove the field

    Returns:
        The files that were actually changed.
    """
    yaml = create_yaml_instance()
    changed: list[Path] = []

    for yaml_file in yaml_files:
        with yaml_file.open("r", encoding="utf-8") as file:
            data = yaml.load(file)

        if not isinstance(data, dict):
            raise ValueError(f"{yaml_file} does not contain a YAML mapping")

        if disabled:
            if data.get("disabled") is True:
                LOGGER.info("%s is already disabled", yaml_file)
                continue
            data["disabled"] = True
        else:
            if "disabled" not in data:
                LOGGER.info("%s is already enabled", yaml_file)
                continue
            del data["disabled"]

        with yaml_file.open("w", encoding="utf-8") as file:
            yaml.dump(data, file)
        changed.append(yaml_file)

    return changed
