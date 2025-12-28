"""Data models for zigpy-ota."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ExistingImagesHandling(StrEnum):
    """Options for handling existing images of the same type."""

    REPLACE = "REPLACE"
    SET_MIN_VERSION = "SET_MIN_VERSION"
    KEEP_ALL = "KEEP_ALL"


@dataclass(frozen=True, kw_only=True, slots=True)
class OTAFile:
    """Represents an OTA file attachment from GitHub."""

    filename: str
    url: str

    def to_dict(self) -> dict[str, str]:
        """Convert to dictionary."""
        return {"filename": self.filename, "url": self.url}


@dataclass(frozen=True, kw_only=True, slots=True)
class IssueChecklist:
    """Checklist items from the issue submission."""

    supported_format: bool
    filled_release_notes: bool
    tested_on_device: bool
    is_official_source: bool

    def to_dict(self) -> dict[str, bool]:
        """Convert to dictionary."""
        return {
            "supported_format": self.supported_format,
            "filled_release_notes": self.filled_release_notes,
            "tested_on_device": self.tested_on_device,
            "is_official_source": self.is_official_source,
        }


@dataclass(frozen=True, kw_only=True, slots=True)
class IssueData:
    """Parsed data from a GitHub issue for OTA submission."""

    ota_file: OTAFile | None
    ota_image_url: str | None
    manufacturer_name: str | None
    checklist: IssueChecklist
    existing_images_handling: ExistingImagesHandling = ExistingImagesHandling.KEEP_ALL
    third_party_download: bool = False
    release_notes: str | None = None
    additional_information: str | None = None
    optional_metadata: str | None = None

    @property
    def is_official_source(self) -> bool:
        """Convenience property to access is_official_source from checklist."""
        return self.checklist.is_official_source

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IssueData:
        """Create an IssueData instance from a dictionary."""
        ota_file = None
        if data.get("ota_file"):
            ota_file = OTAFile(**data["ota_file"])

        checklist = IssueChecklist(**data["checklist"])

        # Parse existing_images_handling field
        # ExistingImagesHandling constructor handles both enum instances and valid strings
        # Raises ValueError for invalid strings
        # Defaults to KEEP_ALL if not specified
        existing_images_handling = (
            ExistingImagesHandling(value)
            if (value := data.get("existing_images_handling")) is not None
            else ExistingImagesHandling.KEEP_ALL
        )

        return cls(
            ota_file=ota_file,
            ota_image_url=data.get("ota_image_url"),
            manufacturer_name=data.get("manufacturer_name"),
            existing_images_handling=existing_images_handling,
            third_party_download=data.get("third_party_download", False),
            release_notes=data.get("release_notes"),
            checklist=checklist,
            additional_information=data.get("additional_information"),
            optional_metadata=data.get("optional_metadata"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert IssueData to a dictionary."""
        return {
            "ota_file": self.ota_file.to_dict() if self.ota_file else None,
            "ota_image_url": self.ota_image_url,
            "manufacturer_name": self.manufacturer_name,
            "existing_images_handling": self.existing_images_handling.value,
            "third_party_download": self.third_party_download,
            "release_notes": self.release_notes,
            "checklist": self.checklist.to_dict(),
            "additional_information": self.additional_information,
            "optional_metadata": self.optional_metadata,
        }
