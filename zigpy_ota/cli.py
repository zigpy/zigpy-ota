"""Command-line interface for zigpy-ota tools.

Provides commands for:
- Generating YAML metadata for OTA images
- Generating zigpy JSON index from images and metadata
- Parsing GitHub issue submissions
- Preparing pull requests for OTA submissions
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from zigpy_ota.actions.issue.issue_parsing import (
    parse_issue_file,
    parse_issue_file_to_model,
)
from zigpy_ota.actions.markdown.markdown_gen import save_metadata_to_markdown_file
from zigpy_ota.actions.metadata.collision_validation import validate_collisions
from zigpy_ota.actions.metadata.disable_images import set_images_disabled
from zigpy_ota.actions.metadata.merging import (
    parse_metadata_complete,
    prepare_metadata_for_markdown,
    prepare_metadata_for_z2m,
    prepare_metadata_for_zigpy,
    save_metadata_to_z2m_file,
    save_metadata_to_zigpy_file,
)
from zigpy_ota.actions.metadata.ota_renaming import rename_ota_files_in_folder
from zigpy_ota.actions.metadata.stale_validation import validate_unreachable_images
from zigpy_ota.actions.metadata.yaml_metadata_deletion import delete_metadata
from zigpy_ota.actions.metadata.yaml_metadata_generation import (
    generate_metadata_for_image,
    generate_stub_metadata_folder,
    normalize_yaml_metadata_folder,
)
from zigpy_ota.actions.pr.markdown_gen import (
    generate_commit_message,
    generate_pr_markdown,
)
from zigpy_ota.actions.pr.prepare_files import prepare_pr
from zigpy_ota.actions.testing.fake_ota_generator import (
    generate_fake_ota_image,
    replace_ota_with_fake,
)
from zigpy_ota.const import (
    DEFAULT_GITHUB_REF,
    IMAGES_PATH,
    MARKDOWN_OTA_METADATA_OUTPUT_PATH,
    METADATA_EXAMPLE_RELEASE_NOTES,
    METADATA_EXAMPLE_URL,
    Z2M_OTA_METADATA_OUTPUT_PATH,
    ZIGPY_OTA_METADATA_OUTPUT_PATH,
)
from zigpy_ota.models.yaml_metadata import Channel, YamlMetadataFile
from zigpy_ota.utils.cli_formatting import setup_logging


@click.group()
def cli() -> None:
    """zigpy-ota command-line tools for managing OTA firmware images."""
    setup_logging()


@cli.command()
@click.argument(
    "image_file",
    type=click.Path(
        exists=True, file_okay=True, dir_okay=False, path_type=type(IMAGES_PATH)
    ),
)
@click.option(
    "--include-examples",
    is_flag=True,
    default=False,
    help="Include example source_url and release_notes in generated YAML file",
)
def generate_stub_metadata(image_file: Path, include_examples: bool) -> None:
    """Generate stub metadata YAML file for a single image file."""
    click.echo(f"Generating stub metadata file for: {image_file}")

    # Create stub metadata, optionally with example values
    # source_file_name is the same as file_name for stub metadata
    stub_metadata = YamlMetadataFile(
        file_name=image_file.name,
        source_file_name=image_file.name,
        source_url=METADATA_EXAMPLE_URL if include_examples else None,
        release_notes=METADATA_EXAMPLE_RELEASE_NOTES if include_examples else None,
    )
    generate_metadata_for_image(image_file, stub_metadata)
    click.echo("Done!")


@cli.command()
@click.option(
    "--images-path",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, path_type=type(IMAGES_PATH)
    ),
    default=IMAGES_PATH,
    help="Path to the images folder",
)
@click.option(
    "--include-examples",
    is_flag=True,
    default=False,
    help="Include example source_url and release_notes in generated YAML files",
)
def generate_stub_metadata_all(images_path: Path, include_examples: bool) -> None:
    """Generate stub metadata YAML files for each image file in the images folder."""
    click.echo(f"Generating stub metadata files in: {images_path}")
    generate_stub_metadata_folder(images_path, include_examples=include_examples)
    click.echo("Done!")


@cli.command()
@click.option(
    "--images-path",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, path_type=type(IMAGES_PATH)
    ),
    default=IMAGES_PATH,
    help="Path to the images folder",
)
@click.option(
    "--output-file",
    type=click.Path(
        file_okay=True, dir_okay=False, path_type=type(ZIGPY_OTA_METADATA_OUTPUT_PATH)
    ),
    default=None,
    help="Path to output JSON file (default depends on format)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["zigpy", "z2m", "markdown"], case_sensitive=False),
    default="zigpy",
    help="Output format: zigpy (default), z2m (Zigbee2MQTT), or markdown (human-readable)",
)
@click.option(
    "--tag",
    type=str,
    default=DEFAULT_GITHUB_REF,
    help=f"Git tag or branch to use in the GitHub raw URL (default: {DEFAULT_GITHUB_REF})",
)
@click.option(
    "--validate-third-party",
    is_flag=True,
    default=False,
    help="Download and validate third-party OTA images from their URLs (slower but ensures URLs work)",
)
@click.option(
    "--allow-missing-yaml/--no-allow-missing-yaml",
    default=False,
    help="Allow OTA images without corresponding YAML metadata (default: fail on missing YAML)",
)
@click.option(
    "--allow-inconsistent-yaml/--no-allow-inconsistent-yaml",
    default=False,
    help="Allow third-party YAML files with corresponding local OTA files (default: fail on inconsistency)",
)
@click.option(
    "--allow-filename-mismatch/--no-allow-filename-mismatch",
    default=False,
    help="Allow YAML files where file_name field doesn't match the filename (default: fail on mismatch)",
)
@click.option(
    "--allow-missing-ota/--no-allow-missing-ota",
    default=False,
    help="Allow YAML metadata files without corresponding OTA binary (default: fail on missing)",
)
@click.option(
    "--allow-invalid-yaml/--no-allow-invalid-yaml",
    default=False,
    help="Allow YAML files that fail to parse or are missing required fields (default: fail on invalid)",
)
@click.option(
    "--allow-collisions/--no-allow-collisions",
    default=False,
    help="Allow OTA image collisions (same manufacturer_id, image_type, "
    "version, and specificity but different content). Default: fail on collisions.",
)
@click.option(
    "--allow-unreachable/--no-allow-unreachable",
    default=False,
    help="Allow images that can never be offered to any device (empty "
    "current-version or hardware-version range). Default: fail on unreachable.",
)
@click.option(
    "--channel",
    type=click.Choice(["stable", "beta", "dev"], case_sensitive=False),
    default="stable",
    help="Release channel: stable (default), beta (includes beta), dev (includes all)",
)
def generate_index(
    images_path: Path,
    output_file: Path | None,
    output_format: str,
    tag: str,
    validate_third_party: bool,
    allow_missing_yaml: bool,
    allow_inconsistent_yaml: bool,
    allow_filename_mismatch: bool,
    allow_missing_ota: bool,
    allow_invalid_yaml: bool,
    allow_collisions: bool,
    allow_unreachable: bool,
    channel: str,
) -> None:
    """Parse OTA images and metadata YAML files to generate OTA index.

    Supports three output formats:

    \b
    - zigpy: JSON index for zigpy/Home Assistant ZHA (default)
    - z2m: JSON index for Zigbee2MQTT
    - markdown: Human-readable markdown index

    To generate multiple formats, run the command multiple times with different --format options.

    For third-party downloads (external hosting), by default the metadata from YAML
    is trusted without downloading the files. Use --validate-third-party to download
    and validate each third-party OTA file.

    Release channels:

    \b
    - stable: Only includes stable images (no channel set in YAML). Default.
    - beta: Includes stable and beta images (channel: beta in YAML).
    - dev: Includes all images (stable, beta, and dev).
    """
    click.echo(f"Generating {output_format} index from images and metadata files...")
    if validate_third_party:
        click.echo(
            "Third-party validation enabled - will download and validate external OTA files"
        )

    fail_on_missing_yaml = not allow_missing_yaml
    fail_on_inconsistent_yaml = not allow_inconsistent_yaml
    fail_on_filename_mismatch = not allow_filename_mismatch
    fail_on_missing_ota = not allow_missing_ota
    fail_on_invalid_yaml = not allow_invalid_yaml

    # Parse all metadata
    merged_metadata = parse_metadata_complete(
        images_path,
        tag,
        validate_third_party,
        fail_on_missing_yaml,
        fail_on_inconsistent_yaml,
        fail_on_filename_mismatch,
        fail_on_missing_ota,
        fail_on_invalid_yaml,
    )

    # Check for images that can never be offered to any device
    validate_unreachable_images(
        merged_metadata, fail_on_unreachable=not allow_unreachable
    )

    # Check for OTA image collisions (same version+specificity, different content)
    fail_on_collision = not allow_collisions
    collisions = validate_collisions(merged_metadata, fail_on_collision)
    # TODO: Remove this click.echo call, since we already warn (or raise)?
    if collisions:
        click.echo(
            f"  Warning: Found {len(collisions)} OTA image collision(s) - "
            "zigpy will ignore these images at runtime"
        )

    # Convert channel string to enum
    channel_enum = Channel(channel)

    # Generate index based on format
    if output_format == "zigpy":
        out_path = output_file or ZIGPY_OTA_METADATA_OUTPUT_PATH
        prepared_zigpy = prepare_metadata_for_zigpy(merged_metadata, channel_enum)
        save_metadata_to_zigpy_file(prepared_zigpy, out_path)
        click.echo(
            f"  {output_format} index: {out_path} ({len(prepared_zigpy)} entries)"
        )
    elif output_format == "z2m":
        out_path = output_file or Z2M_OTA_METADATA_OUTPUT_PATH
        prepared_z2m = prepare_metadata_for_z2m(merged_metadata, channel_enum)
        save_metadata_to_z2m_file(prepared_z2m, out_path)
        click.echo(f"  {output_format} index: {out_path} ({len(prepared_z2m)} entries)")
    else:  # markdown
        out_path = output_file or MARKDOWN_OTA_METADATA_OUTPUT_PATH
        prepared_md = prepare_metadata_for_markdown(merged_metadata, channel_enum)
        save_metadata_to_markdown_file(prepared_md, out_path, channel_enum)
        click.echo(f"  {output_format} index: {out_path} ({len(prepared_md)} entries)")
    click.echo("Done!")


@cli.command()
@click.option(
    "--images-path",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, path_type=type(IMAGES_PATH)
    ),
    default=IMAGES_PATH,
    help="Path to the images folder",
)
def delete_stub_metadata(images_path: Path) -> None:
    """Delete stub metadata YAML files from the images folder."""
    click.echo(f"Deleting stub metadata files in: {images_path}")
    delete_metadata(images_path)
    click.echo("Done!")


@cli.command()
@click.argument(
    "yaml_files",
    nargs=-1,
    required=True,
    type=click.Path(
        exists=True, file_okay=True, dir_okay=False, path_type=type(IMAGES_PATH)
    ),
)
@click.option(
    "--enable",
    is_flag=True,
    default=False,
    help="Remove the `disabled` field (re-enable the images) instead of setting it",
)
def set_image_disabled(yaml_files: tuple[Path, ...], enable: bool) -> None:
    """Set `disabled: true` in OTA metadata YAML files (or remove it with --enable).

    Disabled images are excluded from the generated JSON indexes but stay in the
    repository.
    """
    try:
        changed = set_images_disabled(list(yaml_files), disabled=not enable)
    except ValueError as err:
        raise click.ClickException(str(err)) from err
    for yaml_file in changed:
        click.echo(f"{'Enabled' if enable else 'Disabled'}: {yaml_file}")
    click.echo(f"Changed {len(changed)} of {len(yaml_files)} file(s)")


@cli.command()
@click.argument(
    "issue_file",
    type=click.Path(
        exists=True, file_okay=True, dir_okay=False, path_type=type(IMAGES_PATH)
    ),
)
def parse_issue(issue_file: Path) -> None:
    """Parse a GitHub issue markdown file and display the extracted data."""
    click.echo(f"Parsing issue file: {issue_file}")
    parsed_data = parse_issue_file(issue_file)
    click.echo(json.dumps(parsed_data, indent=2))
    click.echo("Done!")


@cli.command()
@click.argument(
    "output_file",
    type=click.Path(file_okay=True, dir_okay=False, path_type=type(IMAGES_PATH)),
)
@click.option(
    "--manufacturer-id",
    required=True,
    type=str,
    help="Manufacturer ID in hex format (e.g., 0x100B)",
)
@click.option(
    "--image-type",
    required=True,
    type=str,
    help="Image type in hex format (e.g., 0x010C)",
)
@click.option(
    "--file-version",
    required=True,
    type=str,
    help="File version in hex format (e.g., 0x01001A02)",
)
@click.option(
    "--min-hw-version",
    type=str,
    default=None,
    help="Minimum hardware version in hex format (e.g., 0x0001)",
)
@click.option(
    "--max-hw-version",
    type=str,
    default=None,
    help="Maximum hardware version in hex format (e.g., 0x0002)",
)
@click.option(
    "--header-string",
    type=str,
    default=None,
    help="Header string (max 32 characters)",
)
def generate_fake_ota(
    output_file: Path,
    manufacturer_id: str,
    image_type: str,
    file_version: str,
    min_hw_version: str | None,
    max_hw_version: str | None,
    header_string: str | None,
) -> None:
    """Generate a fake OTA image for testing purposes.

    Creates a minimal valid OTA image from scratch that passes zigpy validation.
    The image contains only a valid header and minimal dummy data (64 bytes),
    with no real upgrade firmware. Suitable for testing metadata and validation
    workflows, but NOT for actual device firmware updates.
    """
    click.echo(f"Generating fake OTA image: {output_file}")

    try:
        # Parse hex values
        mfg_id = int(manufacturer_id, 16)
        img_type = int(image_type, 16)
        file_ver = int(file_version, 16)

        min_hw = int(min_hw_version, 16) if min_hw_version else None
        max_hw = int(max_hw_version, 16) if max_hw_version else None

        # Generate the fake OTA image
        generate_fake_ota_image(
            output_path=output_file,
            manufacturer_id=mfg_id,
            image_type=img_type,
            file_version=file_ver,
            min_hardware_version=min_hw,
            max_hardware_version=max_hw,
            header_string=header_string,
        )

        click.echo("Done!")
        click.echo(f"Fake OTA image created at: {output_file}")
        click.echo(f"  Manufacturer ID: 0x{mfg_id:04X}")
        click.echo(f"  Image Type: 0x{img_type:04X}")
        click.echo(f"  File Version: 0x{file_ver:08X}")
        if min_hw is not None:
            click.echo(f"  Min HW Version: 0x{min_hw:04X}")
        if max_hw is not None:
            click.echo(f"  Max HW Version: 0x{max_hw:04X}")
        if header_string is not None:
            click.echo(f"  Header String: {header_string}")

    except ValueError as e:
        click.echo(f"Error: Invalid hex value - {e}", err=True)
        raise click.Abort from e


@cli.command()
@click.argument(
    "ota_files",
    nargs=-1,
    required=True,
    type=click.Path(
        exists=True, file_okay=True, dir_okay=False, path_type=type(IMAGES_PATH)
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be replaced without actually replacing files",
)
def replace_with_fake_ota(ota_files: tuple[Path, ...], dry_run: bool) -> None:
    """Replace real OTA files with fake ones preserving header data.

    Reads header data from existing OTA files and generates minimal fake
    OTA files with the same header values but much smaller size. Useful
    for reducing test file sizes while maintaining valid OTA structure.

    Examples:

        # Replace a single OTA file
        zigpy-ota replace-with-fake-ota tests/data/ota_files/file.zigbee

        # Replace multiple files
        zigpy-ota replace-with-fake-ota tests/data/ota_files/*.zigbee

        # Dry run to see what would change
        zigpy-ota replace-with-fake-ota --dry-run tests/data/ota_files/*.zigbee
    """
    click.echo(f"Processing {len(ota_files)} OTA file(s)...")
    if dry_run:
        click.echo("[DRY RUN MODE - No files will be modified]")
    click.echo("")

    total_original = 0
    total_fake = 0
    results = []

    for ota_file in ota_files:
        try:
            result = replace_ota_with_fake(Path(ota_file), dry_run=dry_run)
            results.append(result)
            # Type narrowing: we know these are ints from the function's return
            total_original += int(result["original_size"])
            total_fake += int(result["fake_size"])
        except Exception as e:
            click.echo(f"Error processing {ota_file}: {e}", err=True)
            raise click.Abort from e

    # Print summary
    click.echo("")
    click.echo("Summary:")
    click.echo(f"  Files processed: {len(results)}")
    click.echo(f"  Total original size: {total_original:,} bytes")

    if not dry_run:
        click.echo(f"  Total fake size: {total_fake:,} bytes")
        total_reduction = total_original - total_fake
        reduction_pct = (
            100 * total_reduction / total_original if total_original > 0 else 0
        )
        click.echo(
            f"  Total size reduction: {total_reduction:,} bytes ({reduction_pct:.1f}%)"
        )
        click.echo("")
        click.echo("✓ All OTA files replaced successfully!")
    else:
        click.echo("")
        click.echo("Use without --dry-run to actually replace files")


@cli.command()
@click.argument(
    "issue_file",
    type=click.Path(
        exists=True, file_okay=True, dir_okay=False, path_type=type(IMAGES_PATH)
    ),
)
@click.option(
    "--output-pr-markdown",
    type=click.Path(file_okay=True, dir_okay=False, path_type=type(IMAGES_PATH)),
    default=None,
    help="Optional path to output a markdown file for creating a GitHub PR",
)
@click.option(
    "--output-commit-message",
    type=click.Path(file_okay=True, dir_okay=False, path_type=type(IMAGES_PATH)),
    default=None,
    help="Optional path to output a commit message file (similar to PR markdown but without formatting)",
)
def prepare_pr_command(
    issue_file: Path,
    output_pr_markdown: Path | None,
    output_commit_message: Path | None,
) -> None:
    """Prepare changes for creating a GitHub PR from an OTA submission issue.

    Downloads the OTA file from the issue, saves it to the images folder,
    and generates metadata YAML. Source URL and notes are extracted from
    the issue file.
    """
    click.echo(f"Preparing PR from issue file: {issue_file}")
    click.echo("")

    try:
        # Parse the issue file to IssueData model
        issue_data = parse_issue_file_to_model(issue_file)

        # Prepare PR changes
        result = prepare_pr(issue_data=issue_data)

        click.echo("Successfully prepared PR changes:")
        click.echo(f"  - OTA file saved to: {result.image_path}")
        click.echo(f"  - Metadata saved to: {result.yaml_path}")
        click.echo(f"  - Filename: {result.filename}")

        # Generate PR markdown if requested
        if output_pr_markdown:
            markdown_content = generate_pr_markdown(result)
            output_path = Path(output_pr_markdown)
            output_path.write_text(markdown_content)
            click.echo(f"  - PR markdown saved to: {output_path}")

        # Generate commit message if requested
        if output_commit_message:
            commit_content = generate_commit_message(result)
            commit_path = Path(output_commit_message)
            commit_path.write_text(commit_content)
            click.echo(f"  - Commit message saved to: {commit_path}")

        click.echo("")
        click.echo("Done! You can now commit these changes and create a PR.")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option(
    "--images-path",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, path_type=type(IMAGES_PATH)
    ),
    default=IMAGES_PATH,
    help="Path to the images folder",
)
def normalize_yaml(images_path: Path) -> None:
    """Re-write all YAML metadata files with normalized formatting.

    Parses all YAML metadata files and re-writes them to ensure consistent
    formatting and field ordering. This is useful for maintaining consistent
    formatting across all metadata files in the repository.

    Examples:

        # Normalize all YAML files in the images folder
        zigpy-ota normalize-yaml

        # Use a different images folder
        zigpy-ota normalize-yaml --images-path ./test-images
    """
    # TODO: Consider using similar logic to generate-zigpy-json?
    click.echo(f"Normalizing YAML metadata files in: {images_path}")
    click.echo("")

    count = normalize_yaml_metadata_folder(images_path)

    click.echo("")
    click.echo(f"Normalized {count} YAML file(s)")
    click.echo("Done!")


@cli.command()
@click.option(
    "--images-path",
    type=click.Path(
        exists=True, file_okay=False, dir_okay=True, path_type=type(IMAGES_PATH)
    ),
    default=IMAGES_PATH,
    help="Path to the images folder",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be renamed without making changes",
)
def rename_ota_files(images_path: Path, dry_run: bool) -> None:
    """Rename OTA files to standardized format.

    Scans the images folder for OTA files and renames them to the standardized
    format: <manufacturer_id>-<image_type>-<file_version>_<hash>.ota

    Also updates the corresponding YAML metadata files with the new filename.

    \b
    Examples:
        # Preview what would be renamed
        zigpy-ota rename-ota-files --dry-run

        # Rename all OTA files in the images folder
        zigpy-ota rename-ota-files

        # Use a different images folder
        zigpy-ota rename-ota-files --images-path ./test-images
    """
    click.echo(f"Scanning for OTA files in: {images_path}")
    if dry_run:
        click.echo("[DRY RUN MODE - No files will be modified]")
    click.echo("")

    # Perform the renaming
    summary = rename_ota_files_in_folder(images_path, dry_run=dry_run)

    # Display results
    for result in summary.results:
        relative_path = result.original_path.relative_to(images_path)

        if result.error:
            click.echo(f"  Skipping ({result.error}): {relative_path}", err=True)
        elif result.skipped:
            pass  # Don't print already correct files
        elif result.new_path:
            new_relative_path = result.new_path.relative_to(images_path)
            click.echo(f"  {relative_path} -> {new_relative_path}")
            if result.yaml_updated and not dry_run:
                click.echo(f"    Updated YAML: {result.new_path.name}.yaml")

    click.echo("")
    click.echo("Summary:")
    click.echo(f"  Renamed: {summary.renamed}")
    click.echo(f"  Already correct: {summary.already_correct}")
    if summary.errors:
        click.echo(f"  Errors: {summary.errors}")

    if dry_run and summary.renamed > 0:
        click.echo("")
        click.echo("Use without --dry-run to actually rename files")

    click.echo("Done!")
