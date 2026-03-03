"""Parse GitHub issue markdown to extract OTA submission information."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from zigpy_ota.models.issue_model import ExistingImagesHandling, IssueData


def parse_issue_markdown(markdown_content: str) -> dict[str, Any]:
    """Parse GitHub issue markdown and extract structured data."""
    sections = _split_into_sections(markdown_content)

    parsed_data = {
        "ota_file": _parse_ota_file_section(sections.get("OTA file", "")),
        "ota_image_url": _parse_ota_image_url_section(
            sections.get("OTA image URL", "")
        ),
        "manufacturer_name": _parse_text_section(sections.get("Manufacturer name", "")),
        "existing_images_handling": _parse_existing_images_handling(
            sections.get("How to handle existing images of the same type", "")
        ),
        "third_party_download": _parse_checkbox_section(
            sections.get("Third-party download (external hosting)", "")
        ),
        "release_notes": _parse_text_section(sections.get("Release notes", "")),
        "checklist": _parse_checklist_section(sections.get("Checklist", "")),
        "additional_information": _parse_text_section(
            sections.get("Additional information", "")
        ),
        "optional_metadata": _parse_text_section(sections.get("Optional metadata", "")),
    }

    return parsed_data


def _split_into_sections(markdown_content: str) -> dict[str, str]:
    """Split markdown content into sections based on h3 headers (###)."""
    sections = {}
    current_section: str | None = None
    current_content: list[str] = []

    for line in markdown_content.split("\n"):
        if line.startswith("### "):
            # Save previous section if it exists
            if current_section is not None:
                sections[current_section] = "\n".join(current_content).strip()

            # Start new section
            current_section = line[4:].strip()
            current_content = []
        else:
            if current_section is not None:
                current_content.append(line)

    # Save the last section
    if current_section is not None:
        sections[current_section] = "\n".join(current_content).strip()

    return sections


def _parse_ota_file_section(content: str) -> dict[str, str] | None:
    """Parse the OTA file section to extract file attachment info."""
    if not content or content.lower() == "_no response_":
        return None

    # Match markdown link format: [filename](url)
    match = re.search(r"\[([^]]+)]\(([^)]+)\)", content)
    if match:
        return {"filename": match.group(1), "url": match.group(2)}

    return None


def _parse_ota_image_url_section(content: str) -> str | None:
    """Parse the OTA image URL section."""
    if not content or content.lower() == "_no response_":
        return None

    content = content.strip()

    # Check if it's a valid URL
    if content.startswith("http://") or content.startswith("https://"):
        return content

    return None


def _parse_text_section(content: str) -> str | None:
    """Parse a text section, handling '_no response_' and empty content."""
    if not content or content.lower() == "_no response_":
        return None

    # Strip trailing whitespace from each line to avoid linter issues in YAML
    cleaned = "\n".join(line.rstrip() for line in content.strip().splitlines())

    return cleaned if cleaned else None


def _parse_checkbox_section(content: str) -> bool:
    """Parse a checkbox section and return whether it's checked."""
    if not content:
        return False

    return "- [x]" in content or "- [X]" in content


def _parse_existing_images_handling(content: str) -> ExistingImagesHandling:
    """Parse the dropdown selection for existing images handling.

    Converts the full text from the dropdown to the enum.
    Defaults to KEEP_ALL if no selection is made.

    Args:
        content: The text content from the markdown section

    Returns:
        The ExistingImagesHandling enum (defaults to KEEP_ALL)
    """
    if not content or content.lower() == "_no response_":
        return ExistingImagesHandling.KEEP_ALL

    content_lower = content.lower()
    if "replace existing images" in content_lower:
        return ExistingImagesHandling.REPLACE
    elif "with version constraint" in content_lower:
        return ExistingImagesHandling.SET_MIN_VERSION
    elif "keep all" in content_lower:
        return ExistingImagesHandling.KEEP_ALL

    return ExistingImagesHandling.KEEP_ALL


def _parse_checklist_section(content: str) -> dict[str, bool]:
    """Parse the checklist section to extract checkbox states."""
    checklist = {
        "supported_format": False,
        "filled_release_notes": False,
        "tested_on_device": False,
        "is_official_source": False,
    }

    if not content:
        return checklist

    lines = content.split("\n")
    for line in lines:
        is_checked = "- [x]" in line.lower()

        if "supported format" in line.lower():
            checklist["supported_format"] = is_checked
        elif "filled out the release notes" in line.lower():
            checklist["filled_release_notes"] = is_checked
        elif "tested and verified" in line.lower():
            checklist["tested_on_device"] = is_checked
        elif "official source" in line.lower():
            checklist["is_official_source"] = is_checked

    return checklist


def _read_issue_file(file_path: Path) -> str:
    """Read a GitHub issue markdown file."""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def parse_issue_file(file_path: Path) -> dict[str, Any]:
    """Parse a GitHub issue markdown file."""
    content = _read_issue_file(file_path)
    return parse_issue_markdown(content)


def parse_issue_to_model(markdown_content: str) -> IssueData:
    """Parse GitHub issue markdown and return an IssueData model."""
    data_dict = parse_issue_markdown(markdown_content)
    return IssueData.from_dict(data_dict)


def parse_issue_file_to_model(file_path: Path) -> IssueData:
    """Parse a GitHub issue markdown file and return an IssueData model."""
    content = _read_issue_file(file_path)
    return parse_issue_to_model(content)
