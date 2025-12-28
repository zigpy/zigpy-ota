# zigpy-ota

OTA firmware images, metadata, and CLI tools for Zigbee devices, used by [zigpy](https://github.com/zigpy/zigpy)-based applications like Home Assistant's ZHA.

## For End Users

**You don't need to use this repository directly.** OTA updates are automatically available through:

- **Home Assistant ZHA integration** - Updates appear automatically in the UI (requires Home Assistant Core 2026.1.0 or later)
- **zigpy-based applications** - Any application using zigpy can consume these updates

### Browse available firmware

- [Stable channel](https://github.com/zigpy/zigpy-ota/blob/release/files/stable/markdown_v1.md)
- [Beta channel](https://github.com/zigpy/zigpy-ota/blob/release/files/beta/markdown_v1.md)
- [Dev channel](https://github.com/zigpy/zigpy-ota/blob/release/files/dev/markdown_v1.md)

**Note**: Firmware marked as `[disabled]` or `[stale]` is not installable. It's retained for historic and changelog purposes only.

### Using pre-release channels

<details><summary>Click to expand</summary>

By default, only stable firmware is available, which is highly recommended for most users.\
To opt into pre-release firmware, add this to your Home Assistant configuration:

```yaml
zha:
  zigpy_config:
    ota:
      extra_providers:
        - type: zigpy_ota
          channel: beta # or 'dev' for bleeding edge (unstable, not recommended)
          override_previous: true
```

</details>

## For Contributors

### Submitting OTA Firmware Images

**Use the GitHub issue form to submit OTA images** - this is the recommended and easiest method:

1. Go to: https://github.com/zigpy/zigpy-ota/issues/new/choose
2. Select one of two options:
   - **"Submit OTA (URL)"** - Provide a download URL to the OTA file
   - **"Submit OTA (File Upload)"** - Upload the OTA file directly (must be zipped first)
3. Fill out the form with:
   - **Title**: Use format `Add Manufacturer Device vX.X.X`
   - **OTA image URL** or **upload zipped OTA file** (depending on which form)
   - **How to handle existing images** (required dropdown):
     - Keep all existing images
     - Keep existing images and set `min_current_file_version` to highest existing version
   - Manufacturer name (optional, for display purposes)
   - Release notes (optional but recommended)
   - Optional metadata (model names, version constraints, hardware versions, etc.)
   - Checklist items (at least confirm the file format)

**Important**: Submit **one issue per OTA image**. Multiple versions should be separate issues.

**What happens next:**

- For trusted submitters, an automated PR is created immediately
- For other submitters, a maintainer will review your issue and add the `ota-create` label to trigger PR creation

If you need to make changes to your submission, edit the original issue and ask a maintainer to add the `ota-resubmit` label to update the PR.

**Tip**: You can also submit older firmware versions (e.g., factory-installed firmware) so that ZHA displays "up-to-date" instead of "unknown" for devices already running the latest available firmware.

### Manual YAML Metadata Edits

For updates to existing images (e.g., adding `min_current_file_version` or `model_names` to an existing image), you can submit a PR directly:

1. Fork the repository
2. Edit the `.yaml` file in the `images/` directory
3. Submit a pull request with your changes

See the [YAML Metadata Format](#yaml-metadata-format) section below.

### Removing or Reverting Firmware Updates

To disable or revert an existing firmware update, submit a PR using one of these methods:

1. **Disable the image** (preferred) - Add `disabled: true` to the YAML metadata file to exclude it from the index without deleting the files.
2. **Revert the commit** - If the firmware was recently added, create a PR that reverts the commit which added the update
3. **Manual deletion** - Delete both the OTA file (`.zigbee` or `.ota`) and its corresponding YAML metadata file (`.yaml`) from the `images/` directory, then submit a PR with those changes

For options 2 and 3, both the OTA binary and YAML metadata file must be removed together to fully remove a firmware update from the index.
Use deletion only if the firmware bricks devices.

**Note**: The repository generally retains all firmware images for historic purposes.
Zigpy always prefers newer firmware versions, so older images are only used when they have constraints (like `min_current_file_version` or `model_names`) that make them more specific to certain devices.
You can check the [firmware index](#browse-available-firmware) to see if an image is marked as `[stale]` or `[disabled]`. These are not installed by zigpy/ZHA.

## Release Process

1. OTA images are submitted via GitHub issues
2. Automated PRs are created and reviewed
3. Once merged to `dev`, the `dev/` folder on the [`release/files`](https://github.com/zigpy/zigpy-ota/tree/release/files) branch is automatically updated with the latest index files
4. Images are immediately available for testing from the dev channel
5. For stable/beta releases, maintainers create a GitHub release. Index files are attached as [release assets](https://github.com/zigpy/zigpy-ota/releases) and mirrored to the corresponding folder on the [`release/files`](https://github.com/zigpy/zigpy-ota/tree/release/files) branch
6. zigpy and Home Assistant automatically consume the index from the appropriate channel

## Release Channels

- **stable** - Production releases for end users
- **beta** - Pre-release testing versions
- **dev** - Latest development builds from the `dev` branch

Images are included in channels based on their `channel` YAML field:

- No `channel` field (default): included in stable, beta, and dev
- `channel: beta`: included in beta and dev only
- `channel: dev`: included in dev only

**Index file naming (GitHub release assets):**

- Stable releases: `zigpy_v1_ota.json`, `z2m_v1_ota.json`, and `markdown_v1.md`
- Beta releases: `zigpy_v1_ota_beta.json`, `z2m_v1_ota_beta.json`, and `markdown_v1_beta.md`

### Accessing the index files programmatically

**Recommended**: Discover the URL dynamically via version files on the [`release/version`](https://github.com/zigpy/zigpy-ota/tree/release/version) branch:\
`https://raw.githubusercontent.com/zigpy/zigpy-ota/release/version/{stable,beta,dev}.json`

Index files are also mirrored to the [`release/files`](https://github.com/zigpy/zigpy-ota/tree/release/files) branch organized by channel (`stable/`, `beta/`, `dev/`), where all folders use the same filenames (`zigpy_v1_ota.json`, `z2m_v1_ota.json`, `markdown_v1.md`).

After an image is merged to the `dev` branch, the updated index is immediately available for testing at:\
`https://raw.githubusercontent.com/zigpy/zigpy-ota/release/files/dev/zigpy_v1_ota.json`

**Direct access** for all channels (not preferred):\
`https://raw.githubusercontent.com/zigpy/zigpy-ota/release/files/{stable,beta,dev}/zigpy_v1_ota.json`

<!-- Consider moving the Z2M configuration to the "For End-Users" section at some point --->

**Example**: To use the stable Zigbee2MQTT index, add this to your Z2M configuration:

```yaml
ota:
  zigbee_ota_override_index_location: https://raw.githubusercontent.com/zigpy/zigpy-ota/release/files/stable/z2m_v1_ota.json
```

## YAML Metadata Format

The YAML metadata file must have the same name as the OTA file with `.yaml` appended.\
(e.g., `firmware_name.ota` → `firmware_name.ota.yaml`).

OTA files are automatically renamed to a standardized format based on their metadata: `<manufacturer_id>-<image_type>-<file_version>_<hash>.ota` (hash is first 6 chars of SHA3-256). The original filename is preserved in the `source_file_name` field.\
This renaming is done automatically when submitting a new OTA image via the issue form. In the future, CLI tools will also be added to rename files locally.

<!-- Third-party section not enabled yet. It's also disabled in issue forms.
There are two types of YAML metadata files:

### Regular (Repo-Hosted) Images
--->

For images stored in this repository:

```yaml
# OTA metadata
file_name: 100B-010C-01001A02_abc123.ota
source_file_name: original_firmware.zigbee
source_url: https://manufacturer.com/original_firmware.zigbee

# Optional fields:
release_notes: |-
  - Bug fixes
  - New features
manufacturer_names: [Manufacturer A, Manufacturer B]
model_names: [Model X, Model Y]
min_current_file_version: 100
max_current_file_version: 200
min_hardware_version: 5
max_hardware_version: 10
specificity: 3
channel: beta
```

- `file_name`: The standardized filename in the repository (auto-generated from OTA metadata)
- `source_file_name`: The original filename from the source (preserved for reference)

<!-- Third-party section not enabled yet. It's also disabled in issue forms.
### Third-Party (Externally-Hosted) Images

For images hosted externally (not stored in repo):

```yaml
# OTA metadata
file_name: firmware.ota
source_url: https://manufacturer.com/firmware.ota
# OTA image metadata required for third-party hosted images:
third_party_download:
  manufacturer_id: 1234
  image_type: 789
  file_version: 123456
  file_size: 12345678
  checksum_sha3_256: abc123...
  checksum_sha512: def456...

# Optional fields are the same as regular images (see above)
```

**Key differences:**

- Regular YAML: Checksum/file_size/manufacturer_id extracted from binary automatically
- Third-party YAML: Must provide all fields under the `third_party_download` key (no binary in repo to extract from)

**How to create third-party YAML:**

There is no dedicated CLI command to generate third-party YAML at the moment. Use one of these methods:

1. **Recommended**: Use the GitHub issue form (URL submission) and check the "Third-party download" checkbox - metadata will be generated automatically (this internally uses `zigpy-ota prepare-pr` with the GitHub issue form markdown)
2. **Manual**: Create the YAML file manually with all required fields listed above
-->

### Optional Metadata Fields

- `manufacturer_names` - List of manufacturer name strings for device matching
- `model_names` - List of model name strings for device matching
- `min_current_file_version` - Minimum current firmware version for update eligibility
- `max_current_file_version` - Maximum current firmware version for update eligibility
- `min_hardware_version` - Minimum hardware version compatibility
- `max_hardware_version` - Maximum hardware version compatibility
- `specificity` - Priority level when multiple images match (higher = more specific)
- `channel` - Release channel (omit for stable which appears in all channels; `beta` appears in beta and dev; `dev` appears only in dev)

**Note on multi-step upgrades:** Due to how zigpy's firmware matching algorithm works, it's typically sufficient to set `min_current_file_version` on the newer image to require a previous upgrade first.

Zigpy automatically prioritizes and prefers more specific images based on the device's current firmware version, so `max_current_file_version` constraints are usually not needed.\
For the [generated Z2M index](https://raw.githubusercontent.com/zigpy/zigpy-ota/release/files/stable/z2m_v1_ota.json), `maxFileVersion` is automatically computed from `min_current_file_version` constraints of newer images.

## For Developers

<details><summary>Click to expand</summary>

### Installation

```bash
# Clone the repository
git clone https://github.com/zigpy/zigpy-ota.git
cd zigpy-ota

# Run setup script (creates venv, installs dependencies, sets up pre-commit)
script/setup

# Activate the virtual environment
source .venv/bin/activate

# Or manually:
# uv sync
# pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Update snapshots after intentional changes
pytest --snapshot-update

# Run specific test file
pytest tests/test_prepare_pr.py

# Run with coverage
pytest --cov=zigpy_ota --cov-report=html
```

### Code Quality

```bash
# Run all pre-commit hooks
pre-commit run --all-files

# Type checking
mypy zigpy_ota

# Linting and formatting
ruff check zigpy_ota
ruff format zigpy_ota
```

### CLI Commands

```bash
# Generate index from images
zigpy-ota generate-index --format zigpy     # zigpy JSON (default)
zigpy-ota generate-index --format z2m       # Zigbee2MQTT JSON
zigpy-ota generate-index --format markdown  # Human-readable markdown

# Parse a GitHub issue submission
zigpy-ota parse-issue issue.md

# Prepare PR from issue (download OTA, create YAML, generate PR markdown)
zigpy-ota prepare-pr issue.md --output-pr-markdown pr.md

# Generate stub YAML metadata for an OTA file
zigpy-ota generate-stub-metadata firmware.ota

# Rename OTA files to standardized format (updates YAML too)
zigpy-ota rename-ota-files --dry-run  # preview
zigpy-ota rename-ota-files            # apply

# Generate fake OTA image for testing
zigpy-ota generate-fake-ota output.ota --manufacturer-id 0x100B --image-type 0x010C --file-version 0x00000001

# Replace real OTA files with fake ones (for tests)
zigpy-ota replace-with-fake-ota tests/data/ota_files/*.ota
```

### Validation Options

The `generate-index` command has validation flags (all default to strict/fail):

```bash
# Strict validation (recommended for CI/CD)
zigpy-ota generate-index

# Development mode flags:
--allow-missing-yaml        # Allow OTA images without corresponding YAML metadata
--allow-missing-ota         # Allow YAML files without corresponding OTA binary
--allow-inconsistent-yaml   # Allow third-party YAML with local OTA files present
--allow-filename-mismatch   # Allow YAML file_name field not matching filename
--allow-invalid-yaml        # Allow YAML files that fail to parse
--allow-collisions          # Allow duplicate images (same ID/type/version)

# Download and validate third-party/remote hosted images (not for CI/CD)
--validate-third-party
```

See [CLAUDE.md](CLAUDE.md) for detailed developer documentation.

</details>

## License

The zigpy-ota **software code** is licensed under GPL-3.0 (GNU General Public License v3.0). See [LICENSE](LICENSE) file.

**Important**: Binary firmware image files in this repository are **third-party content** from their respective manufacturers and are **NOT covered by the GPL license**. These firmware files remain under their original copyright and licensing terms as set by their manufacturers. Users must comply with applicable manufacturer terms when using these firmware files.

## Questions

For questions or discussions, see [GitHub Discussions](https://github.com/zigpy/zigpy-ota/discussions).
