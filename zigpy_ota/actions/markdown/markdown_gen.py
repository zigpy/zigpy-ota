"""Markdown index generation for zigpy-ota.

Generates a human-readable markdown index of all OTA firmware images.
"""

from __future__ import annotations

from pathlib import Path

from zigpy_ota.actions.markdown.utils import format_hex_dec, format_list_or_str
from zigpy_ota.const import GITHUB_PR_BASE_URL
from zigpy_ota.models.index_metadata import IndexMetadata
from zigpy_ota.models.yaml_metadata import Channel


def save_metadata_to_markdown_file(
    metadata: list[tuple[str, IndexMetadata, bool, bool]],
    output_file: Path,
    channel: Channel,
) -> None:
    """Save the parsed metadata to a human-readable markdown file.

    Groups firmware images by manufacturer directory and displays
    key metadata for each image.

    Args:
        metadata: List of (path, IndexMetadata, is_stale, is_disabled) tuples
        output_file: Path to output markdown file
        channel: Release channel this index was generated for
    """
    lines: list[str] = []
    lines.append("# zigpy-ota Firmware Index")
    lines.append("")
    lines.append(
        "This is a human-readable index of all OTA firmware images "
        "in the zigpy-ota repository."
    )
    lines.append("")
    lines.append(f"**Channel:** {channel.value}\\")

    # Count enabled and disabled images
    disabled_count = sum(1 for _, _, _, is_disabled in metadata if is_disabled)
    enabled_count = len(metadata) - disabled_count
    if disabled_count > 0:
        lines.append(
            f"**Total firmware images:** {enabled_count} enabled + {disabled_count} disabled"
        )
    else:
        lines.append(f"**Total firmware images:** {enabled_count}")
    lines.append("")

    # Group by manufacturer directory
    current_manufacturer: str | None = None

    # TODO: Divider per image type? (##)
    for image_path, index_meta, is_stale, is_disabled in metadata:
        manufacturer_dir = image_path.split("/")[0]

        # Add manufacturer header when it changes
        if manufacturer_dir != current_manufacturer:
            current_manufacturer = manufacturer_dir
            lines.append(f"## {manufacturer_dir}")
            lines.append("")

        # Firmware entry
        filename = image_path.split("/")[-1]
        markers = []
        if is_disabled:
            markers.append("**[disabled]**")
        if is_stale:
            markers.append("**[stale]**")
        marker_str = " " + " ".join(markers) if markers else ""
        lines.append(f"### `{filename}`{marker_str}")
        lines.append("")

        # Original file name at top
        lines.append(f"- **Original File Name**: `{index_meta.source_file_name}`")

        # Core identifiers
        lines.append(
            f"- **Manufacturer ID**: {format_hex_dec(index_meta.manufacturer_id, '04X')}"
        )
        lines.append(
            f"- **Image Type**: {format_hex_dec(index_meta.image_type, '04X')}"
        )
        lines.append(
            f"- **File Version**: {format_hex_dec(index_meta.file_version, '08X')}"
        )
        lines.append(f"- **File Size**: {index_meta.file_size:,} bytes")
        lines.append(f"- **Checksum SHA3-256**: `{index_meta.checksum_sha3_256}`")
        lines.append(f"- **Checksum SHA512**: `{index_meta.checksum_sha512}`")
        lines.append(f"- **Binary URL**: {index_meta.binary_url}")

        if index_meta.source_url:
            lines.append(f"- **Source URL**: {index_meta.source_url}")
        if index_meta.third_party_download:
            lines.append("- **Hosting**: Third-party (externally hosted)")

        # Header string if present
        if index_meta.header_string:
            lines.append(f"- **Header String**: `{index_meta.header_string}`")

        # Hardware version constraints
        if index_meta.min_hardware_version is not None:
            lines.append(
                f"- **Min Hardware Version**: "
                f"{format_hex_dec(index_meta.min_hardware_version, '04X')}"
            )
        if index_meta.max_hardware_version is not None:
            lines.append(
                f"- **Max Hardware Version**: "
                f"{format_hex_dec(index_meta.max_hardware_version, '04X')}"
            )

        # File version constraints
        if index_meta.min_current_file_version is not None:
            lines.append(
                f"- **Min Current File Version**: "
                f"{format_hex_dec(index_meta.min_current_file_version, '08X')}"
            )
        if index_meta.max_current_file_version is not None:
            lines.append(
                f"- **Max Current File Version**: "
                f"{format_hex_dec(index_meta.max_current_file_version, '08X')}"
            )

        # Device matching info
        if index_meta.manufacturer_names:
            lines.append(
                f"- **Manufacturer Names**: "
                f"{format_list_or_str(index_meta.manufacturer_names)}"
            )
        if index_meta.model_names:
            lines.append(
                f"- **Model Names**: {format_list_or_str(index_meta.model_names)}"
            )

        # Other optional fields
        if index_meta.specificity is not None:
            lines.append(f"- **Specificity**: {index_meta.specificity}")

        # Release info
        if index_meta.release_notes:
            lines.append("")
            lines.append("**Release Notes:**")
            lines.append("")
            # Indent release notes as blockquote
            for note_line in index_meta.release_notes.split("\n"):
                lines.append(f"> {note_line}")

        if index_meta.release_notes_url:
            lines.append(f"- **Release Notes URL**: {index_meta.release_notes_url}")

        if index_meta.pull_request:
            pr_url = f"{GITHUB_PR_BASE_URL}/{index_meta.pull_request}"
            lines.append(f"- **Pull Request**: [#{index_meta.pull_request}]({pr_url})")

        lines.append("")

    output_file.write_text("\n".join(lines))
