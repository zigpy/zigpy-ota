"""Constants and configuration values for zigpy-ota."""

from __future__ import annotations

from pathlib import Path

# Path Constants
# Directory where OTA firmware images are stored, organized by manufacturer
IMAGES_PATH = Path("images")

# Output path for the generated zigpy JSON metadata index
ZIGPY_OTA_METADATA_OUTPUT_PATH = Path("zigpy_ota.json")

# Output path for the generated Zigbee2MQTT JSON metadata index
Z2M_OTA_METADATA_OUTPUT_PATH = Path("z2m_ota.json")

# Output path for the generated markdown index (human-readable)
MARKDOWN_OTA_METADATA_OUTPUT_PATH = Path("markdown.md")

# Repository Configuration
# Default git branch/tag for generating GitHub raw URLs
DEFAULT_GITHUB_REF = "dev"

# Base URL for pull requests
GITHUB_PR_BASE_URL = "https://github.com/zigpy/zigpy-ota/pull"

# Manufacturer fallback directory for unknown or unmapped manufacturer IDs
FALLBACK_MANUFACTURER_DIRECTORY = "other"


def get_github_raw_base_url(github_ref: str) -> str:
    """Construct the GitHub raw base URL for the given git ref (tag or branch)."""
    return f"https://raw.githubusercontent.com/zigpy/zigpy-ota/{github_ref}/images"


# Example/Template Values for Metadata Generation
# Placeholder URL used when generating stub YAML metadata files
METADATA_EXAMPLE_URL = "http://example.com/path/to/zigbee.ota"

# Placeholder release notes used when generating stub YAML metadata files
METADATA_EXAMPLE_RELEASE_NOTES = (
    "- Fixed bugs\n- Improved performance\n- Added new features"
)
