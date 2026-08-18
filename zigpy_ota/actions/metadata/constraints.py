"""Shared, per-image constraint rules.

Pure functions over a single image's matching constraints, usable from both
pipeline stages: index generation (validating the whole repo) and PR
preparation (validating one submission before any files are written).
Cross-image rules (collisions, staleness) inherently need the full index and
live in their own modules; only single-image rules belong here.
"""

from __future__ import annotations


def effective_max_current_version(
    file_version: int, max_current_file_version: int | None
) -> int:
    """Return the highest current version a device may run and still be offered this image.

    zigpy (and Z2M) only offer an image when the device's current version is
    below the image's own file_version, so every image has an implicit ceiling
    of file_version - 1 on top of any explicit max_current_file_version.
    """
    effective = file_version - 1
    if max_current_file_version is not None:
        effective = min(effective, max_current_file_version)
    return effective


def unreachable_reasons(
    *,
    file_version: int,
    min_current_file_version: int | None = None,
    max_current_file_version: int | None = None,
    min_hardware_version: int | None = None,
    max_hardware_version: int | None = None,
) -> list[str]:
    """Return the reasons no device could ever be offered an image with these constraints.

    An image is unreachable when its effective current-version range is empty
    (e.g. min_current_file_version at or above its own file_version, min above
    max, or a file_version of 0) or when its hardware-version range is empty.

    Returns:
        Human-readable reason strings, empty if the constraints are satisfiable
    """
    reasons: list[str] = []

    min_current = min_current_file_version or 0
    max_current = effective_max_current_version(file_version, max_current_file_version)
    if min_current > max_current:
        # Hex to match how versions are written in the issue form and YAML
        # (the effective max is -1 for a file_version of 0 - keep that decimal)
        max_repr = f"0x{max_current:08X}" if max_current >= 0 else str(max_current)
        reasons.append(
            f"empty current-version range - no device version satisfies "
            f"0x{min_current:08X} <= version <= {max_repr} (an image is only "
            f"offered below its own file version, 0x{file_version:08X})"
        )

    if (
        min_hardware_version is not None
        and max_hardware_version is not None
        and min_hardware_version > max_hardware_version
    ):
        reasons.append(
            f"empty hardware-version range - "
            f"min {min_hardware_version} > max {max_hardware_version}"
        )

    return reasons
