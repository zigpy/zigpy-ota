from __future__ import annotations

import logging
import os
from pathlib import Path

from zigpy.ota.image import parse_ota_image
from zigpy.ota.validators import validate_ota_image

from zigpy_ota.actions.metadata.yaml_parsing import parse_metadata_file
from zigpy_ota.actions.pr.download_utils import download_ota_file
from zigpy_ota.models.ota_metadata import OtaMetadata
from zigpy_ota.models.yaml_metadata import YamlMetadataThirdParty

LOGGER = logging.getLogger(__name__)


def verify_third_party_metadata(
    ota_metadata: OtaMetadata, yaml_metadata: YamlMetadataThirdParty, yaml_path: Path
) -> None:
    """Verify that OTA metadata matches the third-party YAML metadata.

    Raises ValueError with detailed comparison if critical fields don't match.

    Args:
        ota_metadata: Metadata extracted from the downloaded OTA file
        yaml_metadata: Metadata from the third-party YAML file
        yaml_path: Path to the YAML file (for error messages)

    Raises:
        ValueError: If checksum or other critical fields don't match
    """
    tp = yaml_metadata.third_party_download

    # TODO: Check if we want to keep this, and keep it here?
    # Build detailed metadata comparison for error messages
    def _build_error_details() -> str:
        return (
            f"\nMetadata comparison for {yaml_path.name}:"
            f"\n  Manufacturer ID - YAML: 0x{tp.manufacturer_id:04X}, OTA: 0x{ota_metadata.manufacturer_id:04X}"
            f"\n  Image type - YAML: 0x{tp.image_type:04X}, OTA: 0x{ota_metadata.image_type:04X}"
            f"\n  File version - YAML: 0x{tp.file_version:08X}, OTA: 0x{ota_metadata.file_version:08X}"
            f"\n  File size - YAML: {tp.file_size}, OTA: {ota_metadata.file_size}"
            f"\n  Checksum SHA3-256 - YAML: {tp.checksum_sha3_256}, OTA: {ota_metadata.checksum_sha3_256}"
            f"\n  Checksum SHA512 - YAML: {tp.checksum_sha512}, OTA: {ota_metadata.checksum_sha512}"
            f"\n  Min hardware version - YAML: {yaml_metadata.min_hardware_version}, OTA: {ota_metadata.min_hardware_version}"
            f"\n  Max hardware version - YAML: {yaml_metadata.max_hardware_version}, OTA: {ota_metadata.max_hardware_version}"
        )

    # Verify checksums first (critical)
    if ota_metadata.checksum_sha3_256 != tp.checksum_sha3_256:
        raise ValueError(
            f"Checksum SHA3-256 mismatch for third-party download{_build_error_details()}"
        )
    if ota_metadata.checksum_sha512 != tp.checksum_sha512:
        raise ValueError(
            f"Checksum SHA512 mismatch for third-party download{_build_error_details()}"
        )

    # Verify other critical fields
    if ota_metadata.file_size != tp.file_size:
        raise ValueError(
            f"File size mismatch for third-party download{_build_error_details()}"
        )

    if ota_metadata.manufacturer_id != tp.manufacturer_id:
        raise ValueError(
            f"Manufacturer ID mismatch for third-party download{_build_error_details()}"
        )

    if ota_metadata.image_type != tp.image_type:
        raise ValueError(
            f"Image type mismatch for third-party download{_build_error_details()}"
        )

    if ota_metadata.file_version != tp.file_version:
        raise ValueError(
            f"File version mismatch for third-party download{_build_error_details()}"
        )

    # Note: Hardware versions are NOT validated because they can be overridden in YAML
    # to restrict compatibility, similar to how local OTA files work


def parse_third_party_yaml_to_ota(
    yaml_path: Path, validate: bool = False
) -> OtaMetadata | None:
    """Parse third-party YAML and optionally validate by downloading.

    Args:
        yaml_path: Path to the YAML metadata file
        validate: If True, download and validate the OTA file from the URL

    Returns:
        OtaMetadata for the third-party OTA image, None if not a third-party download

    Raises:
        ValueError: If YAML parsing fails or validation fails
    """
    yaml_metadata = parse_metadata_file(yaml_path)

    # Only process third-party downloads
    if not isinstance(yaml_metadata, YamlMetadataThirdParty):
        return None

    LOGGER.info(f"Parsing third-party YAML: {yaml_path}")

    if validate:
        LOGGER.info(f"Validating third-party download from: {yaml_metadata.source_url}")
        try:
            # Download and validate the OTA file
            content = download_ota_file(yaml_metadata.source_url)

            # Parse and validate, can raise ValueError
            ota_metadata = parse_and_validate_ota_bytes(content)

            # Verify all metadata fields match
            verify_third_party_metadata(ota_metadata, yaml_metadata, yaml_path)

            LOGGER.info(
                f"Successfully validated third-party download: {yaml_path.name}"
            )
        except Exception as e:
            LOGGER.error(f"Failed to validate third-party download: {e}")
            raise ValueError(
                f"Third-party download validation failed for {yaml_path.name}: {e}"
            ) from e
    else:
        LOGGER.info(
            f"Trusting metadata without validation for third-party download: {yaml_path.name}"
        )

    return OtaMetadata.from_third_party_yaml(yaml_metadata)


def parse_ota_files(
    images_folder_path: Path, validate_third_party: bool = False
) -> dict[str, OtaMetadata]:
    """Parse all OTA image files and third-party YAMLs in the images directory.

    Args:
        images_folder_path: Path to images directory
        validate_third_party: If True, download and validate third-party OTA files

    Returns:
        Dictionary mapping relative paths to OtaMetadata (e.g., "signify/lamp.zigbee")
    """
    metadata: dict[str, OtaMetadata] = {}
    processed_files: set[str] = set()

    for root, dirs, files in os.walk(images_folder_path):
        for file in files:
            if file.startswith("."):
                continue

            file_path = Path(root) / file

            # Handle YAML files for third-party downloads
            if file.endswith(".yaml"):
                base_file = file[:-5]  # Remove .yaml extension
                image_file = Path(root) / base_file

                # Only process if image file doesn't exist (third-party download)
                # If it exists, the OTA file will be processed instead.
                if not image_file.exists():
                    relative_path = str(image_file.relative_to(images_folder_path))
                    try:
                        ota_metadata_from_third_party_yaml = (
                            parse_third_party_yaml_to_ota(
                                file_path, validate_third_party
                            )
                        )
                        if ota_metadata_from_third_party_yaml:
                            metadata[relative_path] = ota_metadata_from_third_party_yaml
                            processed_files.add(relative_path)
                    except Exception as e:
                        # TODO: Or raise here instead? Make controllable?
                        #  This basically only fails if validation is enabled and download/validation fails,
                        #  so we likely want to know about it, but it would abort the whole parsing process,
                        #  e.g. during index generation for a release.
                        LOGGER.error(
                            f"Failed to process third-party YAML {file_path}: {e}"
                        )
            # Handle regular OTA files (skip if already processed as third-party)
            # If both YAML and OTA file exist, OTA file takes precedence here,
            # as the logic above skips processing the YAML in that case.
            else:
                relative_path = str(file_path.relative_to(images_folder_path))
                if relative_path not in processed_files:
                    file_metadata = parse_ota_file(file_path)
                    if file_metadata:
                        metadata[relative_path] = file_metadata
                        processed_files.add(relative_path)

    return metadata


def parse_and_validate_ota_bytes(contents: bytes) -> OtaMetadata:
    """Parse and validate OTA image from bytes.

    Args:
        contents: Binary contents of the OTA file

    Returns:
        OtaMetadata with parsed and validated OTA image metadata

    Raises:
        ValueError: If the content is not a valid Zigbee OTA image
    """
    try:
        image, rest = parse_ota_image(contents)
    except Exception as e:
        raise ValueError(f"Invalid Zigbee OTA image: {e}") from e

    if rest:
        LOGGER.warning(f"OTA content has {len(rest)} bytes of trailing data")

    try:
        validate_ota_image(image)
    except Exception as e:
        raise ValueError(f"Invalid Zigbee OTA image: {e}") from e

    return OtaMetadata.from_ota_image(image, contents)


def parse_ota_file(file_path: Path) -> OtaMetadata | None:
    """Parse a single OTA image file and return its metadata.

    Args:
        file_path: Path to the OTA file

    Returns:
        OtaMetadata if parsing succeeds, None on error
    """
    LOGGER.info(f"Parsing OTA file: {file_path}")
    contents = file_path.read_bytes()

    try:
        return parse_and_validate_ota_bytes(contents)
    except ValueError as e:
        LOGGER.error(f"Failed to parse OTA file {file_path}: {e}")
        # TODO: Or raise here instead? Make controllable?
        #  Right now, it's used for index generation and finding existing images during PR preparation.
        #  Individual images are still validated when added or when explicitly validating third-party downloads.
        # raise ValueError(f"Failed to parse OTA file {file_path}: {e}") from e
        return None
