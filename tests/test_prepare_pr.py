"""Tests for prepare-pr CLI command using snapshot testing.

Tests the prepare-pr command which processes GitHub issue submissions,
downloads OTA files, generates YAML metadata, and creates PR markdown.
Validates outputs against snapshots and zigpy schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner, Result
from syrupy.assertion import SnapshotAssertion

from tests.common import validate_ota_index_schema
from zigpy_ota.cli import cli


@pytest.fixture
def issue_hue_old() -> Path:
    """Issue file for old Hue OTA version."""
    return Path("tests/data/gh_issues/issue_hue_old.md")


@pytest.fixture
def issue_hue_new_keep() -> Path:
    """Issue file for new Hue OTA version (keep existing)."""
    return Path("tests/data/gh_issues/issue_hue_new_keep.md")


@pytest.fixture
def issue_hue_new_replace() -> Path:
    """Issue file for new Hue OTA version (replace existing)."""
    return Path("tests/data/gh_issues/issue_hue_new_replace.md")


@pytest.fixture
def issue_hue_old_release_notes_headings() -> Path:
    """Issue file for old Hue OTA version with markdown headings in release notes."""
    return Path("tests/data/gh_issues/issue_hue_old_release_notes_headings.md")


@pytest.fixture
def issue_hue_old_trailing_whitespace() -> Path:
    """Issue file for old Hue OTA version with trailing whitespace in release notes."""
    return Path("tests/data/gh_issues/issue_hue_old_trailing_whitespace.md")


@pytest.fixture
def issue_hue_old_metadata_no_space() -> Path:
    """Issue file for old Hue OTA version with missing spaces after colons in metadata."""
    return Path("tests/data/gh_issues/issue_hue_old_metadata_no_space.md")


@pytest.fixture
def issue_hue_old_reupload() -> Path:
    """Issue file for re-uploading old Hue OTA version (same filename)."""
    return Path("tests/data/gh_issues/issue_hue_old_reupload.md")


@pytest.fixture
def issue_hue_no_metadata() -> Path:
    """Issue file for Hue OTA with no optional metadata fields."""
    return Path("tests/data/gh_issues/issue_hue_no_metadata.md")


@pytest.fixture
def issue_hue_third_party() -> Path:
    """Issue file for third-party download."""
    return Path("tests/data/gh_issues/issue_hue_third_party.md")


@pytest.fixture
def issue_hue_regular_replace_third_party() -> Path:
    """Issue file for regular upload replacing third-party download."""
    return Path("tests/data/gh_issues/issue_hue_regular_replace_third_party.md")


@pytest.fixture
def issue_hue_old_replace() -> Path:
    """Issue file for old Hue OTA version (replace existing - downgrade)."""
    return Path("tests/data/gh_issues/issue_hue_old_replace.md")


@pytest.fixture
def issue_hue_new_auto_version() -> Path:
    """Issue file for new Hue OTA version (set min_current_file_version automatically)."""
    return Path("tests/data/gh_issues/issue_hue_new_auto_version.md")


@pytest.fixture
def ota_hue_old() -> Path:
    """Old version of Hue OTA file."""
    return Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )


@pytest.fixture
def ota_hue_new() -> Path:
    """New version of Hue OTA file."""
    return Path(
        "tests/data/ota_files/fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee"
    )


@pytest.fixture
def ota_hue_newest() -> Path:
    """Newest version of Hue OTA file."""
    return Path(
        "tests/data/ota_files/fake_100B-010C-01002602-ConfLight-Lamps_0012.zigbee"
    )


@pytest.fixture
def issue_hue_new_keep_for_middle() -> Path:
    """Issue file for new Hue OTA version (keep existing - for middle test)."""
    return Path("tests/data/gh_issues/issue_hue_new_keep.md")


@pytest.fixture
def issue_hue_newest_keep() -> Path:
    """Issue file for newest Hue OTA version (keep existing)."""
    return Path("tests/data/gh_issues/issue_hue_newest_keep.md")


@pytest.fixture
def issue_hue_new_replace_both() -> Path:
    """Issue file for new Hue OTA version (replace both old and newest)."""
    return Path("tests/data/gh_issues/issue_hue_new_replace_both.md")


@pytest.fixture
def issue_hue_new_set_min_version() -> Path:
    """Issue file for new Hue OTA version (set min_current_file_version)."""
    return Path("tests/data/gh_issues/issue_hue_new_set_min_version.md")


@pytest.fixture
def issue_hue_new_manual_override() -> Path:
    """Issue file for new Hue OTA version (manual override of min_current_file_version)."""
    return Path("tests/data/gh_issues/issue_hue_new_manual_override.md")


@pytest.fixture
def issue_hue_old_hw_override() -> Path:
    """Issue file for Hue OTA with hardware version overrides."""
    return Path("tests/data/gh_issues/issue_hue_old_hw_override.md")


@pytest.fixture
def issue_hue_header_string() -> Path:
    """Issue file for Hue OTA with header string in OTA file."""
    return Path("tests/data/gh_issues/issue_hue_header_string.md")


@pytest.fixture
def ota_hue_header_string() -> Path:
    """OTA file with header string."""
    return Path("tests/data/ota_files/fake_100B-010C-01003000-WithHeaderString.zigbee")


@pytest.fixture
def issue_hue_third_party_header_string() -> Path:
    """Issue file for third-party download with header string in OTA file."""
    return Path("tests/data/gh_issues/issue_hue_third_party_header_string.md")


@pytest.fixture
def issue_paths(request: pytest.FixtureRequest) -> list[Path]:
    """Resolve issue fixture names to actual Path objects."""
    return [request.getfixturevalue(name) for name in request.param]


@pytest.fixture
def ota_paths(request: pytest.FixtureRequest) -> list[Path]:
    """Resolve OTA fixture names to actual Path objects."""
    return [request.getfixturevalue(name) for name in request.param]


def run_prepare_pr(
    issue_path: Path,
    ota_file: Path,
    output_markdown: Path,
    mock_download: MagicMock,
) -> Result:
    """Run prepare-pr command for a given issue and OTA file.

    Args:
        issue_path: Path to the GitHub issue markdown file
        ota_file: Path to the OTA firmware file
        output_markdown: Path where PR markdown should be written
        mock_download: Mock object for download_ota_file function

    Returns:
        CliRunner Result object with command execution details
    """
    # Read the actual OTA file content to use in mock
    ota_content = ota_file.read_bytes()
    mock_download.return_value = ota_content

    # Generate PR files: download OTA, create YAML, generate markdown
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "prepare-pr",
            str(issue_path),
            "--output-pr-markdown",
            str(output_markdown),
        ],
    )

    return result


@pytest.mark.parametrize(
    ("issue_paths", "ota_paths"),
    [
        # Test 1: Single image - old version only
        pytest.param(["issue_hue_old"], ["ota_hue_old"], id="single_old"),
        # Test 2: Old + new version with keep existing
        pytest.param(
            ["issue_hue_old", "issue_hue_new_keep"],
            ["ota_hue_old", "ota_hue_new"],
            id="old_plus_new_keep",
        ),
        # Test 3: Old + new version with replace existing
        pytest.param(
            ["issue_hue_old", "issue_hue_new_replace"],
            ["ota_hue_old", "ota_hue_new"],
            id="old_plus_new_replace",
        ),
        # Test 4: Re-upload same filename (triggers file replacement warning)
        pytest.param(
            ["issue_hue_old", "issue_hue_old_reupload"],
            ["ota_hue_old", "ota_hue_old"],
            id="file_replacement_warning",
        ),
        # Test 5: Issue with no metadata fields (no metadata header shown)
        pytest.param(
            ["issue_hue_no_metadata"],
            ["ota_hue_old"],
            id="no_metadata_header",
        ),
        # Test 6: Third-party download (no image file saved)
        pytest.param(
            ["issue_hue_third_party"],
            ["ota_hue_old"],
            id="third_party",
        ),
        # Test 7: Regular + third-party mixed
        pytest.param(
            ["issue_hue_old", "issue_hue_third_party"],
            ["ota_hue_old", "ota_hue_old"],
            id="regular_plus_third_party",
        ),
        # Test 8: Third-party + regular mixed (reverse of test 7)
        pytest.param(
            ["issue_hue_third_party", "issue_hue_regular_replace_third_party"],
            ["ota_hue_old", "ota_hue_old"],
            id="third_party_plus_regular",
        ),
        # Test 9: Downgrade - old version replacing new version
        pytest.param(
            ["issue_hue_new_replace", "issue_hue_old_replace"],
            ["ota_hue_new", "ota_hue_old"],
            id="new_plus_old_downgrade",
        ),
        # Test 10: Middle version replacing both old and newest versions
        pytest.param(
            ["issue_hue_old", "issue_hue_newest_keep", "issue_hue_new_replace_both"],
            ["ota_hue_old", "ota_hue_newest", "ota_hue_new"],
            id="middle_replaces_old_and_newest",
        ),
        # Test 11: Auto-set min_current_file_version from existing images
        pytest.param(
            ["issue_hue_old", "issue_hue_new_auto_version"],
            ["ota_hue_old", "ota_hue_new"],
            id="old_plus_new_auto_min_version",
        ),
        # Test 12: Middle version with SET_MIN_VERSION (should only use versions below middle)
        pytest.param(
            ["issue_hue_old", "issue_hue_newest_keep", "issue_hue_new_set_min_version"],
            ["ota_hue_old", "ota_hue_newest", "ota_hue_new"],
            id="middle_set_min_version_ignores_higher",
        ),
        # Test 13: Manual override of min_current_file_version (warning should appear)
        pytest.param(
            ["issue_hue_old", "issue_hue_newest_keep", "issue_hue_new_manual_override"],
            ["ota_hue_old", "ota_hue_newest", "ota_hue_new"],
            id="middle_manual_override_warning",
        ),
        # Test 14: Hardware version override (warning should appear)
        pytest.param(
            ["issue_hue_old_hw_override"],
            ["ota_hue_old"],
            id="hardware_version_override",
        ),
        # Test 15: OTA file with header string (should appear in PR markdown)
        pytest.param(
            ["issue_hue_header_string"],
            ["ota_hue_header_string"],
            id="ota_header_string",
        ),
        # Test 16: Third-party download with header string (should appear in YAML and PR markdown)
        pytest.param(
            ["issue_hue_third_party_header_string"],
            ["ota_hue_header_string"],
            id="third_party_header_string",
        ),
        # Test 17: Trailing whitespace in release notes should be stripped
        pytest.param(
            ["issue_hue_old_trailing_whitespace"],
            ["ota_hue_old"],
            id="trailing_whitespace_stripped",
        ),
        # Test 18: Missing space after colon in optional metadata should be fixed
        pytest.param(
            ["issue_hue_old_metadata_no_space"],
            ["ota_hue_old"],
            id="metadata_missing_space_after_colon",
        ),
        # Test 19: Markdown headings (###) in release notes should be preserved
        pytest.param(
            ["issue_hue_old_release_notes_headings"],
            ["ota_hue_old"],
            id="release_notes_with_headings",
        ),
    ],
    indirect=["issue_paths", "ota_paths"],
)
def test_prepare_pr_command_with_snapshot(
    snapshot: SnapshotAssertion,
    tmp_path: Path,
    issue_paths: list[Path],
    ota_paths: list[Path],
) -> None:
    """Test prepare-pr command generates correct outputs with snapshot validation.

    Runs prepare-pr for multiple scenarios including single/multiple images,
    keep/replace existing, file re-uploads, third-party downloads, and mixed cases.
    Validates that markdown, YAML, and OTA index outputs match expected snapshots
    and that the generated index conforms to zigpy's REMOTE_PROVIDER_SCHEMA.

    Args:
        snapshot: Syrupy snapshot fixture for comparing output
        tmp_path: Pytest fixture providing temporary directory path
        issue_paths: List of issue markdown file paths (parametrized)
        ota_paths: List of OTA firmware file paths (parametrized)
    """
    # Build issue_ota_pairs from the resolved fixture values
    issue_ota_pairs = list(zip(issue_paths, ota_paths))

    # Create separate directories for images and markdown outputs
    images_path = tmp_path / "images"
    markdown_output_path = tmp_path / "markdown_outputs"
    markdown_output_path.mkdir(exist_ok=True)

    # Mock both download and IMAGES_PATH (patch in all locations where it's imported)
    with (
        patch("zigpy_ota.actions.pr.prepare_files.download_ota_file") as mock_download,
        patch("zigpy_ota.actions.pr.download_utils.IMAGES_PATH", images_path),
        patch("zigpy_ota.actions.pr.pr_utils.IMAGES_PATH", images_path),
        patch("zigpy_ota.actions.pr.prepare_files.IMAGES_PATH", images_path),
    ):
        # Loop through all issue/OTA pairs and run prepare-pr for each
        for idx, (issue_path, ota_file) in enumerate(issue_ota_pairs):
            # Create unique output path for each markdown in separate directory
            output_markdown = markdown_output_path / f"test_pr_{idx}.md"

            result = run_prepare_pr(
                issue_path, ota_file, output_markdown, mock_download
            )

            # Check that the command succeeded
            assert result.exit_code == 0, (
                f"Command failed for pair {idx} with exit code {result.exit_code}. "
                f"Output: {result.output}"
            )

            # Verify the markdown file was created
            assert output_markdown.exists(), (
                f"Output markdown file {output_markdown} was not created for pair {idx}"
            )

            # Verify that a YAML file exists (was created or replaced)
            # Re-uploads with same content will get the same filename,
            # so there may not be a "new" file when
            yaml_files_after = set(images_path.rglob("*.yaml"))
            assert len(yaml_files_after) >= 1, f"No YAML file exists after pair {idx}"
            # TODO: already collect YAML (+ PR contents) for snapshot later?

    # After all prepare-pr calls, collect all generated files for snapshot comparison
    # Collect all markdown files from the markdown output directory
    markdown_files = sorted(markdown_output_path.glob("test_pr_*.md"))
    markdown_contents = {f.name: f.read_text() for f in markdown_files}

    # Collect all YAML files from the images directory
    yaml_files = sorted(images_path.rglob("*.yaml"))
    yaml_contents = {f.name: f.read_text() for f in yaml_files}

    # Collect all OTA image files (for third-party, should be empty or only regular downloads)
    ota_files = [
        f
        for f in images_path.rglob("*")
        if f.is_file()
        and not f.suffix == ".yaml"
        and not f.name.endswith(".md")
        and not f.name.endswith(".json")
    ]
    ota_file_names = sorted([f.name for f in ota_files])

    # Generate OTA index JSON using CLI (generate-index command)
    ota_index_json_path = tmp_path / "zigpy_ota_metadata.json"

    runner = CliRunner()
    index_result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(images_path),
            "--output-file",
            str(ota_index_json_path),
            "--tag",
            "test-tag",
            "--allow-missing-yaml",  # Allow missing YAML for test markdown files
        ],
    )

    # Check that the generate-index command succeeded
    assert index_result.exit_code == 0, (
        f"generate-index command failed with exit code {index_result.exit_code}. "
        f"Output: {index_result.output}"
    )

    # Check that the OTA index JSON was created
    assert ota_index_json_path.exists(), "OTA index JSON file was not created"

    # Read and parse the OTA index JSON
    with ota_index_json_path.open("r") as f:
        ota_index_data = json.load(f)

    # Validate the OTA index data has correct structure
    assert isinstance(ota_index_data, dict), (
        f"Expected JSON dict, got {type(ota_index_data).__name__}"
    )
    assert "firmwares" in ota_index_data, "Expected 'firmwares' key in JSON output"
    assert isinstance(ota_index_data["firmwares"], list), (
        "Expected 'firmwares' to be a list"
    )

    # Validate against zigpy REMOTE_PROVIDER_SCHEMA
    validate_ota_index_schema(ota_index_data)

    # Convert OTA index to JSON string for snapshot
    ota_index_json = json.dumps(ota_index_data, indent=2)

    # Compare with snapshot
    assert {
        "markdowns": markdown_contents,
        "yamls": yaml_contents,
        "ota_files": ota_file_names,  # Track which image files were actually saved
        "ota_index": ota_index_json,
    } == snapshot
