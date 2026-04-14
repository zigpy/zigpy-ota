"""Utility functions for downloading and extracting OTA files."""

from __future__ import annotations

import io
import logging
import os
import re
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests
import urllib3

from zigpy_ota.const import IMAGES_PATH

LOGGER = logging.getLogger(__name__)

# Maximum file size for OTA images (2 MB)
MAX_FILE_SIZE = 2 * 1024 * 1024
# Chunk size for streaming downloads
CHUNK_SIZE = 8192
# Error message for file size limit
MAX_SIZE_ERROR = f"maximum allowed size ({MAX_FILE_SIZE} bytes / 2 MB)"

# GitHub URL patterns to normalize to raw.githubusercontent.com.
# Order matters: more specific patterns (refs/heads, refs/tags) must come before
# the catch-all /raw/ pattern. Each regex captures (owner/repo) and (remaining path).
_GITHUB_RAW_URL_PATTERNS: list[re.Pattern[str]] = [
    # github.com/{owner}/{repo}/blob/{ref}/{path}
    re.compile(r"^https://github\.com/([^/]+/[^/]+)/blob/(.+)$"),
    # github.com/{owner}/{repo}/raw/refs/heads/{branch}/{path}
    re.compile(r"^https://github\.com/([^/]+/[^/]+)/raw/refs/heads/(.+)$"),
    # github.com/{owner}/{repo}/raw/refs/tags/{tag}/{path}
    re.compile(r"^https://github\.com/([^/]+/[^/]+)/raw/refs/tags/(.+)$"),
    # github.com/{owner}/{repo}/raw/{ref}/{path} (catch-all)
    re.compile(r"^https://github\.com/([^/]+/[^/]+)/raw/(.+)$"),
]


def normalize_github_url(url: str) -> str:
    """Normalize GitHub URLs to raw.githubusercontent.com direct download URLs.

    Converts various GitHub URL formats to the canonical raw.githubusercontent.com
    form, which provides direct file downloads without HTML wrappers.

    Supported conversions:
    - github.com/{owner}/{repo}/blob/{ref}/{path}
      → raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}
    - github.com/{owner}/{repo}/raw/refs/heads/{branch}/{path}
      → raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}
    - github.com/{owner}/{repo}/raw/refs/tags/{tag}/{path}
      → raw.githubusercontent.com/{owner}/{repo}/{tag}/{path}
    - github.com/{owner}/{repo}/raw/{ref}/{path}
      → raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}

    Args:
        url: URL to normalize

    Returns:
        Normalized URL (unchanged if not a recognized GitHub pattern)
    """
    for pattern in _GITHUB_RAW_URL_PATTERNS:
        match = pattern.match(url)
        if match:
            normalized = (
                f"https://raw.githubusercontent.com/{match.group(1)}/{match.group(2)}"
            )
            LOGGER.info(f"Normalized GitHub URL: {url} → {normalized}")
            return normalized

    return url


def save_ota_file(
    ota_content: bytes, manufacturer_directory: str, filename: str
) -> Path:
    """Save OTA file to the appropriate directory with path traversal protection.

    Args:
        ota_content: Binary content of the OTA file
        manufacturer_directory: Manufacturer name (used as subdirectory)
        filename: Filename for the OTA file

    Returns:
        Path to the saved file

    Raises:
        ValueError: If path traversal is detected in the filename
    """
    target_dir = IMAGES_PATH / manufacturer_directory
    target_dir.mkdir(parents=True, exist_ok=True)

    image_path = target_dir / filename

    # Prevent path traversal by ensuring the resolved path is within IMAGES_PATH
    try:
        resolved_path = image_path.resolve()
        resolved_path.relative_to(IMAGES_PATH.resolve())
    except ValueError as e:
        raise ValueError(
            f"Invalid filename - path traversal detected: {filename}"
        ) from e

    with open(image_path, "wb") as f:
        f.write(ota_content)

    LOGGER.info(f"Saved OTA file to: {image_path}")
    return image_path


def download_ota_file(download_url: str) -> bytes:
    """Download a file from a URL with security checks.

    Validates URL scheme, enforces file size limits, and supports streaming
    downloads. Falls back to unverified SSL if verification fails. Uses GitHub
    PAT authentication (GH_TOKEN or GITHUB_TOKEN env var) for GitHub URLs.

    Args:
        download_url: URL to download from (must be http:// or https://)

    Returns:
        Binary content of the downloaded file

    Raises:
        ValueError: If URL scheme is invalid or file exceeds size limit
        requests.HTTPError: If HTTP request fails
    """
    # Validate URL scheme to prevent file:// and other dangerous schemes
    parsed_url = urlparse(download_url)
    if parsed_url.scheme not in ("https", "http"):
        raise ValueError(
            f"Invalid URL scheme: {parsed_url.scheme}. Only https:// and http:// are allowed."
        )

    # Download with streaming to check size incrementally
    LOGGER.info(f"Downloading OTA file from: {download_url}")

    # Add GitHub PAT authentication for user-attachments URLs
    headers: dict[str, str] | None = None
    github_token = os.getenv("GITHUB_TOKEN")
    is_github_attachment = (
        parsed_url.scheme == "https"
        and parsed_url.hostname == "github.com"
        and parsed_url.path.startswith("/user-attachments/files/")
        and download_url.startswith("https://github.com/user-attachments/files/")
    )

    if is_github_attachment and github_token:
        headers = {"Authorization": f"Bearer {github_token}"}
        LOGGER.info("Using GitHub authentication for user-attachments download")

    # Try with SSL verification first, fallback to unverified if needed
    try:
        response = requests.get(
            download_url, timeout=30, verify=True, stream=True, headers=headers
        )
        response.raise_for_status()
    except requests.exceptions.SSLError as e:
        LOGGER.warning(
            f"SSL verification failed for {download_url}: {e}. "
            "Retrying without SSL verification. "
            "WARNING: This is insecure and should only be used for self-signed certificates."
        )
        # Suppress urllib3 InsecureRequestWarning since we're logging our own warning
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        response = requests.get(download_url, timeout=30, verify=False, stream=True)
        response.raise_for_status()

    # Check Content-Length header if available
    content_length = response.headers.get("Content-Length")
    if content_length and int(content_length) > MAX_FILE_SIZE:
        raise ValueError(
            f"File size ({int(content_length)} bytes) exceeds {MAX_SIZE_ERROR}"
        )

    # Download in chunks and enforce size limit
    chunks = []
    total_size = 0

    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
        if chunk:  # filter out keep-alive new chunks
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                raise ValueError(f"Downloaded file size exceeds {MAX_SIZE_ERROR}")
            chunks.append(chunk)

    content = b"".join(chunks)
    LOGGER.info(f"Downloaded {total_size} bytes")

    return content


def extract_ota_from_zip(content: bytes) -> tuple[bytes, str] | None:
    """Extract OTA file from ZIP archive with validation.

    Validates the ZIP contains exactly one valid OTA file (ignoring metadata
    and hidden files), checks for zip bombs, and prevents path traversal.

    Args:
        content: Binary content to extract from (may or may not be a ZIP)

    Returns:
        Tuple of (ota_content, filename) if valid ZIP, None if not a ZIP file

    Raises:
        ValueError: If ZIP is invalid, contains wrong number of files, or exceeds size limits
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zip_file:
            file_list = zip_file.namelist()
            LOGGER.info(f"Found ZIP archive with {len(file_list)} file(s): {file_list}")

            if not file_list:
                raise ValueError("ZIP archive contains no files")

            # Filter out metadata and hidden files (e.g., __MACOSX, .DS_Store)
            valid_files = [
                f
                for f in file_list
                if not f.startswith("__MACOSX/")
                and not f.startswith(".")
                and not f.endswith("/")  # Skip directories
            ]

            if not valid_files:
                raise ValueError(
                    f"ZIP archive contains no valid OTA files (only metadata/hidden files): {file_list}"
                )

            if len(valid_files) > 1:
                raise ValueError(
                    f"ZIP archive must contain exactly 1 OTA file, found {len(valid_files)}: {valid_files}"
                )

            # Extract the single file
            filename = valid_files[0]

            # Prevent absolute paths in ZIP (relative paths will be validated in save_ota_file)
            if Path(filename).is_absolute():
                raise ValueError(
                    f"Invalid filename in ZIP archive (absolute path not allowed): {filename}"
                )

            # Check uncompressed size to prevent zip bombs
            file_info = zip_file.getinfo(filename)
            if file_info.file_size > MAX_FILE_SIZE:
                raise ValueError(
                    f"Extracted file size ({file_info.file_size} bytes) exceeds {MAX_SIZE_ERROR}"
                )

            LOGGER.info(f"Extracting OTA file from ZIP: {filename}")
            ota_content = zip_file.read(filename)

            # Double-check actual extracted size (in case metadata was wrong)
            if len(ota_content) > MAX_FILE_SIZE:
                raise ValueError(
                    f"Extracted file size ({len(ota_content)} bytes) exceeds {MAX_SIZE_ERROR}"
                )

            return ota_content, filename

    except zipfile.BadZipFile:
        # Not a ZIP file, return None
        return None
    except ValueError as e:
        # Log validation errors and re-raise
        LOGGER.error(f"Invalid ZIP archive: {e}")
        raise
    except Exception as e:
        LOGGER.error(f"Error extracting from ZIP: {e}")
        raise
