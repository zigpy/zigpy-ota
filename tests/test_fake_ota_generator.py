"""Tests for fake OTA generator."""

from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner

from zigpy_ota.cli import cli


def test_generate_fake_ota(tmp_path: Path) -> None:
    """Test generate-fake-ota command creates valid OTA image."""
    output_file = tmp_path / "fake.zigbee"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-fake-ota",
            str(output_file),
            "--manufacturer-id",
            "0x1234",
            "--image-type",
            "0x5678",
            "--file-version",
            "0x00000001",
        ],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Generating fake OTA image:" in result.output
    assert "Done!" in result.output
    assert "Fake OTA image created at:" in result.output
    assert "Manufacturer ID: 0x1234" in result.output
    assert "Image Type: 0x5678" in result.output
    assert "File Version: 0x00000001" in result.output

    # Verify file was created
    assert output_file.exists(), "Fake OTA file was not created"

    # Verify it's a valid OTA image by parsing it with zigpy
    from zigpy.ota.image import parse_ota_image

    data = output_file.read_bytes()
    image, remaining = parse_ota_image(data)

    assert not remaining, "OTA image has unexpected trailing data"
    assert image.header.manufacturer_id == 0x1234
    assert image.header.image_type == 0x5678
    assert image.header.file_version == 0x00000001


def test_generate_fake_ota_with_hardware_versions(tmp_path: Path) -> None:
    """Test generate-fake-ota command with hardware version parameters."""
    output_file = tmp_path / "fake_hw.zigbee"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-fake-ota",
            str(output_file),
            "--manufacturer-id",
            "0xABCD",
            "--image-type",
            "0xEF01",
            "--file-version",
            "0x12345678",
            "--min-hw-version",
            "0x0001",
            "--max-hw-version",
            "0x0002",
            "--header-string",
            "Test OTA",
        ],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Min HW Version: 0x0001" in result.output
    assert "Max HW Version: 0x0002" in result.output
    assert "Header String: Test OTA" in result.output

    # Verify file was created and parse it
    assert output_file.exists()

    from zigpy.ota.image import parse_ota_image

    data = output_file.read_bytes()
    image, remaining = parse_ota_image(data)

    assert not remaining
    assert image.header.manufacturer_id == 0xABCD
    assert image.header.image_type == 0xEF01
    assert image.header.file_version == 0x12345678
    assert image.header.minimum_hardware_version == 0x0001
    assert image.header.maximum_hardware_version == 0x0002
    assert "Test OTA" in str(image.header.header_string)


def test_generate_fake_ota_invalid_hex(tmp_path: Path) -> None:
    """Test generate-fake-ota command fails with invalid hex value."""
    output_file = tmp_path / "fake.zigbee"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-fake-ota",
            str(output_file),
            "--manufacturer-id",
            "invalid",
            "--image-type",
            "0x5678",
            "--file-version",
            "0x00000001",
        ],
    )

    # Verify command failed
    assert result.exit_code != 0
    assert "Error: Invalid hex value" in result.output or "Aborted" in result.output


def test_replace_with_fake_ota_single_file(tmp_path: Path) -> None:
    """Test replace-with-fake-ota command with a single file."""
    # Copy a real OTA file to temp directory
    src_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    test_ota = tmp_path / "test.zigbee"
    shutil.copy(src_ota, test_ota)

    original_size = test_ota.stat().st_size

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "replace-with-fake-ota",
            str(test_ota),
        ],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "Processing 1 OTA file(s)" in result.output
    assert "Processing OTA file:" in result.output
    assert "Manufacturer ID: 0x100B" in result.output
    assert "Image Type: 0x010C" in result.output
    assert "File Version: 0x01001A02" in result.output
    assert "✓ All OTA files replaced successfully!" in result.output

    # Verify file was replaced
    assert test_ota.exists()
    new_size = test_ota.stat().st_size
    # Note: Since test files are already fake, size might be the same
    assert new_size <= original_size, "Fake file should not be larger than original"

    # Verify it's still a valid OTA image
    from zigpy.ota.image import parse_ota_image

    data = test_ota.read_bytes()
    image, remaining = parse_ota_image(data)

    assert not remaining
    assert image.header.manufacturer_id == 0x100B
    assert image.header.image_type == 0x010C
    assert image.header.file_version == 0x01001A02


def test_replace_with_fake_ota_multiple_files(tmp_path: Path) -> None:
    """Test replace-with-fake-ota command with multiple files."""
    # Copy multiple real OTA files to temp directory
    ota_files_dir = Path("tests/data/ota_files")
    test_files = []

    for src_ota in ota_files_dir.glob("*.zigbee"):
        test_ota = tmp_path / src_ota.name
        shutil.copy(src_ota, test_ota)
        test_files.append(test_ota)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "replace-with-fake-ota",
            *[str(f) for f in test_files],
        ],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert f"Processing {len(test_files)} OTA file(s)" in result.output
    assert "✓ All OTA files replaced successfully!" in result.output

    # Verify all files were replaced
    for test_file in test_files:
        assert test_file.exists()


def test_replace_with_fake_ota_dry_run(tmp_path: Path) -> None:
    """Test replace-with-fake-ota command with --dry-run flag."""
    # Copy a real OTA file to temp directory
    src_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    test_ota = tmp_path / "test.zigbee"
    shutil.copy(src_ota, test_ota)

    original_size = test_ota.stat().st_size
    original_data = test_ota.read_bytes()

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "replace-with-fake-ota",
            "--dry-run",
            str(test_ota),
        ],
    )

    # Verify command succeeded
    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert "[DRY RUN MODE - No files will be modified]" in result.output
    assert "Use without --dry-run to actually replace files" in result.output

    # Verify file was NOT modified
    assert test_ota.stat().st_size == original_size
    assert test_ota.read_bytes() == original_data


def test_replace_with_fake_ota_nonexistent_file() -> None:
    """Test replace-with-fake-ota command fails with nonexistent file."""
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "replace-with-fake-ota",
            "nonexistent.zigbee",
        ],
    )

    # Verify command failed
    assert result.exit_code != 0
