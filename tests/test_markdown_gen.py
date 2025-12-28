"""Tests for PR markdown generation."""

from __future__ import annotations

from pathlib import Path

import pytest

from zigpy_ota.actions.pr.markdown_gen import (
    generate_commit_message,
    generate_pr_markdown,
)
from zigpy_ota.models.index_metadata import IndexMetadata
from zigpy_ota.models.issue_model import ExistingImagesHandling, IssueChecklist
from zigpy_ota.models.ota_metadata import OtaMetadata
from zigpy_ota.models.pr_result import PrepareResult
from zigpy_ota.models.yaml_metadata import YamlMetadataFile

# Default checklist for tests (all items unchecked except supported_format)
DEFAULT_CHECKLIST = IssueChecklist(
    supported_format=True,
    filled_release_notes=False,
    tested_on_device=False,
    is_official_source=False,
)


@pytest.fixture
def ota_metadata() -> OtaMetadata:
    """Create a sample OtaMetadata for testing."""
    return OtaMetadata(
        manufacturer_id=0x100B,
        image_type=0x010C,
        file_version=0x01001A02,
        file_size=12345,
        checksum_sha3_256="abc123" * 10,
        checksum_sha512="def456" * 20,
        min_hardware_version=5,
        max_hardware_version=10,
    )


@pytest.fixture
def yaml_metadata() -> YamlMetadataFile:
    """Create a sample YamlMetadataFile for testing."""
    return YamlMetadataFile(
        file_name="test_firmware.zigbee",
        source_file_name="original_firmware.zigbee",
        source_url="https://example.com/firmware.zigbee",
        manufacturer_names=("Test Manufacturer",),
        model_names=("Model A", "Model B"),
        release_notes="- Bug fixes\n- Performance improvements",
    )


@pytest.fixture
def yaml_metadata_with_hw_override() -> YamlMetadataFile:
    """Create YamlMetadataFile with hardware version overrides."""
    return YamlMetadataFile(
        file_name="test_firmware.zigbee",
        source_file_name="original_firmware.zigbee",
        source_url="https://example.com/firmware.zigbee",
        min_hardware_version=1,  # Different from OTA's 5
        max_hardware_version=20,  # Different from OTA's 10
    )


@pytest.fixture
def deletable_image() -> IndexMetadata:
    """Create a sample IndexMetadata for deletable images."""
    return IndexMetadata(
        binary_url="https://example.com/old_firmware.zigbee",
        manufacturer_id=0x100B,
        image_type=0x010C,
        file_version=0x01001A01,  # Older version
        file_size=11111,
        checksum_sha3_256="old123" * 10,
        checksum_sha512="old456" * 20,
        source_file_name="old_firmware.zigbee",
    )


@pytest.fixture
def prepare_result_basic(
    ota_metadata: OtaMetadata, yaml_metadata: YamlMetadataFile
) -> PrepareResult:
    """Create a basic PrepareResult without warnings."""
    return PrepareResult(
        image_path=Path("/tmp/test_firmware.zigbee"),
        yaml_path=Path("/tmp/test_firmware.zigbee.yaml"),
        filename="test_firmware.zigbee",
        manufacturer_name="Test Corp",
        manufacturer_directory="test",
        deletable_images={},
        existing_images_handling=ExistingImagesHandling.KEEP_ALL,
        auto_min_version=None,
        file_existed=False,
        replaced_third_party=False,
        checklist=DEFAULT_CHECKLIST,
        ota_metadata=ota_metadata,
        yaml_metadata=yaml_metadata,
    )


@pytest.fixture
def prepare_result_with_file_existed(
    ota_metadata: OtaMetadata, yaml_metadata: YamlMetadataFile
) -> PrepareResult:
    """Create a PrepareResult where file already existed."""
    return PrepareResult(
        image_path=Path("/tmp/test_firmware.zigbee"),
        yaml_path=Path("/tmp/test_firmware.zigbee.yaml"),
        filename="test_firmware.zigbee",
        manufacturer_name=None,
        manufacturer_directory="test",
        deletable_images={},
        existing_images_handling=ExistingImagesHandling.KEEP_ALL,
        auto_min_version=None,
        file_existed=True,
        replaced_third_party=False,
        checklist=DEFAULT_CHECKLIST,
        ota_metadata=ota_metadata,
        yaml_metadata=yaml_metadata,
    )


@pytest.fixture
def prepare_result_with_hw_override(
    ota_metadata: OtaMetadata, yaml_metadata_with_hw_override: YamlMetadataFile
) -> PrepareResult:
    """Create a PrepareResult with hardware version overrides."""
    return PrepareResult(
        image_path=Path("/tmp/test_firmware.zigbee"),
        yaml_path=Path("/tmp/test_firmware.zigbee.yaml"),
        filename="test_firmware.zigbee",
        manufacturer_name=None,
        manufacturer_directory="test",
        deletable_images={},
        existing_images_handling=ExistingImagesHandling.KEEP_ALL,
        auto_min_version=None,
        file_existed=False,
        replaced_third_party=False,
        checklist=DEFAULT_CHECKLIST,
        ota_metadata=ota_metadata,
        yaml_metadata=yaml_metadata_with_hw_override,
    )


@pytest.fixture
def prepare_result_with_deletable_images(
    ota_metadata: OtaMetadata,
    yaml_metadata: YamlMetadataFile,
    deletable_image: IndexMetadata,
) -> PrepareResult:
    """Create a PrepareResult with deletable images (REPLACE mode - actually deleted)."""
    return PrepareResult(
        image_path=Path("/tmp/test_firmware.zigbee"),
        yaml_path=Path("/tmp/test_firmware.zigbee.yaml"),
        filename="test_firmware.zigbee",
        manufacturer_name=None,
        manufacturer_directory="test",
        deletable_images={"old_firmware.zigbee": deletable_image},
        existing_images_handling=ExistingImagesHandling.REPLACE,
        auto_min_version=None,
        file_existed=False,
        replaced_third_party=False,
        checklist=DEFAULT_CHECKLIST,
        ota_metadata=ota_metadata,
        yaml_metadata=yaml_metadata,
    )


@pytest.fixture
def prepare_result_with_auto_min_version(
    ota_metadata: OtaMetadata,
    deletable_image: IndexMetadata,
) -> PrepareResult:
    """Create a PrepareResult with auto min version."""
    yaml_with_min = YamlMetadataFile(
        file_name="test_firmware.zigbee",
        source_file_name="original_firmware.zigbee",
        source_url="https://example.com/firmware.zigbee",
        min_current_file_version=0x01001A01,  # Same as auto_min_version
    )
    return PrepareResult(
        image_path=Path("/tmp/test_firmware.zigbee"),
        yaml_path=Path("/tmp/test_firmware.zigbee.yaml"),
        filename="test_firmware.zigbee",
        manufacturer_name=None,
        manufacturer_directory="test",
        deletable_images={"old_firmware.zigbee": deletable_image},
        existing_images_handling=ExistingImagesHandling.SET_MIN_VERSION,
        auto_min_version=0x01001A01,
        file_existed=False,
        replaced_third_party=False,
        checklist=DEFAULT_CHECKLIST,
        ota_metadata=ota_metadata,
        yaml_metadata=yaml_with_min,
    )


class TestGeneratePrMarkdown:
    """Tests for generate_pr_markdown function."""

    def test_basic_output_contains_file_info(
        self, prepare_result_basic: PrepareResult
    ) -> None:
        """Test that basic file information is always included."""
        markdown = generate_pr_markdown(prepare_result_basic)

        assert "## OTA File Submission" in markdown
        assert "### File Information" in markdown
        assert "test_firmware.zigbee" in markdown
        assert "Test Corp" in markdown
        assert "0x100B" in markdown  # manufacturer_id
        assert "0x010C" in markdown  # image_type

    def test_file_replacement_shown(
        self, prepare_result_with_file_existed: PrepareResult
    ) -> None:
        """Test that file replacement warning is shown."""
        markdown = generate_pr_markdown(prepare_result_with_file_existed)

        assert "### ⚠️ File Replacement Warning" in markdown
        assert "overwrite" in markdown.lower()

    def test_hw_override_shown(
        self, prepare_result_with_hw_override: PrepareResult
    ) -> None:
        """Test that hardware version override warning is shown."""
        markdown = generate_pr_markdown(prepare_result_with_hw_override)

        assert "### ⚠️ Hardware Version Override Warning" in markdown
        assert "Min Hardware Version" in markdown
        assert "Max Hardware Version" in markdown

    def test_deleted_images_shown(
        self, prepare_result_with_deletable_images: PrepareResult
    ) -> None:
        """Test that deleted images section is shown."""
        markdown = generate_pr_markdown(prepare_result_with_deletable_images)

        assert "### Deleted Images" in markdown
        assert "old_firmware.zigbee" in markdown

    def test_auto_min_version_shown(
        self, prepare_result_with_auto_min_version: PrepareResult
    ) -> None:
        """Test that auto min version note is shown."""
        markdown = generate_pr_markdown(prepare_result_with_auto_min_version)

        assert "min_current_file_version" in markdown
        assert "automatically set" in markdown

    def test_metadata_included(self, prepare_result_basic: PrepareResult) -> None:
        """Test that metadata sections are included."""
        markdown = generate_pr_markdown(prepare_result_basic)

        assert "### Metadata" in markdown
        assert "Test Manufacturer" in markdown
        assert "Model A" in markdown
        assert "### Release Notes" in markdown
        assert "Bug fixes" in markdown


class TestGenerateCommitMessage:
    """Tests for generate_commit_message function."""

    def test_strips_header_prefixes(self, prepare_result_basic: PrepareResult) -> None:
        """Test that markdown header prefixes are stripped."""
        commit_msg = generate_commit_message(prepare_result_basic)

        # Should not have ## or ### prefixes
        assert "## " not in commit_msg
        assert "### " not in commit_msg
        # But should still have section names
        assert "OTA File Submission" in commit_msg
        assert "File Information" in commit_msg

    def test_strips_bold_markers(self, prepare_result_basic: PrepareResult) -> None:
        """Test that **bold** markers are stripped."""
        commit_msg = generate_commit_message(prepare_result_basic)

        # Should not have ** markers
        assert "**" not in commit_msg
        # But should still have the text that was bold
        assert "Filename" in commit_msg
        assert "Manufacturer ID" in commit_msg

    def test_strips_backticks(self, prepare_result_basic: PrepareResult) -> None:
        """Test that `backticks` are stripped."""
        commit_msg = generate_commit_message(prepare_result_basic)

        # Should not have backticks
        assert "`" not in commit_msg
        # But should still have the text that was in backticks
        assert "test_firmware.zigbee" in commit_msg
        assert "0x100B" in commit_msg

    def test_includes_hw_override_warnings(
        self, prepare_result_with_hw_override: PrepareResult
    ) -> None:
        """Test that hardware override warnings are included in commit message."""
        commit_msg = generate_commit_message(prepare_result_with_hw_override)

        assert "Hardware Version Override Warning" in commit_msg

    def test_includes_metadata(self, prepare_result_basic: PrepareResult) -> None:
        """Test that metadata is included in commit message."""
        commit_msg = generate_commit_message(prepare_result_basic)

        assert "Test Manufacturer" in commit_msg
        assert "Model A" in commit_msg
        assert "Release Notes" in commit_msg

    def test_includes_deleted_images(
        self, prepare_result_with_deletable_images: PrepareResult
    ) -> None:
        """Test that deleted images are included in commit message."""
        commit_msg = generate_commit_message(prepare_result_with_deletable_images)

        assert "Deleted Images" in commit_msg
        assert "old_firmware.zigbee" in commit_msg

    def test_includes_file_replacement(
        self, prepare_result_with_file_existed: PrepareResult
    ) -> None:
        """Test that file replacement info is included in commit message."""
        commit_msg = generate_commit_message(prepare_result_with_file_existed)

        assert "File Replacement Warning" in commit_msg
        assert "overwrite" in commit_msg.lower()
