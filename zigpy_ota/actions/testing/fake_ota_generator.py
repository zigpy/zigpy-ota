"""Generate fake OTA images for testing purposes.

Creates minimal valid OTA images from scratch that pass zigpy validation.
The images contain no real upgrade data, only a minimal header and a small
dummy subelement to satisfy the format requirements.
"""

from __future__ import annotations

import logging
from pathlib import Path

import zigpy.types as t
from zigpy.ota.image import (
    ElementTagId,
    FieldControl,
    HWVersion,
    OTAImage,
    OTAImageHeader,
    SubElement,
    parse_ota_image,
)

LOGGER = logging.getLogger(__name__)


def generate_fake_ota_image(
    output_path: Path,
    manufacturer_id: int,
    image_type: int,
    file_version: int,
    min_hardware_version: int | None = None,
    max_hardware_version: int | None = None,
    header_string: str | None = None,
) -> None:
    """Generate a fake OTA image with specified header values.

    Creates a minimal OTA image from scratch with no real upgrade data.
    The image contains only a valid header and a minimal dummy subelement
    to pass zigpy validation.

    Args:
        output_path: Path where the fake OTA image should be saved
        manufacturer_id: Manufacturer ID (uint16)
        image_type: Image type (uint16)
        file_version: File version (uint32)
        min_hardware_version: Minimum hardware version (uint16), optional
        max_hardware_version: Maximum hardware version (uint16), optional
        header_string: Header string, optional (max 32 characters)
    """
    LOGGER.info(f"Generating fake OTA image: {output_path}")

    # Validate header string length
    if header_string is not None and len(header_string) > 32:
        msg = f"Header string too long (max 32 chars): {len(header_string)}"
        raise ValueError(msg)

    # Build field_control flags
    field_control = FieldControl(0)
    if min_hardware_version is not None or max_hardware_version is not None:
        field_control |= FieldControl.HARDWARE_VERSIONS_PRESENT

    # Create the OTA image header
    header = OTAImageHeader(
        upgrade_file_id=OTAImageHeader.MAGIC_VALUE,
        header_version=0x0100,
        header_length=0,  # Will be calculated by zigpy
        field_control=field_control,
        manufacturer_id=manufacturer_id,
        image_type=image_type,
        file_version=file_version,
        stack_version=0x0002,
        header_string=header_string or "",
        image_size=0,  # Will be calculated by zigpy
    )

    # Set hardware versions if provided (wrap in HWVersion type)
    if min_hardware_version is not None:
        header.minimum_hardware_version = HWVersion(min_hardware_version)
    if max_hardware_version is not None:
        header.maximum_hardware_version = HWVersion(max_hardware_version)

    # Create a minimal dummy subelement with UPGRADE_IMAGE tag
    # This contains minimal fake upgrade data (just 64 bytes of zeros)
    # to satisfy the OTA format requirements
    dummy_data = bytes(64)
    subelement = SubElement(tag_id=ElementTagId.UPGRADE_IMAGE, data=dummy_data)

    # Create the OTA image with header and subelements
    image = OTAImage(header=header, subelements=[subelement])

    # Calculate actual sizes by serializing header and subelements separately
    header_size = len(header.serialize())
    subelements_size = sum(len(se.serialize()) for se in image.subelements)
    total_size = header_size + subelements_size

    # Update header with calculated sizes
    image.header.header_length = t.uint16_t(header_size)
    image.header.image_size = t.uint32_t(total_size)

    # Serialize final image and save
    output_data = image.serialize()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(output_data)

    LOGGER.info(
        f"Fake OTA image created: manufacturer_id=0x{manufacturer_id:04X}, "
        f"image_type=0x{image_type:04X}, file_version=0x{file_version:08X}, "
        f"size={len(output_data)} bytes"
    )


def replace_ota_with_fake(
    ota_file: Path,
    *,
    dry_run: bool = False,
) -> dict[str, int | str | bool]:
    """Replace a real OTA file with a fake one preserving header data.

    Reads the header data from an existing OTA file and generates a minimal
    fake OTA file with the same header values but much smaller size.

    Args:
        ota_file: Path to the OTA file to replace
        dry_run: If True, don't actually replace the file, just analyze

    Returns:
        Dictionary with replacement information:
        - file_name (str): Name of the file
        - original_size (int): Original file size in bytes
        - fake_size (int): Fake file size in bytes
        - size_reduction (int): Size reduction in bytes
        - dry_run (bool): Whether this was a dry run

    Raises:
        ValueError: If the OTA file cannot be parsed
        FileNotFoundError: If the OTA file doesn't exist
    """
    if not ota_file.exists():
        msg = f"OTA file not found: {ota_file}"
        raise FileNotFoundError(msg)

    LOGGER.info(f"Processing OTA file: {ota_file.name}")

    # Read and parse the existing OTA file
    data = ota_file.read_bytes()
    original_size = len(data)
    image, _ = parse_ota_image(data)

    # Extract header information
    header = image.header
    LOGGER.info(f"  Manufacturer ID: 0x{header.manufacturer_id:04X}")
    LOGGER.info(f"  Image Type: 0x{header.image_type:04X}")
    LOGGER.info(f"  File Version: 0x{header.file_version:08X}")

    # Extract optional fields
    min_hw = None
    max_hw = None
    if header.minimum_hardware_version is not None:
        min_hw = int(header.minimum_hardware_version)
        LOGGER.info(f"  Min HW Version: 0x{min_hw:04X}")
    if header.maximum_hardware_version is not None:
        max_hw = int(header.maximum_hardware_version)
        LOGGER.info(f"  Max HW Version: 0x{max_hw:04X}")

    header_string = None
    if header.header_string:
        # HeaderString is a bytes subclass - convert to bytes then decode
        header_str_bytes = bytes(header.header_string).rstrip(b"\x00")
        if header_str_bytes:
            header_string = header_str_bytes.decode("utf-8", errors="ignore")
            LOGGER.info(f"  Header String: '{header_string}'")

    if dry_run:
        LOGGER.info(f"  Original size: {original_size:,} bytes")
        LOGGER.info("  [DRY RUN] Would replace with fake OTA file")
        return {
            "file_name": ota_file.name,
            "original_size": original_size,
            "fake_size": 0,
            "size_reduction": 0,
            "dry_run": True,
        }

    # Generate fake OTA file with same header data
    temp_file = ota_file.with_suffix(".zigbee.tmp")
    generate_fake_ota_image(
        output_path=temp_file,
        manufacturer_id=header.manufacturer_id,
        image_type=header.image_type,
        file_version=header.file_version,
        min_hardware_version=min_hw,
        max_hardware_version=max_hw,
        header_string=header_string,
    )

    # Replace original with fake
    fake_size = temp_file.stat().st_size
    temp_file.replace(ota_file)

    size_reduction = original_size - fake_size
    reduction_pct = 100 * size_reduction / original_size

    LOGGER.info(f"  Original size: {original_size:,} bytes")
    LOGGER.info(f"  Fake size: {fake_size:,} bytes")
    LOGGER.info(f"  Size reduction: {size_reduction:,} bytes ({reduction_pct:.1f}%)")
    LOGGER.info("  ✓ Replaced with fake OTA file")

    return {
        "file_name": ota_file.name,
        "original_size": original_size,
        "fake_size": fake_size,
        "size_reduction": size_reduction,
        "dry_run": False,
    }
