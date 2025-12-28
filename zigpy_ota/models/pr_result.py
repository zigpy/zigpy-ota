"""Data models for PR preparation results."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zigpy_ota.models.index_metadata import IndexMetadata
from zigpy_ota.models.issue_model import ExistingImagesHandling, IssueChecklist
from zigpy_ota.models.ota_metadata import OtaMetadata
from zigpy_ota.models.yaml_metadata import BaseYamlMetadata


@dataclass(frozen=True, kw_only=True, slots=True)
class PrepareResult:
    """Result of preparing files for a GitHub PR.

    Contains paths to created files and information about the preparation process,
    including which images were found that could be deleted and whether they were
    actually deleted.
    """

    image_path: Path | None
    """Path to the OTA image file (None for third-party downloads)."""

    yaml_path: Path
    """Path to the generated YAML metadata file."""

    filename: str
    """Name of the OTA image file."""

    manufacturer_name: str | None
    """User-provided manufacturer name (if any)."""

    manufacturer_directory: str
    """Directory name for the manufacturer."""

    deletable_images: dict[str, IndexMetadata]
    """Images that were found with the same type and could be deleted."""

    existing_images_handling: ExistingImagesHandling
    """How existing images of the same type were handled."""

    auto_min_version: int | None
    """Auto-calculated min_current_file_version from existing images (if SET_MIN_VERSION selected)."""

    file_existed: bool
    """Whether an OTA file with the same name already existed."""

    replaced_third_party: bool
    """Whether this upload replaces a third-party download with a local file."""

    checklist: IssueChecklist
    """Checklist items from the issue submission."""

    ota_metadata: OtaMetadata
    """OTA metadata extracted from the image file."""

    yaml_metadata: BaseYamlMetadata
    """YAML metadata for the image file."""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for backward compatibility.

        Converts Path objects to strings for serialization.
        """
        return {
            "image_path": str(self.image_path) if self.image_path else None,
            "yaml_path": str(self.yaml_path),
            "filename": self.filename,
            "manufacturer_name": self.manufacturer_name,
            "manufacturer_directory": self.manufacturer_directory,
            "deletable_images": self.deletable_images,
            "existing_images_handling": self.existing_images_handling.value,
            "auto_min_version": self.auto_min_version,
            "file_existed": self.file_existed,
            "replaced_third_party": self.replaced_third_party,
            "checklist": self.checklist.to_dict(),
        }
