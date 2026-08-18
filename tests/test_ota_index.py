"""Tests for zigpy-ota index CLI commands."""

from __future__ import annotations

import dataclasses
import json
import logging
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner
from syrupy.assertion import SnapshotAssertion

from tests.common import validate_ota_index_schema, validate_z2m_index_schema
from zigpy_ota.actions.metadata.collision_validation import (
    compute_specificity,
    could_match_same_device,
    validate_collisions,
)
from zigpy_ota.actions.metadata.merging import (
    prepare_metadata_for_markdown,
    prepare_metadata_for_z2m,
    prepare_metadata_for_zigpy,
)
from zigpy_ota.actions.metadata.stale_validation import (
    compute_stale_images,
    is_dominated_by,
    validate_unreachable_images,
)
from zigpy_ota.actions.metadata.z2m_utils import compute_max_file_versions
from zigpy_ota.actions.testing.fake_ota_generator import generate_fake_ota_image
from zigpy_ota.cli import cli
from zigpy_ota.const import Z2M_OTA_METADATA_OUTPUT_PATH, ZIGPY_OTA_METADATA_OUTPUT_PATH
from zigpy_ota.models.index_metadata import IndexMetadata
from zigpy_ota.models.yaml_metadata import Channel


def test_generate_index_zigpy_format(tmp_path: Path) -> None:
    """Test that generate-index creates valid zigpy JSON by default.

    Runs against the actual images/ directory to ensure all OTA images
    and YAML metadata can be parsed and indexed correctly.
    """
    output_file = tmp_path / "test_zigpy_ota_metadata.json"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--output-file",
            str(output_file),
        ],
    )

    assert result.exit_code == 0, f"Command failed with output: {result.output}"
    assert output_file.exists(), "Output file was not created"
    assert output_file.stat().st_size > 0, "Output file is empty"

    with output_file.open("r") as f:
        data = json.load(f)

    assert isinstance(data, dict), f"Expected JSON dict, got {type(data).__name__}"
    assert "firmwares" in data, "Expected 'firmwares' key in JSON output"
    assert isinstance(data["firmwares"], list), "Expected 'firmwares' to be a list"

    # Validate against zigpy REMOTE_PROVIDER_SCHEMA
    validate_ota_index_schema(data)


def test_generate_index_z2m_format(tmp_path: Path) -> None:
    """Test that generate-index creates valid z2m JSON with --format z2m.

    Runs against the actual images/ directory to ensure all OTA images
    and YAML metadata can be parsed and indexed correctly.
    """
    output_file = tmp_path / Z2M_OTA_METADATA_OUTPUT_PATH.name

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--format",
            "z2m",
            "--output-file",
            str(output_file),
        ],
    )

    assert result.exit_code == 0, f"Command failed with output: {result.output}"
    assert output_file.exists(), "Output file was not created"
    assert output_file.stat().st_size > 0, "Output file is empty"

    with output_file.open("r") as f:
        data = json.load(f)

    # Z2M format is a list, not a dict with "firmwares" key
    assert isinstance(data, list), f"Expected JSON list, got {type(data).__name__}"

    # TODO: Remove skip when images directory includes at least one firmware
    if len(data) == 0:
        pytest.skip("No firmware entries found in z2m index output")

    assert len(data) > 0, "Expected at least one firmware entry"

    # Check z2m-specific fields
    first_entry = data[0]
    assert "fileVersion" in first_entry, (
        "Expected camelCase 'fileVersion' in z2m format"
    )
    assert "manufacturerCode" in first_entry, (
        "Expected 'manufacturerCode' in z2m format"
    )
    assert "sha512" in first_entry, "Expected 'sha512' in z2m format"

    # Validate every entry against zigbee-herdsman's index entry shape
    validate_z2m_index_schema(data)
    # zigpy uses "manufacturer_id" and "checksum", z2m uses "manufacturerCode" and "sha512"
    assert "manufacturer_id" not in first_entry, "Unexpected zigpy field in z2m format"


def test_index_formats_with_header_string(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test zigpy and z2m index output with OTA header string.

    Z2M format includes otaHeaderString field, zigpy format does not.
    """
    images_path = tmp_path / "images"
    manufacturer_dir = images_path / "test_manufacturer"
    manufacturer_dir.mkdir(parents=True)

    # Copy existing fake OTA with header string
    src_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01003000-WithHeaderString.zigbee"
    )
    ota_file = manufacturer_dir / src_ota.name
    shutil.copy(src_ota, ota_file)

    # Create YAML metadata
    yaml_content = f"""file_name: {src_ota.name}
source_file_name: {src_ota.name}
source_url: https://example.com/{src_ota.name}
release_notes: Test release with header string
manufacturer_names:
  - Test Manufacturer
model_names:
  - Test Model
"""
    yaml_file = manufacturer_dir / f"{src_ota.name}.yaml"
    yaml_file.write_text(yaml_content)

    runner = CliRunner()

    # Generate zigpy index
    zigpy_output = tmp_path / ZIGPY_OTA_METADATA_OUTPUT_PATH.name
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--format",
            "zigpy",
            "--images-path",
            str(images_path),
            "--output-file",
            str(zigpy_output),
            "--tag",
            "test-tag",
        ],
    )
    assert result.exit_code == 0, f"zigpy index failed: {result.output}"

    # Generate z2m index
    z2m_output = tmp_path / Z2M_OTA_METADATA_OUTPUT_PATH.name
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--format",
            "z2m",
            "--images-path",
            str(images_path),
            "--output-file",
            str(z2m_output),
            "--tag",
            "test-tag",
        ],
    )
    assert result.exit_code == 0, f"z2m index failed: {result.output}"

    # Load both outputs
    with zigpy_output.open("r") as f:
        zigpy_data = json.load(f)
    with z2m_output.open("r") as f:
        z2m_data = json.load(f)

    # Snapshot both formats
    assert {
        "zigpy": zigpy_data,
        "z2m": z2m_data,
    } == snapshot


def test_disabled_flag_excludes_from_json(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test that images with 'disabled: true' in YAML are excluded from JSON index."""
    test_data_path = Path("tests/data/test_disabled")
    output_file = tmp_path / "test_zigpy_ota_metadata.json"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(test_data_path),
            "--output-file",
            str(output_file),
            "--tag",
            "test-tag",
            "--no-allow-missing-yaml",  # Explicitly use default strict mode
        ],
    )

    assert result.exit_code == 0, f"Command failed with output: {result.output}"

    # Load the JSON
    with output_file.open("r") as f:
        data = json.load(f)

    # Validate against zigpy schema
    validate_ota_index_schema(data)

    # Compare with snapshot
    assert json.dumps(data, indent=2) == snapshot


def test_generate_index_markdown_format(
    snapshot: SnapshotAssertion, tmp_path: Path
) -> None:
    """Test that generate-index creates valid markdown output."""
    test_data_path = Path("tests/data/test_disabled")
    output_file = tmp_path / "test_ota_index.md"

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--format",
            "markdown",
            "--images-path",
            str(test_data_path),
            "--output-file",
            str(output_file),
            "--tag",
            "test-tag",
            "--channel",
            "dev",  # Include all images
        ],
    )

    assert result.exit_code == 0, f"Command failed with output: {result.output}"
    assert output_file.exists(), "Output file was not created"

    # Read the markdown content
    markdown_content = output_file.read_text()

    # Compare with snapshot
    assert markdown_content == snapshot


def test_fail_on_missing_yaml_metadata(tmp_path: Path) -> None:
    """Test that --allow-missing-yaml CLI option works correctly.

    Verifies that the command fails by default when YAML metadata is missing,
    but succeeds when --allow-missing-yaml flag is provided."""
    # Create separate directories for images and output
    images_path = tmp_path / "images"
    output_path = tmp_path / "output"
    output_path.mkdir(exist_ok=True)

    # Create test directory with OTA file but no YAML
    manufacturer_dir = images_path / "test_manufacturer"
    manufacturer_dir.mkdir(parents=True)

    # Copy OTA file without creating corresponding YAML
    src_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    ota_file = manufacturer_dir / "fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    shutil.copy(src_ota, ota_file)

    output_file = output_path / "test_zigpy_ota_metadata.json"
    runner = CliRunner()

    # Test 1: With --allow-missing-yaml flag (should succeed)
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
            "--allow-missing-yaml",
        ],
    )
    assert result.exit_code == 0, f"Command should succeed: {result.output}"

    # Test 2: Without --allow-missing-yaml flag (default, should fail)
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
        ],
    )
    assert result.exit_code != 0, "Command should fail with missing YAML (default)"
    assert result.exception is not None, "Should have raised an exception"
    assert isinstance(result.exception, ValueError), (
        f"Expected ValueError, got {type(result.exception)}"
    )
    assert "Missing YAML metadata" in str(result.exception)


def test_allow_inconsistent_yaml_option(tmp_path: Path) -> None:
    """Test that --allow-inconsistent-yaml CLI option works correctly.

    Verifies that the command fails by default when a third-party YAML exists
    with a corresponding local OTA file (inconsistent state), but succeeds when
    --allow-inconsistent-yaml flag is provided."""
    # Create separate directories for images and output
    images_path = tmp_path / "images"
    output_path = tmp_path / "output"
    output_path.mkdir(exist_ok=True)

    # Create test directory
    manufacturer_dir = images_path / "test_manufacturer"
    manufacturer_dir.mkdir(parents=True)

    # Copy OTA file
    src_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee"
    )
    ota_file = manufacturer_dir / "test.zigbee"
    shutil.copy(src_ota, ota_file)

    # Create a third-party YAML for the same file (inconsistent state)
    yaml_content = """# OTA metadata for test.zigbee
file_name: test.zigbee
source_file_name: test.zigbee
source_url: https://example.com/test.zigbee
third_party_download:
  manufacturer_id: 4107
  image_type: 268
  file_version: 16786688
  file_size: 126
  checksum_sha3_256: 7104c0da6f0dd13cb212484e46f472216afcbf31f7e3ed40f51c68fc8978e890
  checksum_sha512: 3563f9adbeaa4130252e39b741a7ff37e8e4aebd6e1d4886e2ed97f28f1c4686206782ab02246595313863639f583d9446ca63ad0af699850e1201e2db6dcd83
release_notes: |
  - Test release
"""
    yaml_file = manufacturer_dir / "test.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    output_file = output_path / "test_zigpy_ota_metadata.json"
    runner = CliRunner()

    # Test 1: With --allow-inconsistent-yaml flag (should succeed)
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
            "--allow-inconsistent-yaml",
        ],
    )
    assert result.exit_code == 0, f"Command should succeed: {result.output}"

    # Test 2: Without --allow-inconsistent-yaml flag (default, should fail)
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
        ],
    )
    assert result.exit_code != 0, "Command should fail with inconsistent YAML (default)"
    assert result.exception is not None, "Should have raised an exception"
    assert isinstance(result.exception, ValueError), (
        f"Expected ValueError, got {type(result.exception)}"
    )
    assert "Repository inconsistency detected" in str(result.exception)


def _make_index_metadata(
    manufacturer_id: int,
    image_type: int,
    file_version: int,
    min_current_file_version: int | None = None,
    max_current_file_version: int | None = None,
    channel: Channel = Channel.STABLE,
    model_names: tuple[str, ...] | None = None,
) -> IndexMetadata:
    """Helper to create IndexMetadata for testing."""
    file_name = f"{manufacturer_id}-{image_type}-{file_version}.zigbee"
    return IndexMetadata(
        binary_url=f"https://example.com/{file_name}",
        manufacturer_id=manufacturer_id,
        image_type=image_type,
        file_version=file_version,
        file_size=1000,
        checksum_sha3_256="abc123",
        checksum_sha512="def456",
        source_file_name=file_name,
        min_current_file_version=min_current_file_version,
        max_current_file_version=max_current_file_version,
        channel=channel,
        model_names=model_names,
    )


class TestComputeMaxFileVersions:
    """Tests for compute_max_file_versions helper function."""

    def test_no_min_version_constraints(self) -> None:
        """No max versions computed when no images have min_current_file_version."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/v200.zigbee": _make_index_metadata(100, 1, 200),
            "mfr/v300.zigbee": _make_index_metadata(100, 1, 300),
        }
        result = compute_max_file_versions(metadata)
        assert result == {}

    def test_one_image_with_min_version(self) -> None:
        """Set max_current_file_version on older images when any has min_current_file_version."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, min_current_file_version=100
            ),
            "mfr/v300.zigbee": _make_index_metadata(
                100, 1, 300, min_current_file_version=200
            ),
        }
        result = compute_max_file_versions(metadata)
        # v100 and v200 should get max versions, v300 (newest) should not
        assert result == {
            "mfr/v100.zigbee": 99,  # 100 - 1
            "mfr/v200.zigbee": 199,  # 200 - 1
        }

    def test_newest_image_not_modified(self) -> None:
        """Newest image (highest file_version) should not get max_current_file_version."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/v300.zigbee": _make_index_metadata(
                100, 1, 300, min_current_file_version=100
            ),
        }
        result = compute_max_file_versions(metadata)
        assert result == {"mfr/v100.zigbee": 99}
        assert "mfr/v300.zigbee" not in result

    def test_explicit_max_version_preserved(self) -> None:
        """Images with explicit max_current_file_version are not overwritten."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(
                100, 1, 100, max_current_file_version=150
            ),
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, min_current_file_version=100
            ),
        }
        result = compute_max_file_versions(metadata)
        # v100 already has explicit max, so should not be in computed results
        assert result == {}

    def test_different_image_types_independent(self) -> None:
        """Different (manufacturer_id, image_type) groups are processed independently."""
        metadata = {
            # Group 1: manufacturer 100, image type 1
            "mfr/type1-v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/type1-v200.zigbee": _make_index_metadata(
                100, 1, 200, min_current_file_version=100
            ),
            # Group 2: manufacturer 100, image type 2 - no min_current_file_version
            "mfr/type2-v100.zigbee": _make_index_metadata(100, 2, 100),
            "mfr/type2-v200.zigbee": _make_index_metadata(100, 2, 200),
        }
        result = compute_max_file_versions(metadata)
        # Only group 1 should have computed max versions
        assert result == {"mfr/type1-v100.zigbee": 99}
        assert "mfr/type2-v100.zigbee" not in result
        assert "mfr/type2-v200.zigbee" not in result

    def test_single_image_with_min_version(self) -> None:
        """A single image with min_current_file_version should not get max version.

        This tests the scenario after filtering: if disabled images are filtered out
        before calling this function, only non-disabled images are processed.
        Filtering is handled by _filter_metadata_by_channel, not this function.
        """
        # Only non-disabled images should be passed (filtering happens before)
        metadata = {
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, min_current_file_version=100
            ),
        }
        result = compute_max_file_versions(metadata)
        # v200 is the only (and newest) image, so no max version set
        assert result == {}


class TestValidateUnreachableImages:
    """Tests for validate_unreachable_images."""

    def test_reachable_images_pass(self) -> None:
        """Ordinary images, including constrained ones, are not flagged."""
        metadata = {
            "mfr/plain.zigbee": _make_index_metadata(100, 1, 200),
            "mfr/constrained.zigbee": _make_index_metadata(
                100, 1, 300, min_current_file_version=200, max_current_file_version=299
            ),
        }
        assert validate_unreachable_images(metadata, fail_on_unreachable=True) == []

    @pytest.mark.parametrize(
        ("meta", "reason"),
        [
            # min at/above the image's own version: only offered below it
            pytest.param(
                _make_index_metadata(100, 1, 200, min_current_file_version=200),
                "empty current-version range",
                id="min_equals_file_version",
            ),
            # min above explicit max
            pytest.param(
                _make_index_metadata(
                    100,
                    1,
                    200,
                    min_current_file_version=50,
                    max_current_file_version=40,
                ),
                "empty current-version range",
                id="min_above_max",
            ),
            # file_version 0 can never be an upgrade (current < 0 is impossible)
            pytest.param(
                _make_index_metadata(100, 1, 0),
                "empty current-version range",
                id="file_version_zero",
            ),
            pytest.param(
                dataclasses.replace(
                    _make_index_metadata(100, 1, 200),
                    min_hardware_version=5,
                    max_hardware_version=2,
                ),
                "empty hardware-version range",
                id="empty_hw_range",
            ),
        ],
    )
    def test_unreachable_images_flagged(self, meta: IndexMetadata, reason: str) -> None:
        """Images that can never match any device are flagged and can raise."""
        metadata = {"mfr/image.zigbee": meta}

        result = validate_unreachable_images(metadata, fail_on_unreachable=False)
        assert len(result) == 1
        assert reason in result[0]

        with pytest.raises(ValueError, match="Unreachable images detected"):
            validate_unreachable_images(metadata, fail_on_unreachable=True)

    def test_disabled_images_skipped(self) -> None:
        """Disabled images never ship in an index and are not flagged."""
        metadata = {
            "mfr/disabled.zigbee": dataclasses.replace(
                _make_index_metadata(100, 1, 200, min_current_file_version=200),
                disabled=True,
            ),
        }
        assert validate_unreachable_images(metadata, fail_on_unreachable=True) == []


def test_generate_index_fails_on_unreachable_image(tmp_path: Path) -> None:
    """generate-index fails on unreachable images unless --allow-unreachable."""
    images_path = tmp_path / "images"
    manufacturer_dir = images_path / "test_manufacturer"
    manufacturer_dir.mkdir(parents=True)

    ota_file = "fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    shutil.copy(Path("tests/data/ota_files") / ota_file, manufacturer_dir / ota_file)
    # min == the image's own file version -> empty effective range
    (manufacturer_dir / f"{ota_file}.yaml").write_text(
        f"""file_name: {ota_file}
source_file_name: {ota_file}
source_url: https://example.com/{ota_file}
min_current_file_version: 0x01001A02
"""
    )

    runner = CliRunner()
    args = [
        "generate-index",
        "--images-path",
        str(images_path),
        "--output-file",
        str(tmp_path / "out.json"),
    ]

    result = runner.invoke(cli, args)
    assert result.exit_code != 0
    assert isinstance(result.exception, ValueError)
    assert "Unreachable images detected" in str(result.exception)

    result = runner.invoke(cli, [*args, "--allow-unreachable"])
    assert result.exit_code == 0, f"Command failed with output: {result.output}"


def test_z2m_format_header_hardware_versions_end_to_end(tmp_path: Path) -> None:
    """Header-derived hardware versions reach the z2m index (full pipeline).

    Mirrors real-world case: the constraints live in the OTA header (not the
    YAML) and must survive parsing, merging, and z2m output.
    """
    images_path = tmp_path / "images"
    manufacturer_dir = images_path / "test_manufacturer"
    manufacturer_dir.mkdir(parents=True)

    # Different image types so neither image is stale (stale is excluded from z2m)
    generate_fake_ota_image(
        output_path=manufacturer_dir / "hw_constrained.zigbee",
        manufacturer_id=0x100B,
        image_type=0x0001,
        file_version=0x00000005,
        min_hardware_version=2,
        max_hardware_version=5,
    )
    generate_fake_ota_image(
        output_path=manufacturer_dir / "unconstrained.zigbee",
        manufacturer_id=0x100B,
        image_type=0x0002,
        file_version=0x00000005,
    )
    for name in ("hw_constrained.zigbee", "unconstrained.zigbee"):
        (manufacturer_dir / f"{name}.yaml").write_text(
            f"""file_name: {name}
source_file_name: {name}
source_url: https://example.com/{name}
"""
        )

    output_file = tmp_path / "z2m.json"
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--format",
            "z2m",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
        ],
    )
    assert result.exit_code == 0, f"Command failed with output: {result.output}"

    with output_file.open("r") as f:
        data = json.load(f)

    validate_z2m_index_schema(data)

    entries = {entry["fileName"]: entry for entry in data}
    assert entries["hw_constrained.zigbee"]["hardwareVersionMin"] == 2
    assert entries["hw_constrained.zigbee"]["hardwareVersionMax"] == 5
    assert "hardwareVersionMin" not in entries["unconstrained.zigbee"]
    assert "hardwareVersionMax" not in entries["unconstrained.zigbee"]


def test_z2m_dict_includes_hardware_versions() -> None:
    """Hardware version constraints are emitted for zigbee-herdsman matching."""
    meta = dataclasses.replace(
        _make_index_metadata(100, 1, 200),
        min_hardware_version=2,
        max_hardware_version=5,
    )
    result = meta.to_dict_z2m()
    assert result["hardwareVersionMin"] == 2
    assert result["hardwareVersionMax"] == 5

    # Omitted entirely when unconstrained
    unconstrained = _make_index_metadata(100, 1, 200).to_dict_z2m()
    assert "hardwareVersionMin" not in unconstrained
    assert "hardwareVersionMax" not in unconstrained


def test_z2m_format_auto_max_file_version(tmp_path: Path) -> None:
    """Test that z2m format auto-sets maxFileVersion for version-constrained images."""
    images_path = tmp_path / "images"
    manufacturer_dir = images_path / "test_manufacturer"
    manufacturer_dir.mkdir(parents=True)

    # Copy 3 OTA files with same manufacturer ID and image type
    ota_files = [
        "fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee",  # oldest
        "fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee",  # middle
        "fake_100B-010C-01002602-ConfLight-Lamps_0012.zigbee",  # newest
    ]
    for ota_file in ota_files:
        src = Path("tests/data/ota_files") / ota_file
        shutil.copy(src, manufacturer_dir / ota_file)

    # Create YAML files - middle and newest have min_current_file_version
    yaml_configs = [
        # Oldest: no constraints
        (
            ota_files[0],
            """file_name: {0}
source_file_name: {0}
source_url: https://example.com/{0}
""",
        ),
        # Middle: min constraint requiring oldest version
        (
            ota_files[1],
            """file_name: {0}
source_file_name: {0}
source_url: https://example.com/{0}
min_current_file_version: 0x01001A02
""",
        ),
        # Newest: min constraint requiring middle version
        (
            ota_files[2],
            """file_name: {0}
source_file_name: {0}
source_url: https://example.com/{0}
min_current_file_version: 0x01002500
""",
        ),
    ]

    for ota_file, yaml_template in yaml_configs:
        yaml_content = yaml_template.format(ota_file)
        yaml_path = manufacturer_dir / f"{ota_file}.yaml"
        yaml_path.write_text(yaml_content)

    output_file = tmp_path / Z2M_OTA_METADATA_OUTPUT_PATH.name
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--format",
            "z2m",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
            "--tag",
            "test-tag",
        ],
    )

    assert result.exit_code == 0, f"Command failed: {result.output}"

    with output_file.open("r") as f:
        data = json.load(f)

    assert len(data) == 3

    # Sort by fileVersion to get predictable order
    sorted_data = sorted(data, key=lambda x: x["fileVersion"])

    # Oldest (v0x01001A02 = 16783874): should have maxFileVersion = 16783873
    assert sorted_data[0]["fileVersion"] == 0x01001A02
    assert sorted_data[0]["maxFileVersion"] == 0x01001A02 - 1
    assert "minFileVersion" not in sorted_data[0]

    # Middle (v0x01002500 = 16786688): should have maxFileVersion = 16786687
    assert sorted_data[1]["fileVersion"] == 0x01002500
    assert sorted_data[1]["maxFileVersion"] == 0x01002500 - 1
    assert sorted_data[1]["minFileVersion"] == 0x01001A02

    # Newest (v0x01002602 = 16786946): NO maxFileVersion (newest)
    assert sorted_data[2]["fileVersion"] == 0x01002602
    assert "maxFileVersion" not in sorted_data[2]
    assert sorted_data[2]["minFileVersion"] == 0x01002500


def test_zigpy_format_sorted_by_dir_manufacturer_image_type_version_asc() -> None:
    """Test zigpy sort order: dir, manufacturer_id, image_type, file_version asc."""
    metadata = {
        # Directory "zebra", manufacturer 100
        "zebra/type1_v300.zigbee": _make_index_metadata(100, 1, 300),
        "zebra/type1_v150.zigbee": _make_index_metadata(100, 1, 150),
        # Directory "alpha", manufacturer 200 (higher mfr_id but earlier dir)
        "alpha/type1_v400.zigbee": _make_index_metadata(200, 1, 400),
        "alpha/type1_v250.zigbee": _make_index_metadata(200, 1, 250),
        # Directory "alpha", manufacturer 100, image type 2
        "alpha/type2_v200.zigbee": _make_index_metadata(100, 2, 200),
        "alpha/type2_v100.zigbee": _make_index_metadata(100, 2, 100),
    }

    result = prepare_metadata_for_zigpy(metadata, channel=Channel.STABLE)

    assert len(result) == 6

    # Extract (manufacturer_id, image_type, file_version) tuples
    entries = [
        (entry["manufacturer_id"], entry["image_type"], entry["file_version"])
        for entry in result
    ]

    # Should be sorted by: dir asc, manufacturer_id asc, image_type asc, file_version asc
    assert entries == [
        # "alpha" directory first
        (100, 2, 100),  # alpha, mfr 100, type 2, oldest
        (100, 2, 200),  # alpha, mfr 100, type 2, newer
        (200, 1, 250),  # alpha, mfr 200, type 1, oldest
        (200, 1, 400),  # alpha, mfr 200, type 1, newer
        # "zebra" directory second
        (100, 1, 150),  # zebra, mfr 100, type 1, oldest
        (100, 1, 300),  # zebra, mfr 100, type 1, newer
    ]


def test_z2m_format_sorted_by_file_version_descending() -> None:
    """Test that Z2M format entries are sorted by fileVersion descending (newest first).

    Z2M's getImageMeta() uses Array.find() which returns the first match.
    Without descending sort, older versions would match first and potentially
    be rejected as "not an upgrade", with no fallback to newer versions.

    Each image has unique model_names to prevent stale detection (different devices).
    """
    # Create metadata with various file versions in non-sorted order
    # Each has unique model_names so none are stale
    metadata = {
        "mfr/v200.zigbee": _make_index_metadata(100, 1, 200, model_names=("Model B",)),
        "mfr/v100.zigbee": _make_index_metadata(100, 1, 100, model_names=("Model A",)),
        "mfr/v400.zigbee": _make_index_metadata(100, 1, 400, model_names=("Model D",)),
        "mfr/v300.zigbee": _make_index_metadata(100, 1, 300, model_names=("Model C",)),
    }

    result = prepare_metadata_for_z2m(metadata, channel=Channel.STABLE)

    # Should be sorted by fileVersion descending (newest first)
    assert len(result) == 4
    file_versions = [entry["fileVersion"] for entry in result]
    assert file_versions == [400, 300, 200, 100]


def test_z2m_format_sorted_by_dir_manufacturer_image_type_version_desc() -> None:
    """Test Z2M sort order: dir, manufacturer_id, image_type, file_version desc.

    Each image has unique model_names to prevent stale detection (different devices).
    """
    metadata = {
        # Directory "zebra", manufacturer 100
        "zebra/type1_v300.zigbee": _make_index_metadata(
            100, 1, 300, model_names=("Model F",)
        ),
        "zebra/type1_v150.zigbee": _make_index_metadata(
            100, 1, 150, model_names=("Model E",)
        ),
        # Directory "alpha", manufacturer 200 (higher mfr_id but earlier dir)
        "alpha/type1_v400.zigbee": _make_index_metadata(
            200, 1, 400, model_names=("Model D",)
        ),
        "alpha/type1_v250.zigbee": _make_index_metadata(
            200, 1, 250, model_names=("Model C",)
        ),
        # Directory "alpha", manufacturer 100, image type 2
        "alpha/type2_v200.zigbee": _make_index_metadata(
            100, 2, 200, model_names=("Model B",)
        ),
        "alpha/type2_v100.zigbee": _make_index_metadata(
            100, 2, 100, model_names=("Model A",)
        ),
    }

    result = prepare_metadata_for_z2m(metadata, channel=Channel.STABLE)

    assert len(result) == 6

    # Extract (manufacturer_id, image_type, file_version) tuples
    entries = [
        (entry["manufacturerCode"], entry["imageType"], entry["fileVersion"])
        for entry in result
    ]

    # Should be sorted by: dir asc, manufacturer_id asc, image_type asc, file_version desc
    assert entries == [
        # "alpha" directory first
        (100, 2, 200),  # alpha, mfr 100, type 2, newest
        (100, 2, 100),  # alpha, mfr 100, type 2, older
        (200, 1, 400),  # alpha, mfr 200, type 1, newest
        (200, 1, 250),  # alpha, mfr 200, type 1, older
        # "zebra" directory second
        (100, 1, 300),  # zebra, mfr 100, type 1, newest
        (100, 1, 150),  # zebra, mfr 100, type 1, older
    ]


class TestChannelFiltering:
    """Tests for channel-based filtering in index generation."""

    def test_stable_channel_excludes_beta_images(self) -> None:
        """Stable channel (default) should exclude images with channel='beta'."""
        metadata = {
            "mfr/stable.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/beta.zigbee": _make_index_metadata(100, 1, 200, channel=Channel.BETA),
        }
        result = prepare_metadata_for_zigpy(metadata, channel=Channel.STABLE)

        # Only stable image should be included
        assert len(result) == 1
        assert result[0]["file_version"] == 100

    def test_stable_channel_excludes_dev_images(self) -> None:
        """Stable channel should exclude images with channel='dev'."""
        metadata = {
            "mfr/stable.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/dev.zigbee": _make_index_metadata(100, 1, 200, channel=Channel.DEV),
        }
        result = prepare_metadata_for_zigpy(metadata, channel=Channel.STABLE)

        # Only stable image should be included
        assert len(result) == 1
        assert result[0]["file_version"] == 100

    def test_beta_channel_includes_stable_and_beta(self) -> None:
        """Beta channel should include both stable and beta images."""
        metadata = {
            "mfr/stable.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/beta.zigbee": _make_index_metadata(100, 1, 200, channel=Channel.BETA),
        }
        result = prepare_metadata_for_zigpy(metadata, channel=Channel.BETA)

        # Both images should be included
        assert len(result) == 2

    def test_beta_channel_excludes_dev_images(self) -> None:
        """Beta channel should exclude images with channel='dev'."""
        metadata = {
            "mfr/stable.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/beta.zigbee": _make_index_metadata(100, 1, 200, channel=Channel.BETA),
            "mfr/dev.zigbee": _make_index_metadata(100, 1, 300, channel=Channel.DEV),
        }
        result = prepare_metadata_for_zigpy(metadata, channel=Channel.BETA)

        # Only stable and beta images should be included
        assert len(result) == 2
        versions = {r["file_version"] for r in result}
        assert versions == {100, 200}

    def test_dev_channel_includes_all_images(self) -> None:
        """Dev channel should include stable, beta, and dev images."""
        metadata = {
            "mfr/stable.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/beta.zigbee": _make_index_metadata(100, 1, 200, channel=Channel.BETA),
            "mfr/dev.zigbee": _make_index_metadata(100, 1, 300, channel=Channel.DEV),
        }
        result = prepare_metadata_for_zigpy(metadata, channel=Channel.DEV)

        # All images should be included
        assert len(result) == 3

    def test_z2m_channel_filtering_stable(self) -> None:
        """Z2M format should also filter by channel."""
        metadata = {
            "mfr/stable.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/beta.zigbee": _make_index_metadata(100, 1, 200, channel=Channel.BETA),
        }
        result = prepare_metadata_for_z2m(metadata, channel=Channel.STABLE)

        # Only stable image should be included
        assert len(result) == 1
        assert result[0]["fileVersion"] == 100

    def test_z2m_channel_filtering_beta(self) -> None:
        """Z2M format should include stable and beta in beta channel."""
        metadata = {
            "mfr/stable.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/beta.zigbee": _make_index_metadata(100, 2, 200, channel=Channel.BETA),
        }
        result = prepare_metadata_for_z2m(metadata, channel=Channel.BETA)

        # Both images should be included
        assert len(result) == 2

    def test_z2m_channel_filtering_dev(self) -> None:
        """Z2M format should include all images in dev channel."""
        metadata = {
            "mfr/stable.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/beta.zigbee": _make_index_metadata(100, 2, 200, channel=Channel.BETA),
            "mfr/dev.zigbee": _make_index_metadata(100, 3, 300, channel=Channel.DEV),
        }
        result = prepare_metadata_for_z2m(metadata, channel=Channel.DEV)

        # All images should be included
        assert len(result) == 3

    def test_z2m_multiple_model_names_creates_duplicate_entries(self) -> None:
        """Z2M format should create duplicate entries for multiple model names."""
        metadata = {
            "mfr/multi_model.zigbee": _make_index_metadata(
                100,
                1,
                100,
                model_names=("Model A", "Model B", "Model C"),
            ),
        }
        result = prepare_metadata_for_z2m(metadata, channel=Channel.STABLE)

        # Should have 3 entries, one for each model name
        assert len(result) == 3

        # Verify each entry has the correct modelId
        model_ids = [entry["modelId"] for entry in result]
        assert model_ids == ["Model A", "Model B", "Model C"]

        # All entries should have the same base data
        for entry in result:
            assert entry["fileVersion"] == 100
            assert entry["manufacturerCode"] == 100
            assert entry["imageType"] == 1

    def test_z2m_single_model_name_no_duplication(self) -> None:
        """Z2M format should not duplicate entries for single model name."""
        metadata = {
            "mfr/single_model.zigbee": _make_index_metadata(
                100,
                1,
                100,
                model_names=("Model A",),
            ),
        }
        result = prepare_metadata_for_z2m(metadata, channel=Channel.STABLE)

        # Should have 1 entry
        assert len(result) == 1
        assert result[0]["modelId"] == "Model A"

    def test_z2m_no_model_names_no_model_id(self) -> None:
        """Z2M format should not include modelId if no model names."""
        metadata = {
            "mfr/no_model.zigbee": _make_index_metadata(100, 1, 100),
        }
        result = prepare_metadata_for_z2m(metadata, channel=Channel.STABLE)

        # Should have 1 entry without modelId
        assert len(result) == 1
        assert "modelId" not in result[0]

    def test_all_stable_images_pass_through(self) -> None:
        """All images without channel set should be included in any channel."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/v200.zigbee": _make_index_metadata(100, 1, 200),
            "mfr/v300.zigbee": _make_index_metadata(100, 1, 300),
        }

        stable_result = prepare_metadata_for_zigpy(metadata, channel=Channel.STABLE)
        beta_result = prepare_metadata_for_zigpy(metadata, channel=Channel.BETA)
        dev_result = prepare_metadata_for_zigpy(metadata, channel=Channel.DEV)

        # All three should be included in all channels
        assert len(stable_result) == 3
        assert len(beta_result) == 3
        assert len(dev_result) == 3


def test_channel_cli_option_stable(tmp_path: Path) -> None:
    """Test that --channel stable excludes beta images from CLI."""
    images_path = tmp_path / "images"
    manufacturer_dir = images_path / "test_manufacturer"
    manufacturer_dir.mkdir(parents=True)

    # Copy OTA file
    src_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    ota_file = manufacturer_dir / "test_beta.zigbee"
    shutil.copy(src_ota, ota_file)

    # Create YAML with channel: beta
    yaml_content = """file_name: test_beta.zigbee
source_file_name: test_beta.zigbee
source_url: https://example.com/test_beta.zigbee
channel: beta
"""
    yaml_file = manufacturer_dir / "test_beta.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    output_file = tmp_path / "test_zigpy_ota.json"
    runner = CliRunner()

    # Test with stable channel (default)
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
            "--channel",
            "stable",
        ],
    )

    assert result.exit_code == 0, f"Command failed: {result.output}"

    with output_file.open("r") as f:
        data = json.load(f)

    # Beta image should be excluded
    assert len(data["firmwares"]) == 0


def test_channel_cli_option_beta(tmp_path: Path) -> None:
    """Test that --channel beta includes beta images from CLI."""
    images_path = tmp_path / "images"
    manufacturer_dir = images_path / "test_manufacturer"
    manufacturer_dir.mkdir(parents=True)

    # Copy OTA file
    src_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    ota_file = manufacturer_dir / "test_beta.zigbee"
    shutil.copy(src_ota, ota_file)

    # Create YAML with channel: beta
    yaml_content = """file_name: test_beta.zigbee
source_file_name: test_beta.zigbee
source_url: https://example.com/test_beta.zigbee
channel: beta
"""
    yaml_file = manufacturer_dir / "test_beta.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    output_file = tmp_path / "test_zigpy_ota.json"
    runner = CliRunner()

    # Test with beta channel
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
            "--channel",
            "beta",
        ],
    )

    assert result.exit_code == 0, f"Command failed: {result.output}"

    with output_file.open("r") as f:
        data = json.load(f)

    # Beta image should be included
    assert len(data["firmwares"]) == 1


def test_channel_cli_option_dev(tmp_path: Path) -> None:
    """Test that --channel dev includes all images from CLI."""
    images_path = tmp_path / "images"
    manufacturer_dir = images_path / "test_manufacturer"
    manufacturer_dir.mkdir(parents=True)

    # Copy OTA file for dev image
    src_ota = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    ota_file = manufacturer_dir / "test_dev.zigbee"
    shutil.copy(src_ota, ota_file)

    # Create YAML with channel: dev
    yaml_content = """file_name: test_dev.zigbee
source_file_name: test_dev.zigbee
source_url: https://example.com/test_dev.zigbee
channel: dev
"""
    yaml_file = manufacturer_dir / "test_dev.zigbee.yaml"
    yaml_file.write_text(yaml_content)

    output_file = tmp_path / "test_zigpy_ota.json"
    runner = CliRunner()

    # Test with dev channel - should include dev image
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
            "--channel",
            "dev",
        ],
    )

    assert result.exit_code == 0, f"Command failed: {result.output}"

    with output_file.open("r") as f:
        data = json.load(f)

    # Dev image should be included
    assert len(data["firmwares"]) == 1

    # Test with beta channel - should exclude dev image
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
            "--channel",
            "beta",
        ],
    )

    assert result.exit_code == 0, f"Command failed: {result.output}"

    with output_file.open("r") as f:
        data = json.load(f)

    # Dev image should be excluded in beta channel
    assert len(data["firmwares"]) == 0


class TestComputeSpecificity:
    """Tests for compute_specificity function."""

    def test_base_specificity(self) -> None:
        """Base specificity is 200 (100 for image_type + 100 for manufacturer_id)."""
        meta = _make_index_metadata(100, 1, 100)
        assert compute_specificity(meta) == 200

    def test_manufacturer_names_adds_1000(self) -> None:
        """manufacturer_names adds 1000 to specificity."""
        meta = IndexMetadata(
            binary_url="https://example.com/test.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="abc123",
            checksum_sha512="def456",
            source_file_name="test.zigbee",
            manufacturer_names=("Manufacturer",),
        )
        assert compute_specificity(meta) == 1200  # 200 + 1000

    def test_model_names_adds_1000(self) -> None:
        """model_names adds 1000 to specificity."""
        meta = _make_index_metadata(100, 1, 100, model_names=("Model",))
        assert compute_specificity(meta) == 1200  # 200 + 1000

    def test_version_constraints_add_10_each(self) -> None:
        """min/max_current_file_version each add 10 to specificity."""
        # min only
        meta = _make_index_metadata(100, 1, 100, min_current_file_version=50)
        assert compute_specificity(meta) == 210  # 200 + 10

        # max only
        meta = _make_index_metadata(100, 1, 100, max_current_file_version=150)
        assert compute_specificity(meta) == 210  # 200 + 10

        # both
        meta = _make_index_metadata(
            100, 1, 100, min_current_file_version=50, max_current_file_version=150
        )
        assert compute_specificity(meta) == 220  # 200 + 10 + 10

    def test_hardware_versions_add_1_each(self) -> None:
        """min/max_hardware_version each add 1 to specificity."""
        meta = IndexMetadata(
            binary_url="https://example.com/test.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="abc123",
            checksum_sha512="def456",
            source_file_name="test.zigbee",
            min_hardware_version=1,
            max_hardware_version=5,
        )
        assert compute_specificity(meta) == 202  # 200 + 1 + 1

    def test_explicit_specificity_boost(self) -> None:
        """Explicit specificity value is added to computed specificity."""
        meta = IndexMetadata(
            binary_url="https://example.com/test.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="abc123",
            checksum_sha512="def456",
            source_file_name="test.zigbee",
            specificity=50,
        )
        assert compute_specificity(meta) == 250  # 200 + 50


class TestValidateCollisions:
    """Tests for validate_collisions function."""

    def test_no_collisions_with_different_versions(self) -> None:
        """No collisions when images have different versions."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/v200.zigbee": _make_index_metadata(100, 1, 200),
        }
        collisions = validate_collisions(metadata)
        assert collisions == []

    def test_no_collisions_with_same_checksum(self) -> None:
        """No collision when same version+specificity have identical checksums."""
        # Same checksum = same content = not a collision (duplicates are ok)
        meta1 = IndexMetadata(
            binary_url="https://example.com/test1.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="same_checksum",
            checksum_sha512="def456",
            source_file_name="test1.zigbee",
        )
        meta2 = IndexMetadata(
            binary_url="https://example.com/test2.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="same_checksum",  # Same checksum
            checksum_sha512="def456",
            source_file_name="test2.zigbee",
        )
        metadata = {
            "mfr/test1.zigbee": meta1,
            "mfr/test2.zigbee": meta2,
        }
        collisions = validate_collisions(metadata)
        assert collisions == []

    def test_collision_with_different_checksums(self) -> None:
        """Collision detected when same version+specificity have different checksums."""
        meta1 = IndexMetadata(
            binary_url="https://example.com/test1.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="checksum_a",
            checksum_sha512="def456",
            source_file_name="test1.zigbee",
        )
        meta2 = IndexMetadata(
            binary_url="https://example.com/test2.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="checksum_b",  # Different checksum
            checksum_sha512="def456",
            source_file_name="test2.zigbee",
        )
        metadata = {
            "mfr/test1.zigbee": meta1,
            "mfr/test2.zigbee": meta2,
        }
        collisions = validate_collisions(metadata)
        assert len(collisions) == 1
        assert collisions[0].manufacturer_id == 100
        assert collisions[0].image_type == 1
        assert collisions[0].file_version == 100
        assert len(collisions[0].images) == 2

    def test_no_collision_with_different_specificity(self) -> None:
        """No collision when same version but different specificity."""
        # Different specificity (model_names adds 1000)
        meta1 = IndexMetadata(
            binary_url="https://example.com/test1.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="checksum_a",
            checksum_sha512="def456",
            source_file_name="test1.zigbee",
        )
        meta2 = IndexMetadata(
            binary_url="https://example.com/test2.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="checksum_b",
            checksum_sha512="def456",
            source_file_name="test2.zigbee",
            model_names=("Model X",),  # Higher specificity
        )
        metadata = {
            "mfr/test1.zigbee": meta1,
            "mfr/test2.zigbee": meta2,
        }
        collisions = validate_collisions(metadata)
        assert collisions == []

    def test_collision_raises_with_fail_flag(self) -> None:
        """ValueError raised when fail_on_collision=True and collision detected."""
        meta1 = IndexMetadata(
            binary_url="https://example.com/test1.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="checksum_a",
            checksum_sha512="def456",
            source_file_name="test1.zigbee",
        )
        meta2 = IndexMetadata(
            binary_url="https://example.com/test2.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="checksum_b",
            checksum_sha512="def456",
            source_file_name="test2.zigbee",
        )
        metadata = {
            "mfr/test1.zigbee": meta1,
            "mfr/test2.zigbee": meta2,
        }

        with pytest.raises(ValueError, match="OTA image collision"):
            validate_collisions(metadata, fail_on_collision=True)

    def test_no_collision_with_disjoint_model_names(self) -> None:
        """Two images with disjoint model_names cannot collide at runtime.

        zigpy's check_compatibility filters by model_names before its
        collision check, so a device with model "A" only ever sees the
        first image and a device with model "B" only ever sees the
        second. The validator should not flag this even though the
        matching key is identical.
        """
        meta_a = IndexMetadata(
            binary_url="https://example.com/test_a.zigbee",
            manufacturer_id=0x1407,
            image_type=0xD3B4,
            file_version=47,
            file_size=1000,
            checksum_sha3_256="hash_a",
            checksum_sha512="def456",
            source_file_name="test_a.zigbee",
            model_names=("3RSPU01080Z",),
        )
        meta_b = IndexMetadata(
            binary_url="https://example.com/test_b.zigbee",
            manufacturer_id=0x1407,
            image_type=0xD3B4,
            file_version=47,
            file_size=1000,
            checksum_sha3_256="hash_b",
            checksum_sha512="def456",
            source_file_name="test_b.zigbee",
            model_names=("3RSP02064Z",),
        )
        metadata = {"mfr/a.zigbee": meta_a, "mfr/b.zigbee": meta_b}
        assert validate_collisions(metadata) == []

    def test_collision_when_one_image_has_no_model_names(self) -> None:
        """Asymmetric case: an unconstrained image absorbs all devices.

        An image without model_names matches any device, including those
        targeted by the constrained image, so the two can collide on the
        shared model. We bump the unconstrained image's specificity with
        an explicit ``specificity`` value so the two land in the same
        group despite the +1000 from the other's ``model_names``.
        """
        meta_constrained = IndexMetadata(
            binary_url="https://example.com/c.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_c",
            checksum_sha512="def456",
            source_file_name="c.zigbee",
            model_names=("Model A",),
        )
        meta_unconstrained = IndexMetadata(
            binary_url="https://example.com/u.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_u",
            checksum_sha512="def456",
            source_file_name="u.zigbee",
            specificity=1000,
        )
        assert compute_specificity(meta_constrained) == compute_specificity(
            meta_unconstrained
        )

        metadata = {
            "mfr/c.zigbee": meta_constrained,
            "mfr/u.zigbee": meta_unconstrained,
        }
        collisions = validate_collisions(metadata)
        assert len(collisions) == 1
        assert {path for path, _ in collisions[0].images} == {
            "mfr/c.zigbee",
            "mfr/u.zigbee",
        }

    def test_disjoint_hardware_version_ranges_do_not_collide(self) -> None:
        """Images covering non-overlapping hardware version ranges cannot collide."""
        meta_low = IndexMetadata(
            binary_url="https://example.com/low.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_low",
            checksum_sha512="def456",
            source_file_name="low.zigbee",
            min_hardware_version=1,
            max_hardware_version=5,
        )
        meta_high = IndexMetadata(
            binary_url="https://example.com/high.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_high",
            checksum_sha512="def456",
            source_file_name="high.zigbee",
            min_hardware_version=6,
            max_hardware_version=10,
        )
        metadata = {"mfr/low.zigbee": meta_low, "mfr/high.zigbee": meta_high}
        assert validate_collisions(metadata) == []

    def test_disjoint_current_file_version_ranges_do_not_collide(self) -> None:
        """Images covering non-overlapping current-fv ranges cannot collide."""
        meta_low = IndexMetadata(
            binary_url="https://example.com/low.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_low",
            checksum_sha512="def456",
            source_file_name="low.zigbee",
            min_current_file_version=0,
            max_current_file_version=40,
        )
        meta_high = IndexMetadata(
            binary_url="https://example.com/high.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_high",
            checksum_sha512="def456",
            source_file_name="high.zigbee",
            min_current_file_version=41,
            max_current_file_version=99,
        )
        metadata = {"mfr/low.zigbee": meta_low, "mfr/high.zigbee": meta_high}
        assert validate_collisions(metadata) == []

    def test_three_disjoint_images_produce_no_collision(self) -> None:
        """Three images with pairwise-disjoint model_names: no collisions."""
        metas = []
        for i, model in enumerate(("Model A", "Model B", "Model C")):
            metas.append(
                IndexMetadata(
                    binary_url=f"https://example.com/test{i}.zigbee",
                    manufacturer_id=100,
                    image_type=1,
                    file_version=100,
                    file_size=1000,
                    checksum_sha3_256=f"hash_{i}",
                    checksum_sha512="def456",
                    source_file_name=f"test{i}.zigbee",
                    model_names=(model,),
                )
            )
        metadata = {f"mfr/test{i}.zigbee": m for i, m in enumerate(metas)}
        assert validate_collisions(metadata) == []

    def test_no_collision_with_disjoint_manufacturer_names(self) -> None:
        """Disjoint manufacturer_names lists exempt a group from collisions."""
        meta_a = IndexMetadata(
            binary_url="https://example.com/a.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_a",
            checksum_sha512="def456",
            source_file_name="a.zigbee",
            manufacturer_names=("Mfr A",),
        )
        meta_b = IndexMetadata(
            binary_url="https://example.com/b.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_b",
            checksum_sha512="def456",
            source_file_name="b.zigbee",
            manufacturer_names=("Mfr B",),
        )
        metadata = {"mfr/a.zigbee": meta_a, "mfr/b.zigbee": meta_b}
        assert validate_collisions(metadata) == []

    def test_collision_with_overlapping_hardware_version_ranges(self) -> None:
        """Overlapping hardware version ranges still produce a collision."""
        meta_a = IndexMetadata(
            binary_url="https://example.com/a.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_a",
            checksum_sha512="def456",
            source_file_name="a.zigbee",
            min_hardware_version=1,
            max_hardware_version=5,
        )
        meta_b = IndexMetadata(
            binary_url="https://example.com/b.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_b",
            checksum_sha512="def456",
            source_file_name="b.zigbee",
            min_hardware_version=3,
            max_hardware_version=7,
        )
        metadata = {"mfr/a.zigbee": meta_a, "mfr/b.zigbee": meta_b}
        collisions = validate_collisions(metadata)
        assert len(collisions) == 1
        assert {path for path, _ in collisions[0].images} == {
            "mfr/a.zigbee",
            "mfr/b.zigbee",
        }

    def test_collision_with_three_mutually_compatible_images(self) -> None:
        """Three transitively-compatible images merge into a single collision.

        Also exercises the union-find skip path when find(i) == find(j).
        """
        meta_a = IndexMetadata(
            binary_url="https://example.com/a.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_a",
            checksum_sha512="def456",
            source_file_name="a.zigbee",
            model_names=("Model M",),
        )
        meta_b = IndexMetadata(
            binary_url="https://example.com/b.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_b",
            checksum_sha512="def456",
            source_file_name="b.zigbee",
            model_names=("Model M",),
        )
        meta_c = IndexMetadata(
            binary_url="https://example.com/c.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_c",
            checksum_sha512="def456",
            source_file_name="c.zigbee",
            model_names=("Model M",),
        )
        metadata = {
            "mfr/a.zigbee": meta_a,
            "mfr/b.zigbee": meta_b,
            "mfr/c.zigbee": meta_c,
        }
        collisions = validate_collisions(metadata)
        assert len(collisions) == 1
        assert {path for path, _ in collisions[0].images} == {
            "mfr/a.zigbee",
            "mfr/b.zigbee",
            "mfr/c.zigbee",
        }

    def test_collision_with_overlapping_current_file_version_ranges(self) -> None:
        """Overlapping current_file_version ranges still produce a collision."""
        meta_a = IndexMetadata(
            binary_url="https://example.com/a.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_a",
            checksum_sha512="def456",
            source_file_name="a.zigbee",
            min_current_file_version=0,
            max_current_file_version=50,
        )
        meta_b = IndexMetadata(
            binary_url="https://example.com/b.zigbee",
            manufacturer_id=100,
            image_type=1,
            file_version=100,
            file_size=1000,
            checksum_sha3_256="hash_b",
            checksum_sha512="def456",
            source_file_name="b.zigbee",
            min_current_file_version=30,
            max_current_file_version=80,
        )
        metadata = {"mfr/a.zigbee": meta_a, "mfr/b.zigbee": meta_b}
        collisions = validate_collisions(metadata)
        assert len(collisions) == 1
        assert {path for path, _ in collisions[0].images} == {
            "mfr/a.zigbee",
            "mfr/b.zigbee",
        }


def test_collision_cli_option(tmp_path: Path) -> None:
    """Test that --fail-on-collision option works correctly."""
    # Create separate directories for images and output
    images_path = tmp_path / "images"
    output_path = tmp_path / "output"
    output_path.mkdir(exist_ok=True)
    manufacturer_dir = images_path / "test_manufacturer"
    manufacturer_dir.mkdir(parents=True)

    # Copy two different OTA files with different versions (no collision)
    src_ota1 = Path(
        "tests/data/ota_files/fake_100B-010C-01001A02-ConfLight-Lamps_0012.zigbee"
    )
    src_ota2 = Path(
        "tests/data/ota_files/fake_100B-010C-01002500-ConfLight-Lamps_0012.zigbee"
    )

    ota_file1 = manufacturer_dir / "test1.zigbee"
    ota_file2 = manufacturer_dir / "test2.zigbee"
    shutil.copy(src_ota1, ota_file1)
    shutil.copy(src_ota2, ota_file2)

    # Create YAML files
    yaml_content1 = """# OTA metadata for test1.zigbee
file_name: test1.zigbee
source_file_name: test1.zigbee
source_url: https://example.com/test1.zigbee
"""
    yaml_content2 = """# OTA metadata for test2.zigbee
file_name: test2.zigbee
source_file_name: test2.zigbee
source_url: https://example.com/test2.zigbee
"""
    (manufacturer_dir / "test1.zigbee.yaml").write_text(yaml_content1)
    (manufacturer_dir / "test2.zigbee.yaml").write_text(yaml_content2)

    output_file = output_path / "test_zigpy_ota_metadata.json"
    runner = CliRunner()

    # Test without collision - should succeed (default is strict, but no collision here)
    result = runner.invoke(
        cli,
        [
            "generate-index",
            "--images-path",
            str(images_path),
            "--output-file",
            str(output_file),
        ],
    )
    assert result.exit_code == 0, f"Command should succeed: {result.output}"

    # No collision warning message should appear (files have different versions)
    # Check specifically for our warning message, not just the word "collision"
    assert "OTA image collision" not in result.output


class TestComputeStaleImages:
    """Tests for compute_stale_images function."""

    def test_no_stale_when_single_image(self) -> None:
        """Single image cannot be stale."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
        }
        stale = compute_stale_images(metadata)
        assert stale == set()

    def test_no_stale_when_no_constraints_different_versions(self) -> None:
        """Older image without constraints is stale when newer has no constraints."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/v200.zigbee": _make_index_metadata(100, 1, 200),
        }
        stale = compute_stale_images(metadata)
        # v100 is stale: v200 matches all same devices with same specificity
        assert stale == {"mfr/v100.zigbee"}

    def test_stale_when_older_has_model_names_newer_unconstrained(self) -> None:
        """Older image with model_names IS stale when an unconstrained newer exists.

        zigpy sorts upgrade candidates by (file_version, specificity) descending,
        so for a "Model A" device the unconstrained v200 always outranks the
        model-specific v100 — specificity only breaks equal-version ties.
        """
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(
                100, 1, 100, model_names=("Model A",)
            ),
            "mfr/v200.zigbee": _make_index_metadata(100, 1, 200),
        }
        stale = compute_stale_images(metadata)
        assert stale == {"mfr/v100.zigbee"}

    def test_stale_despite_explicit_specificity_boost(self) -> None:
        """An explicit specificity boost cannot save an older image from staleness."""
        metadata = {
            "mfr/v100.zigbee": dataclasses.replace(
                _make_index_metadata(100, 1, 100), specificity=100
            ),
            "mfr/v200.zigbee": _make_index_metadata(100, 1, 200),
        }
        stale = compute_stale_images(metadata)
        assert stale == {"mfr/v100.zigbee"}

    def test_stale_when_newer_has_superset_of_model_names(self) -> None:
        """Older is stale when newer's model_names is superset of older's."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(
                100, 1, 100, model_names=("Model A",)
            ),
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, model_names=("Model A", "Model B")
            ),
        }
        stale = compute_stale_images(metadata)
        # v100 is stale: v200 matches Model A too, same specificity, newer wins
        assert stale == {"mfr/v100.zigbee"}

    def test_not_stale_when_older_has_exclusive_model(self) -> None:
        """Older is NOT stale when it has models newer doesn't have."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(
                100, 1, 100, model_names=("Model A", "Model B")
            ),
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, model_names=("Model A",)
            ),
        }
        stale = compute_stale_images(metadata)
        # v100 is NOT stale: it exclusively matches Model B devices
        assert stale == set()

    def test_not_stale_when_newer_has_model_names_older_doesnt(self) -> None:
        """Older without model_names is NOT stale when newer has model_names."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, model_names=("Model A",)
            ),
        }
        stale = compute_stale_images(metadata)
        # v100 is NOT stale: matches Model B, C, etc. that v200 doesn't
        assert stale == set()

    def test_stale_with_same_model_names(self) -> None:
        """Older is stale when both have identical model_names."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(
                100, 1, 100, model_names=("Model A", "Model B")
            ),
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, model_names=("Model A", "Model B")
            ),
        }
        stale = compute_stale_images(metadata)
        # v100 is stale: same constraints, same specificity, newer wins
        assert stale == {"mfr/v100.zigbee"}

    def test_different_manufacturer_image_type_independent(self) -> None:
        """Different (manufacturer_id, image_type) groups are independent."""
        metadata = {
            # Group 1: manufacturer 100, image type 1
            "mfr/type1_v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/type1_v200.zigbee": _make_index_metadata(100, 1, 200),
            # Group 2: manufacturer 100, image type 2 - only one image
            "mfr/type2_v100.zigbee": _make_index_metadata(100, 2, 100),
        }
        stale = compute_stale_images(metadata)
        # Only v100 in group 1 is stale, type2 has only one image
        assert stale == {"mfr/type1_v100.zigbee"}

    def test_stale_chain(self) -> None:
        """Multiple old images can be stale."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/v200.zigbee": _make_index_metadata(100, 1, 200),
            "mfr/v300.zigbee": _make_index_metadata(100, 1, 300),
        }
        stale = compute_stale_images(metadata)
        # Both v100 and v200 are stale (dominated by v300)
        assert stale == {"mfr/v100.zigbee", "mfr/v200.zigbee"}

    def test_not_stale_with_version_constraints(self) -> None:
        """Older image with version constraint targeting specific devices is NOT stale."""
        metadata = {
            # v200 requires devices at version >= 100
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, min_current_file_version=100
            ),
            # v300 requires devices at version >= 200
            "mfr/v300.zigbee": _make_index_metadata(
                100, 1, 300, min_current_file_version=200
            ),
        }
        stale = compute_stale_images(metadata)
        # v200 is NOT stale: matches devices at version 100-199 that v300 doesn't
        assert stale == set()

    def test_not_stale_when_older_has_no_constraint_newer_does(self) -> None:
        """Older image without constraint is NOT stale when newer has constraint."""
        metadata = {
            # v100 has no version constraint (matches all devices)
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            # v200 requires devices at version >= 50
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, min_current_file_version=50
            ),
        }
        stale = compute_stale_images(metadata)
        # v100 is NOT stale: matches devices at version 0-49 that v200 doesn't
        assert stale == set()

    def test_stale_when_newer_max_covers_older_implicit_ceiling(self) -> None:
        """Older is stale when newer's max constraint still covers older's range.

        v100 is only ever offered to devices below v100 (implicit ceiling of
        file_version - 1), so a newer image accepting versions up to 150
        covers everything v100 covers.
        """
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, max_current_file_version=150
            ),
        }
        stale = compute_stale_images(metadata)
        assert stale == {"mfr/v100.zigbee"}

    def test_implicit_ceiling_boundary(self) -> None:
        """Newer max exactly at older's implicit ceiling dominates; below does not."""
        older = _make_index_metadata(100, 1, 100)
        # v100's effective range is current versions 0-99
        at_ceiling = _make_index_metadata(100, 1, 200, max_current_file_version=99)
        below_ceiling = _make_index_metadata(100, 1, 200, max_current_file_version=98)
        assert is_dominated_by(older, at_ceiling)
        assert not is_dominated_by(older, below_ceiling)

    def test_explicit_max_above_own_version_is_capped(self) -> None:
        """An explicit max above the image's own version doesn't widen its range."""
        # max=500 is meaningless on v100: devices at 100+ never get offered v100
        older = _make_index_metadata(100, 1, 100, max_current_file_version=500)
        newer = _make_index_metadata(100, 1, 200, max_current_file_version=150)
        assert is_dominated_by(older, newer)

    def test_could_match_same_device_unrelated_images(self) -> None:
        """Images with a different manufacturer_id or image_type never overlap.

        A device queries with a single (manufacturer_id, image_type) pair, so
        could_match_same_device() must check it itself rather than rely on
        callers grouping first (same latent bug is_dominated_by() had).
        """
        image = _make_index_metadata(100, 1, 200)
        assert not could_match_same_device(image, _make_index_metadata(200, 1, 200))
        assert not could_match_same_device(image, _make_index_metadata(100, 2, 200))
        # Sanity check: same pair with no constraints does overlap
        assert could_match_same_device(image, _make_index_metadata(100, 1, 300))

    def test_could_match_same_device_implicit_ceiling(self) -> None:
        """Current-version ranges are capped at each image's own version.

        v100 unconstrained only matches devices below v100; a newer image
        requiring version >= 200 targets a disjoint device set.
        """
        older = _make_index_metadata(100, 1, 100)
        newer = _make_index_metadata(100, 1, 300, min_current_file_version=200)
        assert not could_match_same_device(older, newer)
        # min at/below the older's ceiling does overlap
        overlapping = _make_index_metadata(100, 1, 300, min_current_file_version=99)
        assert could_match_same_device(older, overlapping)

    def test_hardware_version_constraints(self) -> None:
        """Hardware-version constraints follow the same superset rules.

        zigpy's check_compatibility rejects hw-constrained images for devices
        that report no hardware version, so a newer image WITH hw constraints
        never covers an older image WITHOUT them.
        """
        older_unconstrained = _make_index_metadata(100, 1, 100)
        older_hw = dataclasses.replace(
            _make_index_metadata(100, 1, 100),
            min_hardware_version=2,
            max_hardware_version=5,
        )
        newer_unconstrained = _make_index_metadata(100, 1, 200)
        newer_same_hw = dataclasses.replace(
            _make_index_metadata(100, 1, 200),
            min_hardware_version=2,
            max_hardware_version=5,
        )
        newer_narrower_hw = dataclasses.replace(
            _make_index_metadata(100, 1, 200),
            min_hardware_version=3,
            max_hardware_version=5,
        )

        # Newer with hw constraints can't dominate an unconstrained older
        assert not is_dominated_by(older_unconstrained, newer_same_hw)
        # Newer without hw constraints covers a hw-constrained older
        assert is_dominated_by(older_hw, newer_unconstrained)
        # Identical hw range dominates; a narrower one does not
        assert is_dominated_by(older_hw, newer_same_hw)
        assert not is_dominated_by(older_hw, newer_narrower_hw)

    def test_disabled_stale_logs_newest_dominator(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Disabled-vs-enabled staleness logs the newest dominating image."""
        metadata = {
            "mfr/disabled_v100.zigbee": dataclasses.replace(
                _make_index_metadata(100, 1, 100), disabled=True
            ),
            "mfr/v200.zigbee": _make_index_metadata(100, 1, 200),
            "mfr/v300.zigbee": _make_index_metadata(100, 1, 300),
        }
        with caplog.at_level(logging.INFO):
            result = prepare_metadata_for_markdown(metadata, Channel.STABLE)

        stale_by_path = {path: is_stale for path, _, is_stale, _ in result}
        assert stale_by_path["mfr/disabled_v100.zigbee"] is True
        # The newest dominator (v300) is reported, not an arbitrary one
        assert (
            "Disabled image mfr/disabled_v100.zigbee (version 0x00000064) is stale: "
            "dominated by mfr/v300.zigbee (version 0x0000012C) for "
            "manufacturer_id=0x0064, image_type=0x0001" in caplog.text
        )

    def test_compute_stale_images_logs_dominator(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """compute_stale_images logs which image dominates a stale one."""
        metadata = {
            "mfr/v100.zigbee": _make_index_metadata(100, 1, 100),
            "mfr/v200.zigbee": _make_index_metadata(100, 1, 200),
        }
        with caplog.at_level(logging.INFO):
            stale = compute_stale_images(metadata)

        assert stale == {"mfr/v100.zigbee"}
        assert (
            "Image mfr/v100.zigbee (version 0x00000064) is stale: dominated by "
            "mfr/v200.zigbee (version 0x000000C8) for manufacturer_id=0x0064, "
            "image_type=0x0001" in caplog.text
        )

    def test_stale_log_hints_at_narrower_names(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A dominated image scoped to device names gets an intent hint."""
        scoped_by_model = {
            "mfr/v100.zigbee": _make_index_metadata(
                100, 1, 100, model_names=("Model A",)
            ),
            "mfr/v200.zigbee": _make_index_metadata(100, 1, 200),
        }
        with caplog.at_level(logging.INFO):
            assert compute_stale_images(scoped_by_model) == {"mfr/v100.zigbee"}
        assert "the newer image needs constraints" in caplog.text

        caplog.clear()

        # No hint when the dominator explicitly covers the same names
        covered = {
            "mfr/v100.zigbee": _make_index_metadata(
                100, 1, 100, model_names=("Model A",)
            ),
            "mfr/v200.zigbee": _make_index_metadata(
                100, 1, 200, model_names=("Model A", "Model B")
            ),
        }
        with caplog.at_level(logging.INFO):
            assert compute_stale_images(covered) == {"mfr/v100.zigbee"}
        assert "needs constraints" not in caplog.text

    def test_not_dominated_by_unrelated_image(self) -> None:
        """An image is never dominated by one with a different manufacturer/type.

        Regression test: is_dominated_by is also called directly (outside the
        grouping in compute_stale_images) for disabled-vs-enabled staleness in
        prepare_metadata_for_markdown, so it must check manufacturer_id and
        image_type itself.
        """
        older = _make_index_metadata(100, 1, 100)
        # Same constraints and a higher file_version, but unrelated images
        assert not is_dominated_by(older, _make_index_metadata(200, 1, 200))
        assert not is_dominated_by(older, _make_index_metadata(100, 2, 200))
        # Sanity check: same (manufacturer_id, image_type) still dominates
        assert is_dominated_by(older, _make_index_metadata(100, 1, 200))
