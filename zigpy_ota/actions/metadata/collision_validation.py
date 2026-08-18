"""Collision validation for OTA images in the index.

This module provides functions to detect colliding OTA images - images with
the same (manufacturer_id, image_type, file_version, specificity) but different
binary content. Such collisions cause zigpy to ignore all affected images at
runtime because it cannot determine which is correct.

By detecting collisions at index generation time, we can catch problems before
publishing the index.

Images that share a matching key but have mutually exclusive device-matching
constraints (disjoint ``model_names``/``manufacturer_names``, or non-overlapping
hardware/current-file-version ranges) are not reported as collisions: zigpy's
runtime ``check_compatibility`` filters them per-device before its own collision
check runs, so no single device can ever see both at once.
"""

from __future__ import annotations

import itertools
import logging
from collections import defaultdict
from dataclasses import dataclass

from zigpy_ota.actions.metadata.constraints import effective_max_current_version
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


def _ranges_overlap(
    a_min: int | None,
    a_max: int | None,
    b_min: int | None,
    b_max: int | None,
) -> bool:
    """Check if two inclusive integer ranges overlap. ``None`` means unbounded."""
    lo_a = a_min if a_min is not None else float("-inf")
    lo_b = b_min if b_min is not None else float("-inf")
    hi_a = a_max if a_max is not None else float("inf")
    hi_b = b_max if b_max is not None else float("inf")
    return max(lo_a, lo_b) <= min(hi_a, hi_b)


def could_match_same_device(a: IndexMetadata, b: IndexMetadata) -> bool:
    """Return True if a single device could match both images.

    Mirrors the per-device filters zigpy applies in ``check_compatibility``
    before its runtime collision check (zigpy/ota/__init__.py). Two images
    cannot collide at runtime if their constraints are mutually exclusive:
    disjoint ``model_names``/``manufacturer_names``, or non-overlapping
    hardware/current-file-version ranges.

    A side that is empty/None acts as "any device" for that constraint.
    """
    # A device queries with a single (manufacturer_id, image_type) pair, so
    # images differing there can never match the same device. Note: callers
    # currently group by these fields already, but we check explicitly.
    if (a.manufacturer_id, a.image_type) != (b.manufacturer_id, b.image_type):
        return False

    if a.model_names and b.model_names and not set(a.model_names) & set(b.model_names):
        return False

    if (
        a.manufacturer_names
        and b.manufacturer_names
        and not set(a.manufacturer_names) & set(b.manufacturer_names)
    ):
        return False

    if not _ranges_overlap(
        a.min_hardware_version,
        a.max_hardware_version,
        b.min_hardware_version,
        b.max_hardware_version,
    ):
        return False

    # Current-version ranges carry the implicit ceiling of file_version - 1:
    # an image is only ever offered to devices running a version below its own
    if not _ranges_overlap(
        a.min_current_file_version,
        effective_max_current_version(a.file_version, a.max_current_file_version),
        b.min_current_file_version,
        effective_max_current_version(b.file_version, b.max_current_file_version),
    ):
        return False

    return True


def _find_colliding_components(
    entries: list[tuple[str, IndexMetadata]],
) -> list[list[tuple[str, IndexMetadata]]]:
    """Partition entries into components that could collide at zigpy runtime.

    Uses union-find to merge any pair of entries whose constraints overlap
    via :func:`could_match_same_device`. Returns only components that
    contain more than one unique checksum, i.e. real collisions.
    """
    n = len(entries)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in itertools.combinations(range(n), 2):
        if not could_match_same_device(entries[i][1], entries[j][1]):
            continue
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    components: dict[int, list[tuple[str, IndexMetadata]]] = {}
    for i, entry in enumerate(entries):
        components.setdefault(find(i), []).append(entry)

    return [
        component
        for component in components.values()
        if len({meta.checksum_sha3_256 for _, meta in component}) >= 2
    ]


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
        # If only one unique checksum, no collision is possible
        if len(checksum_buckets) < 2:
            continue

        entries = [entry for bucket in checksum_buckets.values() for entry in bucket]

        for component in _find_colliding_components(entries):
            collisions.append(
                CollisionInfo(
                    manufacturer_id=mfr_id,
                    image_type=img_type,
                    file_version=file_ver,
                    specificity=specificity,
                    images=tuple(component),
                )
            )

            image_paths = [path for path, _ in component]
            LOGGER.warning(
                "Multiple unique OTA images for manufacturer_id=0x%04X, "
                "image_type=0x%04X, version=0x%08X with specificity=%d exist. "
                "It is not possible to tell which image is correct so zigpy will "
                "ignore all %d colliding images at runtime. Images: %s",
                mfr_id,
                img_type,
                file_ver,
                specificity,
                len(component),
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
