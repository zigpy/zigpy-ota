"""Tests for GitHub issue parsing functionality."""

from __future__ import annotations

from pathlib import Path

import pytest
from syrupy.assertion import SnapshotAssertion

from zigpy_ota.actions.issue.issue_parsing import (
    parse_issue_file,
    parse_issue_file_to_model,
)
from zigpy_ota.models.issue_model import ExistingImagesHandling


@pytest.fixture(
    params=[
        "issue.md",
        "issue_empty.md",
    ]
)
def issue_markdown_file(request: pytest.FixtureRequest) -> Path:
    """Parametrized fixture for all issue markdown test files."""
    return Path("tests/data/gh_issues") / request.param


@pytest.fixture
def issue_path() -> Path:
    """Path to the example issue markdown file."""
    return Path("tests/data/gh_issues/issue.md")


@pytest.fixture
def issue_empty_path() -> Path:
    """Path to the empty example issue markdown file."""
    return Path("tests/data/gh_issues/issue_empty.md")


def test_parse_issue_file_snapshot(
    snapshot: SnapshotAssertion, issue_markdown_file: Path
) -> None:
    """Test that parse_issue_file output matches snapshot."""
    parsed_data = parse_issue_file(issue_markdown_file)
    assert parsed_data == snapshot


def test_parse_issue_model_snapshot(
    snapshot: SnapshotAssertion, issue_markdown_file: Path
) -> None:
    """Test that parse_issue_file_to_model output matches snapshot."""
    issue_data = parse_issue_file_to_model(issue_markdown_file)
    # Convert to dict for snapshot comparison
    assert issue_data.to_dict() == snapshot


def test_parse_issue_model_attributes(issue_path: Path) -> None:
    """Test specific attributes of the parsed issue model."""
    issue_data = parse_issue_file_to_model(issue_path)

    # Test OTA file
    assert issue_data.ota_file is not None
    assert issue_data.ota_file.filename == "empty_file.ota.zip"
    assert "github.com" in issue_data.ota_file.url

    # Test OTA image URL
    assert (
        issue_data.ota_image_url == "https://example.com/releases/firmware-v1.2.3.ota"
    )

    # Test manufacturer
    assert issue_data.manufacturer_name == "Third Reality"

    # Test official source
    assert issue_data.is_official_source is True

    # Test existing images handling
    assert issue_data.existing_images_handling == ExistingImagesHandling.KEEP_ALL

    # Test release notes
    assert issue_data.release_notes is not None
    assert "Bug fixes" in issue_data.release_notes

    # Test checklist
    assert issue_data.checklist.supported_format is True
    assert issue_data.checklist.filled_release_notes is True
    assert issue_data.checklist.tested_on_device is False

    # Test additional info
    assert issue_data.additional_information == "Test"

    # Test optional metadata
    assert issue_data.optional_metadata is None


@pytest.mark.parametrize(
    "issue_empty_path",
    (Path("tests/data/gh_issues/issue_empty.md"),),
)
def test_parse_issue_empty_model_attributes(issue_empty_path: Path) -> None:
    """Test specific attributes of the parsed empty issue model."""
    issue_data = parse_issue_file_to_model(issue_empty_path)

    # Test that empty fields are None
    assert issue_data.ota_file is None
    assert issue_data.ota_image_url is None
    assert issue_data.manufacturer_name is None
    assert issue_data.release_notes is None
    assert issue_data.additional_information is None

    # Test official source checkbox (unchecked)
    assert issue_data.is_official_source is False

    # Test existing images handling (not selected - defaults to KEEP_ALL)
    assert issue_data.existing_images_handling == ExistingImagesHandling.KEEP_ALL

    # Test checklist - only supported_format should be checked
    assert issue_data.checklist.supported_format is True
    assert issue_data.checklist.filled_release_notes is False
    assert issue_data.checklist.tested_on_device is False

    # Test optional metadata
    assert issue_data.optional_metadata is None
