from __future__ import annotations

import logging
import re

from zigpy_ota.actions.markdown.utils import format_hex_dec, format_list_or_str
from zigpy_ota.actions.metadata.stale_validation import is_dominated_by
from zigpy_ota.models.index_metadata import IndexMetadata
from zigpy_ota.models.issue_model import ExistingImagesHandling
from zigpy_ota.models.pr_result import PrepareResult
from zigpy_ota.models.yaml_metadata import YamlMetadataThirdParty

LOGGER = logging.getLogger(__name__)


def format_image_info(
    filename: str,
    metadata: IndexMetadata,
    new_version: int,
    auto_min_version: int | None = None,
    yaml_min_version: int | None = None,
    is_stale: bool = False,
) -> str:
    """Format image information from metadata for markdown display.

    Args:
        filename: Name of the OTA image file
        metadata: IndexMetadata containing image information
        new_version: New file version for comparison
        auto_min_version: Auto-calculated min_current_file_version (if available)
        yaml_min_version: Min current file version from YAML metadata (if set)
        is_stale: Whether this image would become stale after adding the new image

    Returns:
        Formatted markdown string with image details as sub-bullet points
    """
    # IndexMetadata guarantees all required fields exist with proper types
    file_version_line = (
        f"  - **File Version**: {format_hex_dec(metadata.file_version, '08X')}"
    )

    # Add version comparison
    if new_version > metadata.file_version:
        comparison = " (**older** than PR version)"
    elif new_version < metadata.file_version:
        comparison = " (**newer** than PR version)"
    else:
        comparison = " (**same** as PR version)"
    file_version_line += comparison

    # Add stale indicator
    stale_suffix = " **[stale]**" if is_stale else " **[not stale]**"

    lines = [
        f"- `{filename}`{stale_suffix}",
        f"  - **Source File Name**: `{metadata.source_file_name}`",
        file_version_line,
    ]

    # Add note if this version was used for auto_min_version calculation
    if auto_min_version is not None and metadata.file_version == auto_min_version:
        if yaml_min_version == auto_min_version:
            # Auto value was used
            lines.append("    [automatically used for `min_current_file_version`]")
        else:
            # Auto value was calculated but overridden
            lines.append(
                "    [would have been used for `min_current_file_version`, but was overridden]"
            )

    lines.append(f"  - **File Size**: {metadata.file_size:,} bytes")

    return "\n".join(lines)


def generate_pr_markdown(result: PrepareResult) -> str:
    """Generate markdown content for a GitHub PR based on OTA metadata.

    Creates formatted markdown with file information, metadata, and warnings
    about replaced images or file conflicts.

    Args:
        result: PrepareResult containing paths and metadata from PR preparation

    Returns:
        Formatted markdown string for GitHub PR description
    """
    # TODO: clean up / move to markdown utils module?

    # Use metadata from result (already parsed in prepare_pr)
    is_third_party = isinstance(result.yaml_metadata, YamlMetadataThirdParty)

    manufacturer_id = result.ota_metadata.manufacturer_id
    image_type = result.ota_metadata.image_type
    file_version = result.ota_metadata.file_version
    filename = result.filename

    # Get effective hardware versions (YAML overrides OTA if set)
    ota_min_hw = result.ota_metadata.min_hardware_version
    ota_max_hw = result.ota_metadata.max_hardware_version
    yaml_min_hw = result.yaml_metadata.min_hardware_version
    yaml_max_hw = result.yaml_metadata.max_hardware_version

    minimum_hardware_version = yaml_min_hw if yaml_min_hw is not None else ota_min_hw
    maximum_hardware_version = yaml_max_hw if yaml_max_hw is not None else ota_max_hw

    # Build the markdown content
    lines: list[str] = []
    lines.append("## OTA File Submission")
    lines.append("")

    # File information
    lines.append("### File Information")
    lines.append(f"- **Filename**: `{filename}`")
    lines.append(f"- **Original Filename**: `{result.yaml_metadata.source_file_name}`")

    # Display manufacturer information
    if result.manufacturer_name:
        lines.append(f"- **Manufacturer (user provided)**: {result.manufacturer_name}")

    lines.append(f"- **Manufacturer Directory**: `{result.manufacturer_directory}`")
    lines.append(f"- **Manufacturer ID**: {format_hex_dec(manufacturer_id, '04X')}")
    lines.append(f"- **Image Type**: {format_hex_dec(image_type, '04X')}")
    lines.append(f"- **File Version**: {format_hex_dec(file_version, '08X')}")
    lines.append(f"- **File Size**: {result.ota_metadata.file_size:,} bytes")
    if result.ota_metadata.header_string:
        lines.append(f"- **Header String**: `{result.ota_metadata.header_string}`")
    if minimum_hardware_version is not None:
        lines.append(
            f"- **File Min Hardware Version**: {format_hex_dec(minimum_hardware_version, '04X')}"
        )
    if maximum_hardware_version is not None:
        lines.append(
            f"- **File Max Hardware Version**: {format_hex_dec(maximum_hardware_version, '04X')}"
        )

    # Indicate hosting type
    if is_third_party:
        lines.append("- **Hosting**: Third-party download (externally hosted)")
    else:
        lines.append("- **Hosting**: Repository file (hosted in zigpy-ota)")

    # Indicate how existing images are handled
    handling_labels = {
        ExistingImagesHandling.REPLACE: "Replace existing images",
        ExistingImagesHandling.SET_MIN_VERSION: "Keep existing images with version constraint",
        ExistingImagesHandling.KEEP_ALL: "Keep all existing images",
    }
    lines.append(
        f"- **Existing Images Handling**: {handling_labels[result.existing_images_handling]}"
    )

    # Show whether OTA was tested on a physical device
    tested_status = "Yes" if result.checklist.tested_on_device else "No"
    lines.append(f"- **Tested on Device**: {tested_status}")

    lines.append("")

    # Add warning if hardware versions are overridden in YAML
    hw_overrides = []
    if yaml_min_hw is not None and yaml_min_hw != ota_min_hw:
        if ota_min_hw is not None:
            # TODO: tests for this (OTA file with min hw version)
            hw_overrides.append(
                f"- **Min Hardware Version**: Overridden from "
                f"{format_hex_dec(ota_min_hw, '04X')} (OTA file) to "
                f"{format_hex_dec(yaml_min_hw, '04X')} (YAML metadata)"
            )
        else:
            # TODO: Do we even need to warn if OTA has no min hw version?
            hw_overrides.append(
                f"- **Min Hardware Version**: Set to "
                f"{format_hex_dec(yaml_min_hw, '04X')} (YAML metadata) "
                f"(OTA file has no min hardware version)"
            )

    if yaml_max_hw is not None and yaml_max_hw != ota_max_hw:
        if ota_max_hw is not None:
            # TODO: tests for this (OTA file with max hw version)
            hw_overrides.append(
                f"- **Max Hardware Version**: Overridden from "
                f"{format_hex_dec(ota_max_hw, '04X')} (OTA file) to "
                f"{format_hex_dec(yaml_max_hw, '04X')} (YAML metadata)"
            )
        else:
            # TODO: Do we even need to warn if OTA has no max hw version?
            hw_overrides.append(
                f"- **Max Hardware Version**: Set to "
                f"{format_hex_dec(yaml_max_hw, '04X')} (YAML metadata) "
                f"(OTA file has no max hardware version)"
            )

    if hw_overrides:
        lines.append("### ⚠️ Hardware Version Override Warning")
        lines.append("")
        lines.append(
            "The following hardware version(s) from the YAML metadata override "
            "the values from the OTA file:"
        )
        lines.extend(hw_overrides)
        lines.append("")

    # Add warning if we're overwriting an existing file with the same name
    if result.file_existed:
        lines.append("### ⚠️ File Replacement Warning")
        lines.append("")
        # Different messages for different replacement scenarios
        if result.image_path is None:  # Third-party download replacing local file
            lines.append(
                f"The existing local file `{filename}` will be **deleted** from the repository "
                "because it is being replaced by a third-party hosted image."
            )
        elif result.replaced_third_party:  # Local file replacing third-party download
            lines.append(
                f"The existing third-party download for `{filename}` will be **replaced** "
                "by this local file uploaded to the repository."
            )
        else:  # Regular local file overwriting another local file
            lines.append(
                f"This upload will **overwrite** the existing file `{filename}` "
                "(identical OTA image)."
            )
        lines.append("")

    # Add information about deleted or would-be-deleted images
    if result.deletable_images:
        current_version = result.ota_metadata.file_version

        # Create IndexMetadata for the new image to check staleness
        new_image_metadata = IndexMetadata.from_ota_and_yaml(
            result.ota_metadata, result.yaml_metadata, binary_url=""
        )

        if result.existing_images_handling == ExistingImagesHandling.REPLACE:
            lines.append("### Deleted Images")
            lines.append("")
            lines.append("The following existing image(s) were deleted:")
        else:
            lines.append("### Note: Existing Images Found")
            lines.append("")
            lines.append(
                "The following existing image(s) with the same manufacturer ID and image type were found:"
            )

        for filename, metadata in result.deletable_images.items():
            lines.append(
                format_image_info(
                    filename=filename,
                    metadata=metadata,
                    new_version=current_version,
                    auto_min_version=result.auto_min_version,
                    yaml_min_version=result.yaml_metadata.min_current_file_version,
                    is_stale=is_dominated_by(metadata, new_image_metadata),
                )
            )
        lines.append("")

    # Add note about auto-calculated min_current_file_version
    if result.auto_min_version is not None:
        lines.append("")
        # The YAML metadata has auto_min_version injected if the user did not specify it manually.
        # If the user did specify it, we need to warn them if it differs from the auto-calculated value.
        yaml_min_version = result.yaml_metadata.min_current_file_version

        if yaml_min_version == result.auto_min_version:
            # Auto-calculated value was used
            lines.append(
                f"**Note**: `min_current_file_version` was automatically set to "
                f"{format_hex_dec(result.auto_min_version, '08X')}"
            )
        elif yaml_min_version is not None:
            # User manually specified a different value
            lines.append(
                f"⚠️ **Warning**: `min_current_file_version` was manually set to "
                f"{format_hex_dec(yaml_min_version, '08X')}, "
                f"but the automatic calculation suggests "
                f"{format_hex_dec(result.auto_min_version, '08X')} "
                f"(the highest existing version below the new version). "
                f"Please verify this is intentional. "
                f"If you want to manually manage version constraints, consider using the "
                f'"Keep all existing images without automatic version constraints" option instead.'
            )

    # Metadata from YAML/issue
    metadata_lines = []

    if manufacturers := result.yaml_metadata.manufacturer_names:
        metadata_lines.append(
            f"- **Manufacturer Names**: {format_list_or_str(manufacturers)}"
        )

    if models := result.yaml_metadata.model_names:
        metadata_lines.append(f"- **Model Names**: {format_list_or_str(models)}")

    if url := result.yaml_metadata.source_url:
        metadata_lines.append(f"- **Source URL**: {url}")

    # Only add the "### Metadata" header if there's actual content
    if metadata_lines:
        lines.append("### Metadata")
        lines.extend(metadata_lines)

    # Optional metadata fields
    optional_fields = []
    metadata_field_configs = [
        (result.yaml_metadata.min_hardware_version, "Min Hardware Version", "04X"),
        (result.yaml_metadata.max_hardware_version, "Max Hardware Version", "04X"),
        (
            result.yaml_metadata.min_current_file_version,
            "Min Current File Version",
            "08X",
        ),
        (
            result.yaml_metadata.max_current_file_version,
            "Max Current File Version",
            "08X",
        ),
        (result.yaml_metadata.specificity, "Specificity", None),
    ]

    for field_value, field_label, hex_format in metadata_field_configs:
        if field_value is not None:
            if hex_format:
                optional_fields.append(
                    f"- **{field_label}**: {format_hex_dec(field_value, hex_format)}"
                )
            else:
                optional_fields.append(f"- **{field_label}**: `{field_value}`")

    if optional_fields:
        lines.append("")
        lines.append("### Additional Metadata")
        lines.extend(optional_fields)

    if release_notes := result.yaml_metadata.release_notes:
        lines.append("")
        lines.append("### Release Notes")
        lines.append(release_notes)

    lines.append("")
    return "\n".join(lines)


def generate_commit_message(result: PrepareResult) -> str:
    """Generate commit message content based on OTA metadata.

    Creates a commit message with the same content as the PR markdown but with
    markdown formatting stripped (## headers, **bold**, `backticks`).

    Args:
        result: PrepareResult containing paths and metadata from PR preparation

    Returns:
        Formatted string for git commit message
    """
    # Generate PR markdown (includes all sections)
    markdown = generate_pr_markdown(result)

    # Strip markdown formatting:
    # - Remove ## and ### header prefixes
    # - Remove **bold** markers
    # - Remove `backticks`
    text = re.sub(r"^#{1,3}\s*", "", markdown, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)

    return text
