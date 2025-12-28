"""OTA filename utilities."""

from __future__ import annotations

from zigpy_ota.models.ota_metadata import OtaMetadata


def generate_ota_filename(ota_metadata: OtaMetadata) -> str:
    """Generate a standardized OTA filename from metadata.

    Format: <manufacturer_id>-<image_type>-<file_version>_<first 6 chars of hash>.ota
    All numbers are in hexadecimal format (uppercase).

    Args:
        ota_metadata: OTA metadata containing manufacturer_id, image_type,
                      file_version, and checksum

    Returns:
        Standardized filename string
    """
    manufacturer_id_hex = f"{ota_metadata.manufacturer_id:04X}"
    image_type_hex = f"{ota_metadata.image_type:04X}"
    file_version_hex = f"{ota_metadata.file_version:08X}"
    hash_prefix = ota_metadata.checksum_sha3_256[:6]

    return (
        f"{manufacturer_id_hex}-{image_type_hex}-{file_version_hex}_{hash_prefix}.ota"
    )
