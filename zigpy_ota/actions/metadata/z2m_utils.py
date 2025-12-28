"""Utilities for Zigbee2MQTT (Z2M) index generation."""

from __future__ import annotations

from collections import defaultdict

from zigpy_ota.models.index_metadata import IndexMetadata


def compute_max_file_versions(
    metadata: dict[str, IndexMetadata],
) -> dict[str, int]:
    """Compute max_current_file_version for images in version-constrained groups.

    For images that share the same manufacturer ID and image type, if any image
    in the group has min_current_file_version set, all images except the newest
    one (highest file_version) should have max_current_file_version set to
    file_version - 1.

    Z2M's getImageMeta() uses Array.find() to return the first matching image
    where `current.fileVersion >= minFileVersion && current.fileVersion <= maxFileVersion`.
    Without maxFileVersion, multiple images could match and Z2M picks the first one,
    which may not be the correct upgrade target.

    Example with three images (v100, v200, v300) where step-by-step upgrades are required:
    - v100: no constraints
    - v200: minFileVersion=100, maxFileVersion=199
    - v300: minFileVersion=200, maxFileVersion=299

    A device on v100:
    - v100: matches, but rejected later (not an upgrade) (others aren't checked after a match)
    - v200: matches (100 >= 100 and 100 <= 199) - correct upgrade target
    - v300: doesn't match (100 < 200)

    Setting maxFileVersion = fileVersion - 1 ensures only devices that need
    this specific intermediate version will match it, enforcing the upgrade path.

    Args:
        metadata: Dictionary of IndexMetadata (pre-filtered, non-disabled entries only)

    Returns:
        Dictionary mapping image paths to computed max_current_file_version values.
        Only includes entries that need max_current_file_version set.
    """
    # Group images by (manufacturer_id, image_type)
    # TODO: Technically, we should also group by all other options (like model names)
    groups: dict[tuple[int, int], list[tuple[str, IndexMetadata]]] = defaultdict(list)
    for image_path, index_meta in metadata.items():
        key = (index_meta.manufacturer_id, index_meta.image_type)
        groups[key].append((image_path, index_meta))

    computed_max_versions: dict[str, int] = {}

    for (_mfr_id, _img_type), images in groups.items():
        # Check if any image in this group has min_current_file_version set
        has_min_version_constraint = any(
            meta.min_current_file_version is not None for _, meta in images
        )

        if not has_min_version_constraint:
            continue

        # Sort by file_version ascending
        sorted_images = sorted(images, key=lambda x: x[1].file_version)

        # For all images except the newest, set max_current_file_version
        for image_path, index_meta in sorted_images[:-1]:
            # Only set if not already explicitly set
            if index_meta.max_current_file_version is None:
                computed_max_versions[image_path] = index_meta.file_version - 1

    return computed_max_versions
