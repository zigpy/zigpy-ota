"""Constants for issue parsing."""

from enum import StrEnum


class IssueSection(StrEnum):
    """Known section headers in GitHub issue markdown."""

    OTA_FILE = "OTA file"
    OTA_IMAGE_URL = "OTA image URL"
    MANUFACTURER_NAME = "Manufacturer name"  # Removed from template, kept for old ones
    OFFICIAL_SOURCE = "Provided URL is an official source from the manufacturer"
    EXISTING_IMAGES = "How to handle existing images of the same type"
    THIRD_PARTY_DOWNLOAD = "Third-party download (external hosting)"
    RELEASE_NOTES = "Release notes"
    OPTIONAL_METADATA = "Optional metadata"
    CHECKLIST = "Checklist"
    ADDITIONAL_INFORMATION = "Additional information"


KNOWN_SECTION_HEADERS: set[str] = {s.value for s in IssueSection}
