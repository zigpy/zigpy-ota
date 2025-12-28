"""OTA metadata model for parsing OTA binary files.

This module provides OtaMetadata, which represents metadata extracted directly
from parsing OTA binary files. It contains core fields from the OTA header
(manufacturer_id, image_type, file_version) and computed fields (checksum, file_size).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from zigpy.ota.image import BaseOTAImage

    from zigpy_ota.models.yaml_metadata import YamlMetadataThirdParty


@dataclass(frozen=True, kw_only=True, slots=True)
class OtaMetadata:
    """Metadata extracted from parsing an OTA binary file.

    This represents the core metadata extracted from the OTA file header
    and file itself (checksum, size, etc.).
    """

    # Core fields from OTA header
    manufacturer_id: int
    image_type: int
    file_version: int
    file_size: int

    # Checksum fields
    checksum_sha3_256: str
    checksum_sha512: str

    # Optional hardware version fields
    min_hardware_version: int | None = None
    max_hardware_version: int | None = None

    # Optional header string from OTA file header
    header_string: str | None = None

    # Source indicator: True if created from third-party YAML, False if from actual OTA file
    is_from_third_party_yaml: bool = False

    @classmethod
    def from_ota_image(cls, image: BaseOTAImage, contents: bytes) -> OtaMetadata:
        """Create OtaMetadata from a parsed zigpy BaseOTAImage.

        Extracts metadata from the OTA image header and calculates checksum
        and file size from the binary contents. Integer fields are converted
        from zigpy types to standard Python ints for YAML serialization.

        Args:
            image: Parsed OTA image from zigpy
            contents: Binary contents of the OTA file (for checksum/size)

        Returns:
            OtaMetadata instance with data extracted from the OTA image
        """
        # Extract header string if present (max 32 chars, null-padded)
        header_string = (
            image.header.header_string.rstrip(b"\x00").decode("utf-8", errors="ignore")
            or None
        )

        return cls(
            file_version=int(image.header.file_version),
            file_size=len(contents),
            image_type=int(image.header.image_type),
            manufacturer_id=int(image.header.manufacturer_id),
            checksum_sha3_256=hashlib.sha3_256(contents).hexdigest(),
            checksum_sha512=hashlib.sha512(contents).hexdigest(),
            min_hardware_version=int(image.header.minimum_hardware_version)
            if image.header.hardware_versions_present
            else None,
            max_hardware_version=int(image.header.maximum_hardware_version)
            if image.header.hardware_versions_present
            else None,
            header_string=header_string,
        )

    @classmethod
    def from_third_party_yaml(cls, yaml: YamlMetadataThirdParty) -> OtaMetadata:
        """Create OtaMetadata from YamlMetadataThirdParty.

        For third-party downloads, all OTA metadata is provided in the YAML file
        rather than being extracted from an OTA binary file.

        Args:
            yaml: YamlMetadataThirdParty containing all required OTA metadata

        Returns:
            OtaMetadata instance with data from YAML
        """
        tp = yaml.third_party_download
        return cls(
            manufacturer_id=tp.manufacturer_id,
            image_type=tp.image_type,
            file_version=tp.file_version,
            file_size=tp.file_size,
            checksum_sha3_256=tp.checksum_sha3_256,
            checksum_sha512=tp.checksum_sha512,
            header_string=tp.header_string,
            min_hardware_version=yaml.min_hardware_version,
            max_hardware_version=yaml.max_hardware_version,
            is_from_third_party_yaml=True,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for merging/serialization."""
        result: dict[str, Any] = {
            "manufacturer_id": self.manufacturer_id,
            "image_type": self.image_type,
            "file_version": self.file_version,
            "file_size": self.file_size,
            "checksum_sha3_256": self.checksum_sha3_256,
            "checksum_sha512": self.checksum_sha512,
        }
        if self.min_hardware_version is not None:
            result["min_hardware_version"] = self.min_hardware_version
        if self.max_hardware_version is not None:
            result["max_hardware_version"] = self.max_hardware_version
        return result
