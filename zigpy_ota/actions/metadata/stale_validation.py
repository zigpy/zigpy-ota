"""Stale image detection for OTA images in the index.

This module provides functions to detect stale OTA images - images that can never
be selected by zigpy because a newer image that matches the same set of devices
always takes priority. zigpy orders upgrade candidates by (file_version,
specificity) descending, so specificity only breaks ties between equal versions
and can never make an older version preferred over a newer one.

Stale images are effectively dead code in the index: they consume space but will
never be used for any device. Detecting them helps maintain a clean index.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from zigpy_ota.actions.metadata.constraints import (
    effective_max_current_version,
    unreachable_reasons,
)
from zigpy_ota.models.index_metadata import IndexMetadata

LOGGER = logging.getLogger(__name__)


def _newer_matches_all_older_devices(
    older: IndexMetadata, newer: IndexMetadata
) -> bool:
    """Check if newer image matches all devices that older image matches.

    For newer to match all devices older matches, newer's constraints must be
    "broader" (less restrictive) or equal to older's constraints.

    Args:
        older: The older image (lower file_version)
        newer: The newer image (higher file_version)

    Returns:
        True if newer matches whenever older matches, False otherwise
    """
    # model_names: newer must include all of older's models (or have no constraint)
    if older.model_names is None:
        # Older matches ALL models, newer must too
        if newer.model_names is not None:
            return False
    else:
        # Older matches specific models
        if newer.model_names is not None:
            # Newer must include all of older's models
            if not set(older.model_names).issubset(set(newer.model_names)):
                return False
        # If newer.model_names is None, it matches all models -> OK

    # manufacturer_names: same logic as model_names
    if older.manufacturer_names is None:
        if newer.manufacturer_names is not None:
            return False
    else:
        if newer.manufacturer_names is not None:
            if not set(older.manufacturer_names).issubset(
                set(newer.manufacturer_names)
            ):
                return False

    # min_current_file_version: newer must accept lower versions than older
    # If older has no constraint (matches all), newer must also have no constraint
    # If older requires version >= X, newer must require version >= Y where Y <= X
    if older.min_current_file_version is None:
        if newer.min_current_file_version is not None:
            return False  # Older matches all, newer only matches >= some version
    else:
        if newer.min_current_file_version is not None:
            if newer.min_current_file_version > older.min_current_file_version:
                return False

    # max_current_file_version: newer must accept every current version older
    # accepts, comparing effective ceilings (each capped at the image's own
    # file_version - 1, since an image is only offered below its own version)
    older_max = effective_max_current_version(
        older.file_version, older.max_current_file_version
    )
    newer_max = effective_max_current_version(
        newer.file_version, newer.max_current_file_version
    )
    if newer_max < older_max:
        return False

    # min_hardware_version: newer must accept lower hardware versions
    if older.min_hardware_version is None:
        if newer.min_hardware_version is not None:
            return False
    else:
        if newer.min_hardware_version is not None:
            if newer.min_hardware_version > older.min_hardware_version:
                return False

    # max_hardware_version: newer must accept higher hardware versions
    if older.max_hardware_version is None:
        if newer.max_hardware_version is not None:
            return False
    else:
        if newer.max_hardware_version is not None:
            if newer.max_hardware_version < older.max_hardware_version:
                return False

    return True


def is_dominated_by(older: IndexMetadata, newer: IndexMetadata) -> bool:
    """Check if older image is dominated by newer image.

    An image is dominated if a newer image:
    1. Is for the same (manufacturer_id, image_type)
    2. Has higher file_version
    3. Matches ALL devices that older matches

    Specificity is deliberately NOT considered: zigpy sorts upgrade candidates
    by (file_version, specificity) descending, so a newer version always
    outranks an older one regardless of specificity.

    Args:
        older: The older image being checked for staleness
        newer: A newer image that might dominate it

    Returns:
        True if newer dominates older (older is stale), False otherwise
    """
    # Check manufacturer_id/image_type: only images for the same device type
    # can dominate each other. Note: compute_stale_images already ensures this
    # by grouping, but we check explicitly for other callers
    if (newer.manufacturer_id, newer.image_type) != (
        older.manufacturer_id,
        older.image_type,
    ):
        return False

    # Check file_version: newer must have higher version
    # Note: compute_stale_images already ensures this by sorting, but we check
    # explicitly for other callers
    if newer.file_version <= older.file_version:
        return False

    # Check if newer matches all devices older matches
    if not _newer_matches_all_older_devices(older, newer):
        return False

    return True


def has_narrower_names(older: IndexMetadata, newer: IndexMetadata) -> bool:
    """Check if a dominated image looks intentionally scoped to devices.

    A dominated image with model/manufacturer-name constraints its dominator
    lacks may signal maintainer intent gone wrong: if the older image was
    meant to be exclusive to those devices, the NEWER image needs constraints
    (zigpy offers the newer image to them regardless of the older's names).
    """
    return bool(
        (older.model_names and not newer.model_names)
        or (older.manufacturer_names and not newer.manufacturer_names)
    )


def narrower_names_hint(older: IndexMetadata, newer: IndexMetadata) -> str:
    """Return a log hint when a dominated image looks intentionally scoped."""
    if has_narrower_names(older, newer):
        return (
            " (the stale image has device-name constraints the dominating one"
            " lacks - if it was meant to be exclusive to those devices, the"
            " newer image needs constraints)"
        )
    return ""


def compute_stale_images(
    metadata: dict[str, IndexMetadata],
) -> set[str]:
    """Find images that can never be used because newer images always take priority.

    An image is stale if there exists a newer image (higher file_version, same
    manufacturer_id and image_type) that matches all devices the older image
    matches. zigpy then always prefers the newer image, making the older image
    effectively unused.

    Args:
        metadata: Dictionary mapping paths to IndexMetadata

    Returns:
        Set of paths for stale images
    """
    stale: set[str] = set()

    # Group by (manufacturer_id, image_type)
    groups: dict[tuple[int, int], list[tuple[str, IndexMetadata]]] = defaultdict(list)
    for path, index_meta in metadata.items():
        key = (index_meta.manufacturer_id, index_meta.image_type)
        groups[key].append((path, index_meta))

    for (mfr_id, img_type), images in groups.items():
        # Sort by file_version descending (newest first)
        sorted_images = sorted(images, key=lambda x: x[1].file_version, reverse=True)

        # For each image, check if any newer image dominates it
        for i, (path, meta) in enumerate(sorted_images):
            newer_images = sorted_images[:i]  # All images with higher file_version

            for newer_path, newer_meta in newer_images:
                if is_dominated_by(meta, newer_meta):
                    stale.add(path)
                    LOGGER.info(
                        "Image %s (version 0x%08X) is stale: dominated by %s "
                        "(version 0x%08X) for manufacturer_id=0x%04X, "
                        "image_type=0x%04X%s",
                        path,
                        meta.file_version,
                        newer_path,
                        newer_meta.file_version,
                        mfr_id,
                        img_type,
                        narrower_names_hint(meta, newer_meta),
                    )
                    break  # Only need one dominating image to mark as stale

    return stale


def validate_unreachable_images(
    metadata: dict[str, IndexMetadata],
    fail_on_unreachable: bool = False,
) -> list[str]:
    """Find enabled images that can never be offered to any device.

    An image is unreachable when its effective current-version range is empty
    (zigpy only offers an image when the device's current version is below the
    image's own file_version, so e.g. min_current_file_version >= file_version
    or a file_version of 0 can never match) or when its hardware-version range
    is empty. Disabled images are skipped: they are intentionally kept in the
    repo and never ship in an index.

    Args:
        metadata: Dictionary mapping paths to IndexMetadata
        fail_on_unreachable: If True, raise error when unreachable images
            exist. If False, log a warning.

    Returns:
        List of "path: reason" strings describing any unreachable images
    """
    unreachable: list[str] = []

    for path, meta in metadata.items():
        if meta.disabled:
            continue

        unreachable.extend(
            f"{path}: {reason}"
            for reason in unreachable_reasons(
                file_version=meta.file_version,
                min_current_file_version=meta.min_current_file_version,
                max_current_file_version=meta.max_current_file_version,
                min_hardware_version=meta.min_hardware_version,
                max_hardware_version=meta.max_hardware_version,
            )
        )

    if unreachable:
        message = "Unreachable images detected:\n" + "\n".join(
            f"  - {entry}" for entry in unreachable
        )
        if fail_on_unreachable:
            raise ValueError(message)
        LOGGER.warning(message)

    return unreachable
