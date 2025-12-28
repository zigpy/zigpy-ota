"""Collision validation for OTA images in the index.

This module provides functions to detect colliding OTA images - images with
the same (manufacturer_id, image_type, file_version, specificity) but different
binary content. Such collisions cause zigpy to ignore all affected images at
runtime because it cannot determine which is correct.

By detecting collisions at index generation time, we can catch problems before
publishing the index.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from zigpy_ota.models.index_metadata import IndexMetadata

LOGGER = logging.getLogger(__name__)


def compute_specificity(index_meta: IndexMetadata) -> int:
    """Compute specificity score for an image, matching zigpy's algorithm.

    Higher specificity is preferred when picking a final OTA image.
    This mirrors the logic in zigpy.ota.OtaImageMeta.specificity.

    The algorithm adds points based on which metadata fields are present:
    - +1000 for manufacturer_names
    - +1000 for model_names
    - +100 for image_type (always present)
    - +100 for manufacturer_id (always present)
    - +10 for min_current_file_version
    - +10 for max_current_file_version
    - +1 for min_hardware_version
    - +1 for max_hardware_version
    - Plus any explicit specificity value from metadata

    Args:
        index_meta: The IndexMetadata to compute specificity for

    Returns:
        Computed specificity score
    """
    total = 0

    if index_meta.manufacturer_names:
        total += 1000

    if index_meta.model_names:
        total += 1000

    # image_type and manufacturer_id are always present in OTA images
    total += 100  # image_type
    total += 100  # manufacturer_id

    if index_meta.min_current_file_version is not None:
        total += 10

    if index_meta.max_current_file_version is not None:
        total += 10

    if index_meta.min_hardware_version is not None:
        total += 1

    if index_meta.max_hardware_version is not None:
        total += 1

    # Boost the specificity with explicit value if set
    if index_meta.specificity is not None:
        total += index_meta.specificity

    return total


@dataclass(frozen=True, kw_only=True, slots=True)
class CollisionInfo:
    """Information about a collision between OTA images."""

    manufacturer_id: int
    image_type: int
    file_version: int
    specificity: int
    images: tuple[tuple[str, IndexMetadata], ...]  # Tuple of (path, metadata) pairs


def validate_collisions(
    metadata: dict[str, IndexMetadata],
    fail_on_collision: bool = False,
) -> list[CollisionInfo]:
    """Validate that no colliding OTA images exist in the index.

    A collision occurs when multiple images have the same
    (manufacturer_id, image_type, file_version, specificity) but different
    binary content (different checksums). This mirrors zigpy's runtime check.

    When zigpy encounters such collisions at runtime, it ignores all colliding
    images because it cannot determine which is correct. By detecting this at
    index generation time, we can catch problems before publishing.

    Args:
        metadata: Dictionary mapping paths to IndexMetadata
        fail_on_collision: If True, raise error on collision. If False, log warning.

    Returns:
        List of CollisionInfo objects describing any collisions found

    Raises:
        ValueError: If fail_on_collision is True and collisions are detected
    """
    # Group images by (manufacturer_id, image_type, file_version, specificity)
    # Then sub-group by checksum to identify different binaries
    collision_groups: defaultdict[
        tuple[int, int, int, int],
        defaultdict[str, list[tuple[str, IndexMetadata]]],
    ] = defaultdict(lambda: defaultdict(list))

    for path, index_meta in metadata.items():
        specificity = compute_specificity(index_meta)
        key = (
            index_meta.manufacturer_id,
            index_meta.image_type,
            index_meta.file_version,
            specificity,
        )
        collision_groups[key][index_meta.checksum_sha3_256].append((path, index_meta))

    collisions: list[CollisionInfo] = []

    for (
        mfr_id,
        img_type,
        file_ver,
        specificity,
    ), checksum_buckets in collision_groups.items():
        # If only one unique checksum, no collision
        if len(checksum_buckets) < 2:
            continue

        # Multiple different checksums for same (mfr_id, img_type, version, specificity)
        all_images: list[tuple[str, IndexMetadata]] = []
        for bucket in checksum_buckets.values():
            all_images.extend(bucket)

        collision = CollisionInfo(
            manufacturer_id=mfr_id,
            image_type=img_type,
            file_version=file_ver,
            specificity=specificity,
            images=tuple(all_images),
        )
        collisions.append(collision)

        # Log the collision
        image_paths = [path for path, _ in all_images]
        LOGGER.warning(
            "Multiple unique OTA images for manufacturer_id=0x%04X, image_type=0x%04X, "
            "version=0x%08X with specificity=%d exist. "
            "It is not possible to tell which image is correct so zigpy will ignore "
            "all %d colliding images at runtime. Images: %s",
            mfr_id,
            img_type,
            file_ver,
            specificity,
            len(all_images),
            image_paths,
        )

    if collisions and fail_on_collision:
        collision_details = []
        for c in collisions:
            paths = [path for path, _ in c.images]
            collision_details.append(
                f"  - mfr=0x{c.manufacturer_id:04X}, type=0x{c.image_type:04X}, "
                f"ver=0x{c.file_version:08X}, specificity={c.specificity}: {paths}"
            )
        raise ValueError(
            f"Found {len(collisions)} OTA image collision(s) that zigpy will ignore "
            f"at runtime:\n" + "\n".join(collision_details)
        )

    return collisions
