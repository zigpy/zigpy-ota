"""YAML metadata models."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Channel(StrEnum):
    """Release channel for OTA images.

    Channels form a hierarchy where each level includes all previous levels:
    - STABLE: Production releases (default, no channel set in YAML)
    - BETA: Pre-release testing (includes stable images)
    - DEV: Development builds (includes stable and beta images)
    """

    STABLE = "stable"
    BETA = "beta"
    DEV = "dev"


@dataclass(frozen=True, kw_only=True, slots=True)
class ThirdPartyDownload:
    """OTA metadata required for third-party downloads.

    For third-party downloads, there is no local binary file to extract metadata from,
    so all OTA metadata fields must be provided in the YAML file.
    """

    # OTA header fields
    manufacturer_id: int
    image_type: int
    file_version: int
    file_size: int

    # Checksum fields
    checksum_sha3_256: str
    checksum_sha512: str

    # Optional header string from OTA file header
    header_string: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThirdPartyDownload:
        """Create ThirdPartyDownload from a dictionary.

        Raises:
            KeyError: If required fields are missing
        """
        return cls(
            manufacturer_id=data["manufacturer_id"],
            image_type=data["image_type"],
            file_version=data["file_version"],
            file_size=data["file_size"],
            checksum_sha3_256=data["checksum_sha3_256"],
            checksum_sha512=data["checksum_sha512"],
            header_string=data.get("header_string"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        result = {
            "manufacturer_id": self.manufacturer_id,
            "image_type": self.image_type,
            "file_version": self.file_version,
            "file_size": self.file_size,
            "checksum_sha3_256": self.checksum_sha3_256,
            "checksum_sha512": self.checksum_sha512,
        }
        if self.header_string is not None:
            result["header_string"] = self.header_string
        return result


@dataclass(frozen=True, kw_only=True, slots=True)
class BaseYamlMetadata:
    """Base metadata for OTA YAML files.

    Contains fields common to both regular OTA files and third-party downloads.
    Based on zigpy's BaseOtaImageMetadata but adapted for YAML generation.
    """

    # Required fields
    file_name: str  # Local filename
    source_file_name: str  # Original filename

    # Optional metadata fields (common to both regular and third-party)
    source_url: str | None = None
    pull_request: str | None = None
    release_notes: str | None = None
    release_notes_url: str | None = None
    manufacturer_names: tuple[str, ...] | None = None
    model_names: tuple[str, ...] | None = None
    min_hardware_version: int | None = None
    max_hardware_version: int | None = None
    min_current_file_version: int | None = None
    max_current_file_version: int | None = None
    specificity: int | None = None
    disabled: bool = False
    channel: Channel = Channel.STABLE

    def _add_optional_fields_to_dict(self, result: dict[str, Any]) -> None:
        """Add optional metadata fields to the result dictionary.

        Args:
            result: Dictionary to add fields to (modified in place)
        """
        optional_fields = [
            ("release_notes", self.release_notes),
            ("release_notes_url", self.release_notes_url),
            ("manufacturer_names", self.manufacturer_names),
            ("model_names", self.model_names),
            ("min_hardware_version", self.min_hardware_version),
            ("max_hardware_version", self.max_hardware_version),
            ("min_current_file_version", self.min_current_file_version),
            ("max_current_file_version", self.max_current_file_version),
            ("specificity", self.specificity),
        ]
        for field_name, field_value in optional_fields:
            if field_value is not None:
                result[field_name] = field_value

        if self.disabled:
            result["disabled"] = self.disabled

        # Only write channel if not stable (stable is the default)
        if self.channel != Channel.STABLE:
            result["channel"] = self.channel.value

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization. Implemented in subclasses."""
        raise NotImplementedError("Subclasses must implement to_dict()")


@dataclass(frozen=True, kw_only=True, slots=True)
class YamlMetadataFile(BaseYamlMetadata):
    """Metadata for regular OTA files with local binaries.

    For regular OTA files, the OTA metadata (manufacturer_id, image_type, etc.)
    is extracted from the binary file, not from the YAML.
    """

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> YamlMetadataFile:
        """Create YamlMetadataFile from a dictionary.

        Raises:
            KeyError: If required fields are missing
        """
        return cls(
            file_name=data["file_name"],
            source_file_name=data["source_file_name"],
            source_url=data.get("source_url"),
            pull_request=data.get("pull_request"),
            release_notes=data.get("release_notes"),
            release_notes_url=data.get("release_notes_url"),
            manufacturer_names=data.get("manufacturer_names"),
            model_names=data.get("model_names"),
            min_hardware_version=data.get("min_hardware_version"),
            max_hardware_version=data.get("max_hardware_version"),
            min_current_file_version=data.get("min_current_file_version"),
            max_current_file_version=data.get("max_current_file_version"),
            specificity=data.get("specificity"),
            disabled=data.get("disabled", False),
            channel=Channel(ch) if (ch := data.get("channel")) else Channel.STABLE,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        result: dict[str, Any] = {
            "file_name": self.file_name,
            "source_file_name": self.source_file_name,
        }

        if self.source_url is not None:
            result["source_url"] = self.source_url

        if self.pull_request is not None:
            result["pull_request"] = self.pull_request

        # Add optional metadata fields using base class helper
        self._add_optional_fields_to_dict(result)
        return result


@dataclass(frozen=True, kw_only=True, slots=True)
class YamlMetadataThirdParty(BaseYamlMetadata):
    """Metadata for third-party OTA downloads.

    For third-party downloads, all OTA metadata fields are required since
    there is no local binary file to extract them from. The OTA metadata
    is stored in the YAML file instead of being extracted from a binary.
    """

    # Override to make source_url required
    source_url: str

    # Third-party download info containing OTA metadata and checksums
    third_party_download: ThirdPartyDownload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> YamlMetadataThirdParty:
        """Create YamlMetadataThirdParty from a dictionary.

        Raises:
            KeyError: If required fields are missing
        """
        # Parse the nested third_party_download structure
        third_party_data = data["third_party_download"]
        third_party_download = ThirdPartyDownload.from_dict(third_party_data)

        return cls(
            file_name=data["file_name"],
            source_file_name=data["source_file_name"],
            source_url=data["source_url"],
            pull_request=data.get("pull_request"),
            third_party_download=third_party_download,
            # Optional fields:
            release_notes=data.get("release_notes"),
            release_notes_url=data.get("release_notes_url"),
            manufacturer_names=data.get("manufacturer_names"),
            model_names=data.get("model_names"),
            min_hardware_version=data.get("min_hardware_version"),
            max_hardware_version=data.get("max_hardware_version"),
            min_current_file_version=data.get("min_current_file_version"),
            max_current_file_version=data.get("max_current_file_version"),
            specificity=data.get("specificity"),
            disabled=data.get("disabled", False),
            channel=Channel(ch) if (ch := data.get("channel")) else Channel.STABLE,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        result: dict[str, Any] = {
            "file_name": self.file_name,
            "source_file_name": self.source_file_name,
            "source_url": self.source_url,
        }

        if self.pull_request is not None:
            result["pull_request"] = self.pull_request

        result["third_party_download"] = self.third_party_download.to_dict()

        # Add optional metadata fields using base class helper
        self._add_optional_fields_to_dict(result)
        return result
