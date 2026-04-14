"""Tests for GitHub URL normalization."""

import pytest

from zigpy_ota.actions.pr.download_utils import normalize_github_url


@pytest.mark.parametrize(
    ("input_url", "expected_url"),
    [
        # blob URLs → raw.githubusercontent.com
        pytest.param(
            "https://github.com/Develco-Products/frient_upgrade_images/blob/main/AirQualitySensor_4.0.3.zigbee",
            "https://raw.githubusercontent.com/Develco-Products/frient_upgrade_images/main/AirQualitySensor_4.0.3.zigbee",
            id="blob_main",
        ),
        pytest.param(
            "https://github.com/owner/repo/blob/v1.0/path/to/firmware.ota",
            "https://raw.githubusercontent.com/owner/repo/v1.0/path/to/firmware.ota",
            id="blob_tag",
        ),
        pytest.param(
            "https://github.com/owner/repo/blob/abc123def/firmware.ota",
            "https://raw.githubusercontent.com/owner/repo/abc123def/firmware.ota",
            id="blob_commit_sha",
        ),
        # /raw/refs/heads/ URLs → raw.githubusercontent.com (strip refs/heads/)
        pytest.param(
            "https://github.com/Develco-Products/frient_upgrade_images/raw/refs/heads/main/AirQualitySensor_4.0.3.zigbee",
            "https://raw.githubusercontent.com/Develco-Products/frient_upgrade_images/main/AirQualitySensor_4.0.3.zigbee",
            id="raw_refs_heads_main",
        ),
        pytest.param(
            "https://github.com/owner/repo/raw/refs/heads/develop/path/firmware.ota",
            "https://raw.githubusercontent.com/owner/repo/develop/path/firmware.ota",
            id="raw_refs_heads_develop",
        ),
        # /raw/refs/tags/ URLs → raw.githubusercontent.com (strip refs/tags/)
        pytest.param(
            "https://github.com/owner/repo/raw/refs/tags/v1.0.0/firmware.ota",
            "https://raw.githubusercontent.com/owner/repo/v1.0.0/firmware.ota",
            id="raw_refs_tags",
        ),
        # /raw/ URLs (catch-all) → raw.githubusercontent.com
        pytest.param(
            "https://github.com/owner/repo/raw/main/firmware.ota",
            "https://raw.githubusercontent.com/owner/repo/main/firmware.ota",
            id="raw_main",
        ),
        pytest.param(
            "https://github.com/owner/repo/raw/abc123/path/to/firmware.ota",
            "https://raw.githubusercontent.com/owner/repo/abc123/path/to/firmware.ota",
            id="raw_commit_sha",
        ),
        # URLs that should NOT be modified
        pytest.param(
            "https://raw.githubusercontent.com/owner/repo/main/firmware.ota",
            "https://raw.githubusercontent.com/owner/repo/main/firmware.ota",
            id="already_raw",
        ),
        pytest.param(
            "https://example.com/firmware.ota",
            "https://example.com/firmware.ota",
            id="non_github",
        ),
        pytest.param(
            "https://github.com/user-attachments/files/123/firmware.zip",
            "https://github.com/user-attachments/files/123/firmware.zip",
            id="github_attachment",
        ),
        pytest.param(
            "https://otau.meethue.com/storage/firmware.zigbee",
            "https://otau.meethue.com/storage/firmware.zigbee",
            id="manufacturer_url",
        ),
        pytest.param(
            "http://example.com/firmware.ota",
            "http://example.com/firmware.ota",
            id="http_url",
        ),
    ],
)
def test_normalize_github_url(input_url: str, expected_url: str) -> None:
    assert normalize_github_url(input_url) == expected_url
