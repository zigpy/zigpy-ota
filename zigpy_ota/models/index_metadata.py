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

        # Override hardware versions if specified in YAML. zigpy prefers index
        # metadata over the OTA header (it falls back to the firmware header
        # only when metadata is unset), and overrides are surfaced at
        # submission time via the PR-body hardware override warning.
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

    def to_dict_zigpy(self) -> dict[str, Any]:
        """Convert to dictionary for zigpy JSON index serialization.

        Only emits fields zigpy's remote provider consumes. Repo-internal
        fields (source_file_name, source_url, pull_request, release_notes_url,
        third_party_download, disabled) are omitted to keep the index lean;
        pull_request/release_notes_url instead feed the release_url field.
        """
        result: dict[str, Any] = {
            "binary_url": self.binary_url,
            "manufacturer_id": self.manufacturer_id,
            "image_type": self.image_type,
            "file_version": self.file_version,
            "file_size": self.file_size,
            "checksum": f"sha3-256:{self.checksum_sha3_256}",
        }

        if self.release_notes:
            result["release_notes"] = self.release_notes

        # release_url: prefer release_notes_url, fall back to the PR URL
        if self.release_notes_url:
            result["release_url"] = self.release_notes_url
        elif self.pull_request:
            result["release_url"] = f"{GITHUB_PR_BASE_URL}/{self.pull_request}"

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

        return result

    def to_dict_z2m(self, model_name: str | None = None) -> dict[str, Any]:
        """Convert to dictionary for Zigbee2MQTT JSON index serialization.

        Uses camelCase field names and z2m-specific field mappings:
        - fileName, fileVersion, fileSize, url, imageType, manufacturerCode
        - sha512 (from checksum_sha512)
        - otaHeaderString (always empty string for compatibility)
        - originalUrl (from source_url)
        - releaseNotes (from release_notes)
        - manufacturerName (from manufacturer_names)
        - modelId (from `model_name`, or the first of model_names)
        - minFileVersion, maxFileVersion (version constraints)
        - hardwareVersionMin, hardwareVersionMax (hardware constraints)

        Args:
            model_name: Model name to emit as modelId. z2m entries carry a
                single modelId, so the index generator calls this once per
                model name. Defaults to the first of model_names, if any.
        """
        # The URL basename is the standardized repo file name for local
        # images, and the actual remote file's name for third-party images
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

        # Add modelId (single string; one z2m entry per model name)
        if model_name is None and self.model_names:
            model_name = self.model_names[0]
        if model_name is not None:
            result["modelId"] = model_name

        # Add version constraints
        if self.min_current_file_version is not None:
            result["minFileVersion"] = self.min_current_file_version

        if self.max_current_file_version is not None:
            result["maxFileVersion"] = self.max_current_file_version

        # Add hardware version constraints (Z2M matches on these)
        if self.min_hardware_version is not None:
            result["hardwareVersionMin"] = self.min_hardware_version

        if self.max_hardware_version is not None:
            result["hardwareVersionMax"] = self.max_hardware_version

        return result
