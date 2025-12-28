"""Test that duplicate filenames in different directories are handled correctly."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from zigpy_ota.cli import cli


def test_duplicate_filenames_in_different_directories(tmp_path: Path) -> None:
    """Test that files with same name in different directories are both included.

    This regression test ensures that when multiple manufacturer directories
    contain OTA files with the same filename, all files are included in the
    generated index (not just the last one processed).
    """
    # Create two manufacturer directories
    signify_dir = tmp_path / "signify"
    philips_dir = tmp_path / "philips"
    signify_dir.mkdir()
    philips_dir.mkdir()

    # Copy the same OTA file to both directories with identical filename
    source_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    ota_content = source_ota.read_bytes()

    signify_ota = signify_dir / "lamp.zigbee"
    philips_ota = philips_dir / "lamp.zigbee"
    signify_ota.write_bytes(ota_content)
    philips_ota.write_bytes(ota_content)

    # Create YAML metadata for both (with different manufacturer info)
    signify_yaml = signify_dir / "lamp.zigbee.yaml"
    signify_yaml.write_text(
        """file_name: lamp.zigbee
source_file_name: lamp.zigbee
source_url: https://example.com/signify/lamp.zigbee
manufacturer_names:
  - Signify
model_names:
  - Test Lamp Signify
"""
    )

    philips_yaml = philips_dir / "lamp.zigbee.yaml"
    philips_yaml.write_text(
        """file_name: lamp.zigbee
source_file_name: lamp.zigbee
source_url: https://example.com/philips/lamp.zigbee
manufacturer_names:
  - Philips
model_names:
  - Test Lamp Philips
"""
    )

    # Generate the index
    output_json = tmp_path / "index.json"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(tmp_path),
            "--output-file",
            str(output_json),
            "--tag",
            "test-tag",
        ],
    )

    assert result.exit_code == 0, f"Command failed: {result.output}"
    assert output_json.exists(), "Output file not created"

    # Parse the generated JSON
    with output_json.open("r") as f:
        index_data = json.load(f)

    # Verify JSON structure
    assert isinstance(index_data, dict), "Expected JSON dict"
    assert "firmwares" in index_data, "Expected 'firmwares' key"
    firmwares = index_data["firmwares"]

    # Should have 2 entries (one for each directory), not 1 (which would be the bug)
    assert len(firmwares) == 2, f"Expected 2 entries, got {len(firmwares)}"

    # Verify both entries have different binary_urls with correct paths
    urls = sorted([entry["binary_url"] for entry in firmwares])
    assert any("signify/lamp.zigbee" in url for url in urls), "Signify entry missing"
    assert any("philips/lamp.zigbee" in url for url in urls), "Philips entry missing"
    assert urls[0] != urls[1], "URLs should be different"

    # Verify manufacturer_names are different
    manufacturers = sorted([entry.get("manufacturer_names")[0] for entry in firmwares])
    assert "Philips" in manufacturers, "Philips manufacturer missing"
    assert "Signify" in manufacturers, "Signify manufacturer missing"
