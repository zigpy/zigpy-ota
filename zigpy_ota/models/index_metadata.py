"""Index metadata model for the final OTA metadata JSON index.

This module provides IndexMetadata, which represents the final merged metadata
that appears in the JSON index. It combines data from OTA binary files and YAML
metadata files into the format consumed by zigpy for OTA updates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zigpy_ota.const import GITHUB_PR_BASE_URL
from zigpy_ota.models.ota_metadata import OtaMetadata
from zigpy_ota.models.yaml_metadata import (
    BaseYamlMetadata,
    Channel,
    YamlMetadataThirdParty,
)


@dataclass(frozen=True, kw_only=True, slots=True)
class IndexMetadata:
    """Final merged metadata for the JSON index.

    Combines OTA metadata (from binary parsing) with YAML metadata
    (user-provided information) into the final format for the index.
    """

    # Required core fields (from OTA or third-party YAML)
    binary_url: str
    manufacturer_id: int
    image_type: int
    file_version: int
    file_size: int

    # Checksum fields
    checksum_sha3_256: str
    checksum_sha512: str

    # Optional header string from OTA file header
    header_string: str | None = None

    # Required field (from YAML)
    source_file_name: str

    # Optional metadata fields (from YAML)
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
    third_party_download: bool = False

    # Internal fields
    disabled: bool = False
    channel: Channel = Channel.STABLE

    @classmethod
    def from_ota_and_yaml(
        cls, ota: OtaMetadata, yaml: BaseYamlMetadata, binary_url: str
    ) -> IndexMetadata:
        """Merge OTA metadata with YAML metadata.

        Args:
            ota: Metadata from OTA binary file or YAML third-party download
            yaml: Metadata from YAML file
            binary_url: URL where the OTA binary is hosted

        Returns:
            Merged IndexMetadata for JSON index
        """
        # Start with OTA data
        result: dict[str, Any] = {
            "binary_url": binary_url,
            "manufacturer_id": ota.manufacturer_id,
            "image_type": ota.image_type,
            "file_version": ota.file_version,
            "file_size": ota.file_size,
            "checksum_sha3_256": ota.checksum_sha3_256,
            "checksum_sha512": ota.checksum_sha512,
        }

        if ota.header_string:
            result["header_string"] = ota.header_string

        # Add hardware versions from OTA if present
        if ota.min_hardware_version is not None:
            result["min_hardware_version"] = ota.min_hardware_version
        if ota.max_hardware_version is not None:
            result["max_hardware_version"] = ota.max_hardware_version

        # Add YAML metadata (order matches dataclass field order)
        result["source_file_name"] = yaml.source_file_name
        if yaml.source_url:
            result["source_url"] = yaml.source_url
        if yaml.pull_request:
            result["pull_request"] = yaml.pull_request
        if yaml.release_notes:
            result["release_notes"] = yaml.release_notes
        if yaml.release_notes_url:
            result["release_notes_url"] = yaml.release_notes_url
        if yaml.manufacturer_names:
            result["manufacturer_names"] = yaml.manufacturer_names
        if yaml.model_names:
            result["model_names"] = yaml.model_names

        # Override hardware versions if specified in YAML
        # TODO: Check if zigpy supports this
        # TODO: Check if we want to log a warning if OTA and YAML differ, or raise?
        if yaml.min_hardware_version is not None:
            result["min_hardware_version"] = yaml.min_hardware_version
        if yaml.max_hardware_version is not None:
            result["max_hardware_version"] = yaml.max_hardware_version

        if yaml.min_current_file_version is not None:
            result["min_current_file_version"] = yaml.min_current_file_version
        if yaml.max_current_file_version is not None:
            result["max_current_file_version"] = yaml.max_current_file_version
        if yaml.specificity is not None:
            result["specificity"] = yaml.specificity

        # Add third_party_download flag if this is a third-party metadata
        if isinstance(yaml, YamlMetadataThirdParty):
            result["third_party_download"] = True

        # Preserve disabled flag if set
        if yaml.disabled:
            result["disabled"] = True

        # Set channel from YAML (defaults to STABLE)
        result["channel"] = yaml.channel

        return cls(**result)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Only includes non-None values and skips SHA-512 checksum.
        """
        result: dict[str, Any] = {
            "binary_url": self.binary_url,
            "manufacturer_id": self.manufacturer_id,
            "image_type": self.image_type,
            "file_version": self.file_version,
            "file_size": self.file_size,
            "checksum": f"sha3-256:{self.checksum_sha3_256}",
            "source_file_name": self.source_file_name,
        }

        # Add optional fields if present
        if self.source_url:
            result["source_url"] = self.source_url
        if self.pull_request:
            result["pull_request"] = self.pull_request
        if self.release_notes:
            result["release_notes"] = self.release_notes
        if self.release_notes_url:
            result["release_notes_url"] = self.release_notes_url
        if self.manufacturer_names:
            result["manufacturer_names"] = self.manufacturer_names
        if self.model_names:
            result["model_names"] = self.model_names
        if self.min_hardware_version is not None:
            result["min_hardware_version"] = self.min_hardware_version
        if self.max_hardware_version is not None:
            result["max_hardware_version"] = self.max_hardware_version
        if self.min_current_file_version is not None:
            result["min_current_file_version"] = self.min_current_file_version
        if self.max_current_file_version is not None:
            result["max_current_file_version"] = self.max_current_file_version
        if self.specificity is not None:
            result["specificity"] = self.specificity
        if self.third_party_download:
            result["third_party_download"] = self.third_party_download
        if self.disabled:
            result["disabled"] = self.disabled

        return result

    def to_dict_zigpy(self) -> dict[str, Any]:
        """Convert to dictionary for zigpy JSON index serialization.

        Similar to to_dict() but excludes fields not used by zigpy:
        - source_file_name: informational field, not consumed by zigpy
        - source_url: informational field, not consumed by zigpy
        - disabled: internal field, disabled entries are filtered out entirely
        """
        result = self.to_dict()
        result.pop("disabled", None)
        result.pop("source_file_name", None)

        # TODO: Do we want to keep source_url and third_party_download for zigpy?
        result.pop("source_url", None)
        result.pop("third_party_download", None)

        # Remove internal fields from zigpy output
        result.pop("pull_request", None)
        result.pop("release_notes_url", None)

        # Compute release_url: prefer release_notes_url, fall back to PR URL
        release_url: str | None = None
        if self.release_notes_url:
            release_url = self.release_notes_url
        elif self.pull_request:
            release_url = f"{GITHUB_PR_BASE_URL}/{self.pull_request}"

        # TODO: Remove this hack and insert release_url properly in the correct position
        # Insert release_url after release_notes, or after checksum if no release_notes
        # We can insert after checksum, as everything else between is popped before it
        if release_url:
            insert_after = "release_notes" if "release_notes" in result else "checksum"
            new_result: dict[str, Any] = {}
            for key, value in result.items():
                new_result[key] = value
                if key == insert_after:
                    new_result["release_url"] = release_url
            result = new_result

        return result

    # TODO: For later
    def to_dict_z2m(self) -> dict[str, Any]:
        """Convert to dictionary for Zigbee2MQTT JSON index serialization.

        Uses camelCase field names and z2m-specific field mappings:
        - fileName, fileVersion, fileSize, url, imageType, manufacturerCode
        - sha512 (from checksum_sha512)
        - otaHeaderString (always empty string for compatibility)
        - originalUrl (from source_url)
        - releaseNotes (from release_notes)
        - manufacturerName (from manufacturer_names)
        - modelId (from model_names, first entry only)
        - minFileVersion, maxFileVersion (version constraints)
        """
        # TODO: Get this into IndexMetadata properly
        # Extract filename from binary_url
        file_name = self.binary_url.rsplit("/", 1)[-1]

        result: dict[str, Any] = {
            "fileName": file_name,
            "fileVersion": self.file_version,
            "fileSize": self.file_size,
            "url": self.binary_url,
            "imageType": self.image_type,
            "manufacturerCode": self.manufacturer_id,
            "sha512": self.checksum_sha512,
            "otaHeaderString": self.header_string or "",
        }

        # Add originalUrl from source_url
        if self.source_url:
            result["originalUrl"] = self.source_url

        # Add releaseNotes
        if self.release_notes:
            result["releaseNotes"] = self.release_notes

        # Add manufacturerName (z2m uses singular name but accepts array)
        if self.manufacturer_names:
            result["manufacturerName"] = self.manufacturer_names

        # Add modelId (z2m uses first model name only, as a string)
        # Note: prepare_metadata_for_z2m() duplicates entries for multiple model names
        # TODO: Leave like this? Add parameter to this method about which model name to use?
        if self.model_names:
            result["modelId"] = self.model_names[0]

        # Add version constraints
        if self.min_current_file_version is not None:
            result["minFileVersion"] = self.min_current_file_version

        if self.max_current_file_version is not None:
            result["maxFileVersion"] = self.max_current_file_version

        return result
