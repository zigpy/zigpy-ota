"""Tests for CLI commands."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from zigpy_ota.cli import cli


def test_generate_stub_metadata(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    """Test generate-stub-metadata command creates YAML with stub data."""
    # Copy an existing OTA file to tmp_path
    source_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    test_ota = tmp_path / "test.zigbee"
    test_ota.write_bytes(source_ota.read_bytes())

    # Run the generate-stub-metadata command
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["generate-stub-metadata", str(test_ota)],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Generating stub metadata file for:" in result.output
    assert "Done!" in result.output

    # Verify YAML file was created
    yaml_file = tmp_path / "test.zigbee.yaml"
    assert yaml_file.exists(), "YAML file was not created"

    # Compare YAML content against snapshot
    yaml_content = yaml_file.read_text()
    assert yaml_content == snapshot


def test_generate_stub_metadata_nonexistent_file(tmp_path: Path) -> None:
    """Test generate-stub-metadata command fails for nonexistent file."""
    nonexistent_file = tmp_path / "nonexistent.zigbee"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["generate-stub-metadata", str(nonexistent_file)],
    )

    # Verify command failed
    assert result.exit_code != 0
    assert (
        "does not exist" in result.output.lower()
        or "no such file" in result.output.lower()
    )


def test_generate_stub_metadata_all(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """Test generate-stub-metadata-all command creates YAML files for all images."""
    # Create directory structure with multiple OTA files
    source_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    ota_content = source_ota.read_bytes()

    # Create files in root directory
    (tmp_path / "image1.zigbee").write_bytes(ota_content)
    (tmp_path / "image2.ota").write_bytes(ota_content)

    # Create files in subdirectory
    subdir = tmp_path / "manufacturer"
    subdir.mkdir()
    (subdir / "image3.zigbee").write_bytes(ota_content)

    # Create a hidden file (should be skipped)
    (tmp_path / ".hidden.zigbee").write_bytes(ota_content)

    # Create an existing YAML file (should be skipped)
    existing_yaml = tmp_path / "existing.yaml"
    existing_yaml.write_text("# Existing YAML")

    # Run generate-stub-metadata-all command
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["generate-stub-metadata-all", "--images-path", str(tmp_path)],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert f"Generating stub metadata files in: {tmp_path}" in result.output
    assert "Done!" in result.output

    # Verify YAML files were created for regular image files
    yaml1 = tmp_path / "image1.zigbee.yaml"
    yaml2 = tmp_path / "image2.ota.yaml"
    yaml3 = subdir / "image3.zigbee.yaml"

    assert yaml1.exists(), "YAML for image1.zigbee was not created"
    assert yaml2.exists(), "YAML for image2.ota was not created"
    assert yaml3.exists(), "YAML for image3.zigbee was not created"

    # Verify hidden file was skipped
    hidden_yaml = tmp_path / ".hidden.zigbee.yaml"
    assert not hidden_yaml.exists(), "YAML for hidden file should not be created"

    # Compare YAML file contents against snapshots
    yaml_contents = {
        "image1.zigbee.yaml": yaml1.read_text(),
        "image2.ota.yaml": yaml2.read_text(),
        "manufacturer/image3.zigbee.yaml": yaml3.read_text(),
    }
    assert yaml_contents == snapshot


def test_generate_stub_metadata_all_empty_directory(tmp_path: Path) -> None:
    """Test generate-stub-metadata-all command on empty directory."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["generate-stub-metadata-all", "--images-path", str(empty_dir)],
    )

    # Verify command succeeded (no files to process is not an error)
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Done!" in result.output


def test_delete_stub_metadata(tmp_path: Path) -> None:
    """Test delete-stub-metadata command deletes all YAML files."""
    # Create directory structure with YAML files
    (tmp_path / "file1.yaml").write_text("content1")
    (tmp_path / "file2.zigbee.yaml").write_text("content2")

    # Create files in subdirectory
    subdir = tmp_path / "manufacturer"
    subdir.mkdir()
    (subdir / "file3.yaml").write_text("content3")

    # Create a hidden YAML file (should be skipped)
    (tmp_path / ".hidden.yaml").write_text("hidden")

    # Create a non-YAML file (should not be deleted)
    (tmp_path / "image.zigbee").write_text("image content")

    # Verify all files exist before deletion
    assert (tmp_path / "file1.yaml").exists()
    assert (tmp_path / "file2.zigbee.yaml").exists()
    assert (subdir / "file3.yaml").exists()
    assert (tmp_path / ".hidden.yaml").exists()
    assert (tmp_path / "image.zigbee").exists()

    # Run delete-stub-metadata command
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["delete-stub-metadata", "--images-path", str(tmp_path)],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert f"Deleting stub metadata files in: {tmp_path}" in result.output
    assert "Done!" in result.output

    # Verify YAML files were deleted
    assert not (tmp_path / "file1.yaml").exists(), "file1.yaml should be deleted"
    assert not (tmp_path / "file2.zigbee.yaml").exists(), (
        "file2.zigbee.yaml should be deleted"
    )
    assert not (subdir / "file3.yaml").exists(), "file3.yaml should be deleted"

    # Verify hidden YAML was skipped
    assert (tmp_path / ".hidden.yaml").exists(), "Hidden file should not be deleted"

    # Verify non-YAML file was not deleted
    assert (tmp_path / "image.zigbee").exists(), "Non-YAML file should not be deleted"


def test_delete_stub_metadata_empty_directory(tmp_path: Path) -> None:
    """Test delete-stub-metadata command on directory with no YAML files."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["delete-stub-metadata", "--images-path", str(empty_dir)],
    )

    # Verify command succeeded (no files to delete is not an error)
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Done!" in result.output


def test_parse_issue(snapshot: SnapshotAssertion) -> None:
    """Test parse-issue command extracts data from GitHub issue file."""
    issue_file = Path("tests/data/gh_issues/issue_hue_old.md")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["parse-issue", str(issue_file)],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert f"Parsing issue file: {issue_file}" in result.output
    assert "Done!" in result.output

    # Extract JSON from output (between "Parsing issue file" and "Done!")
    lines = result.output.split("\n")
    json_start = 0
    json_end = len(lines)

    for i, line in enumerate(lines):
        if line.startswith("Parsing issue file:"):
            json_start = i + 1
        elif line.startswith("Done!"):
            json_end = i
            break

    json_output = "\n".join(lines[json_start:json_end])

    # Compare against snapshot
    assert json_output == snapshot


def test_parse_issue_nonexistent_file(tmp_path: Path) -> None:
    """Test parse-issue command fails for nonexistent file."""
    nonexistent_file = tmp_path / "nonexistent.md"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["parse-issue", str(nonexistent_file)],
    )

    # Verify command failed
    assert result.exit_code != 0
    assert (
        "does not exist" in result.output.lower()
        or "no such file" in result.output.lower()
    )


def test_normalize_yaml(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    """Test normalize-yaml command re-writes YAML files with consistent formatting."""
    # Create a directory with YAML files that have inconsistent formatting
    source_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    ota_content = source_ota.read_bytes()

    # Create an OTA file and a YAML file with non-standard formatting
    ota_file = tmp_path / "test.zigbee"
    ota_file.write_bytes(ota_content)

    # Create YAML with non-standard field order and formatting
    yaml_content = """# Some comment
file_name: test.zigbee
source_file_name: test.zigbee
release_notes: 'Some notes'
source_url: https://example.com/firmware.ota
model_names:
- Model A
- Model B
"""
    yaml_file = tmp_path / "test.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    # Run normalize-yaml command
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["normalize-yaml", "--images-path", str(tmp_path)],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert f"Normalizing YAML metadata files in: {tmp_path}" in result.output
    assert "Normalized 1 YAML file(s)" in result.output
    assert "Done!" in result.output

    # Compare normalized YAML content against snapshot
    normalized_content = yaml_file.read_text()
    assert normalized_content == snapshot


def test_normalize_yaml_empty_directory(tmp_path: Path) -> None:
    """Test normalize-yaml command on empty directory."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["normalize-yaml", "--images-path", str(empty_dir)],
    )

    # Verify command succeeded (no files to process is not an error)
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Normalized 0 YAML file(s)" in result.output
    assert "Done!" in result.output


def test_normalize_yaml_third_party(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """Test normalize-yaml command handles third-party YAML files correctly."""
    # Create a third-party YAML file (no OTA binary)
    yaml_content = """# Third party OTA
file_name: third_party.zigbee
source_file_name: third_party.zigbee
source_url: https://example.com/firmware.ota
third_party_download:
  manufacturer_id: 4107
  image_type: 268
  file_version: 16783874
  file_size: 12345
  checksum_sha3_256: abc123
  checksum_sha512: def456
release_notes: |-
  - Bug fixes
  - Performance improvements
"""
    yaml_file = tmp_path / "third_party.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    # Run normalize-yaml command
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["normalize-yaml", "--images-path", str(tmp_path)],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Normalized 1 YAML file(s)" in result.output
    assert "Done!" in result.output

    # Compare normalized YAML content against snapshot
    normalized_content = yaml_file.read_text()
    assert normalized_content == snapshot


def test_rename_ota_files_dry_run(tmp_path: Path) -> None:
    """Test rename-ota-files command in dry-run mode."""
    # Copy an existing OTA file with non-standard name
    source_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    test_ota = tmp_path / "my_firmware.zigbee"
    test_ota.write_bytes(source_ota.read_bytes())

    # Run the rename command in dry-run mode
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["rename-ota-files", "--images-path", str(tmp_path), "--dry-run"],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "[DRY RUN MODE" in result.output
    assert "my_firmware.zigbee ->" in result.output
    assert "100B-010C-01001A02_" in result.output
    assert ".ota" in result.output
    assert "Renamed: 1" in result.output

    # Verify file was NOT actually renamed (dry-run)
    assert test_ota.exists(), "File should not be renamed in dry-run mode"
    assert not any(f.name.startswith("100B-010C") for f in tmp_path.iterdir()), (
        "No renamed file should exist in dry-run mode"
    )


def test_rename_ota_files(tmp_path: Path, snapshot: SnapshotAssertion) -> None:
    """Test rename-ota-files command renames files and updates YAML."""
    # Copy an existing OTA file with non-standard name
    source_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    original_filename = "my_firmware.zigbee"
    test_ota = tmp_path / original_filename
    test_ota.write_bytes(source_ota.read_bytes())

    # Create a YAML file for the OTA
    yaml_content = f"""# OTA metadata
file_name: {original_filename}
source_file_name: {original_filename}
source_url: https://example.com/firmware.ota
release_notes: |-
  - Bug fixes
"""
    yaml_file = tmp_path / f"{original_filename}.yaml"
    yaml_file.write_text(yaml_content)

    # Run the rename command
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["rename-ota-files", "--images-path", str(tmp_path)],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "my_firmware.zigbee ->" in result.output
    assert "Renamed: 1" in result.output
    assert "Updated YAML:" in result.output

    # Verify original file was renamed
    assert not test_ota.exists(), "Original file should be renamed"
    assert not yaml_file.exists(), "Original YAML should be renamed"

    # Find the renamed files
    ota_files = [f for f in tmp_path.iterdir() if f.suffix == ".ota"]
    assert len(ota_files) == 1, "Should have exactly one renamed OTA file"
    renamed_ota = ota_files[0]

    # Verify new filename format
    assert renamed_ota.name.startswith("100B-010C-01001A02_")
    assert renamed_ota.name.endswith(".ota")

    # Verify YAML was updated
    renamed_yaml = renamed_ota.with_suffix(".ota.yaml")
    assert renamed_yaml.exists(), "Renamed YAML should exist"

    # Compare YAML content against snapshot
    yaml_content = renamed_yaml.read_text()
    assert yaml_content == snapshot


def test_rename_ota_files_already_correct(tmp_path: Path) -> None:
    """Test rename-ota-files command skips already correctly named files."""
    # Copy an existing OTA file
    source_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    ota_content = source_ota.read_bytes()

    # Create file with correct standardized name
    # The hash for this file starts with "879c1b"
    correct_name = "100B-010C-01001A02_879c1b.ota"
    test_ota = tmp_path / correct_name
    test_ota.write_bytes(ota_content)

    # Run the rename command
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["rename-ota-files", "--images-path", str(tmp_path)],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Already correct: 1" in result.output
    assert "Renamed: 0" in result.output

    # Verify file was not modified
    assert test_ota.exists(), "File should still exist with same name"


def test_rename_ota_files_preserves_source_file_name(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """Test rename-ota-files preserves existing source_file_name in YAML."""
    # Copy an existing OTA file with non-standard name
    source_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    test_ota = tmp_path / "current_name.zigbee"
    test_ota.write_bytes(source_ota.read_bytes())

    # Create a YAML file with a different source_file_name (already set)
    yaml_content = """# OTA metadata
file_name: current_name.zigbee
source_file_name: original_from_manufacturer.zigbee
source_url: https://example.com/firmware.ota
"""
    yaml_file = tmp_path / "current_name.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    # Run the rename command
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["rename-ota-files", "--images-path", str(tmp_path)],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Renamed: 1" in result.output

    # Find the renamed YAML
    yaml_files = [f for f in tmp_path.iterdir() if f.suffix == ".yaml"]
    assert len(yaml_files) == 1
    renamed_yaml = yaml_files[0]

    # Compare YAML content against snapshot - source_file_name should be preserved
    yaml_content = renamed_yaml.read_text()
    assert yaml_content == snapshot


def test_rename_ota_files_third_party_yaml(
    tmp_path: Path, snapshot: SnapshotAssertion
) -> None:
    """Test rename-ota-files renames third-party YAML files (no OTA binary)."""
    # Create a third-party YAML file (no corresponding OTA binary)
    yaml_content = """# OTA metadata
file_name: my-third-party-firmware.zigbee
source_file_name: my-third-party-firmware.zigbee
source_url: https://example.com/firmware.ota
# OTA image metadata required for third-party hosted images:
third_party_download:
  manufacturer_id: 4107
  image_type: 268
  file_version: 16783874
  file_size: 12345
  checksum_sha3_256: abc123def456789012345678901234567890123456789012345678901234
  checksum_sha512: def456abc123
release_notes: |-
  - Bug fixes
"""
    yaml_file = tmp_path / "my-third-party-firmware.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    # Run the rename command
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["rename-ota-files", "--images-path", str(tmp_path)],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "my-third-party-firmware.zigbee.yaml ->" in result.output
    assert "Renamed: 1" in result.output

    # Verify original file was renamed
    assert not yaml_file.exists(), "Original YAML should be renamed"

    # Find the renamed YAML
    yaml_files = [f for f in tmp_path.iterdir() if f.suffix == ".yaml"]
    assert len(yaml_files) == 1
    renamed_yaml = yaml_files[0]

    # Verify new filename format (100B-010C-01001A02_abc123.ota.yaml)
    assert renamed_yaml.name.startswith("100B-010C-01001A02_")
    assert renamed_yaml.name.endswith(".ota.yaml")

    # Compare YAML content against snapshot
    yaml_content = renamed_yaml.read_text()
    assert yaml_content == snapshot
