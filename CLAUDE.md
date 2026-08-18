# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

zigpy-ota is a repository and toolset for managing OTA (Over-The-Air) firmware images for Zigbee devices supported by zigpy. It contains:

- A collection of OTA firmware images organized by manufacturer in the `images/` directory
- Metadata files (`.yaml`) describing each firmware image
- CLI tools for managing and processing OTA submissions
- Automated GitHub workflows for handling community OTA submissions

### Ecosystem Position

zigpy-ota is a critical component in the Zigbee firmware update pipeline:

**zigpy-ota** → **zigpy** → **Home Assistant ZHA integration** → **End users**

- **Manufacturers** submit firmware updates via GitHub issue forms
- **Automated PRs** are created for each submission
- Once **approved and merged**, a **GitHub release** must be created to publish the updated `zigpy_v2_ota.json` index
- **zigpy** consumes this index to provide firmware updates
- **Home Assistant's ZHA integration** (using zigpy) makes updates available to end users with Zigbee devices

This means changes merged to this repository directly impact Home Assistant users worldwide. Quality, accuracy, and legal compliance are critical.

**Note for End Users**: End users don't interact with this repository directly. OTA updates are automatically available through Home Assistant's ZHA integration and other zigpy-based applications. The firmware index is published at `https://github.com/zigpy/zigpy-ota/releases` for production use, and the dev channel is available at `https://raw.githubusercontent.com/zigpy/zigpy-ota/release/files/dev/zigpy_v2_ota.json` for testing.

### Contributing to zigpy-ota

There are two main ways to contribute:

**1. Submitting OTA Firmware Images (Recommended)**

Use the GitHub issue form - this is the easiest method:

1. Go to: https://github.com/zigpy/zigpy-ota/issues/new/choose
2. Select one of two options:
   - **"Submit OTA (URL)"** (`.github/ISSUE_TEMPLATE/01-submit-ota-url.yml`) - Provide a download URL to the OTA file
   - **"Submit OTA (File Upload)"** (`.github/ISSUE_TEMPLATE/02-submit-ota-file.yml`) - Upload the OTA file directly (must be zipped first)
3. Fill out the form with:
   - **Title**: Use format `Add Manufacturer Device vX.X.X`
   - **OTA image URL** or **upload zipped OTA file** (depending on which form)
   - **How to handle existing images** (required dropdown):
     - Keep all existing images (without automatic version constraints)
     - Keep existing images and set `min_current_file_version` to highest existing version
   - Manufacturer name (optional, for display purposes)
   - Release notes (optional but recommended)
   - Optional metadata (model names, version constraints, hardware versions, etc.)
   - Third-party download checkbox (for external hosting - URL form only - disabled at the moment)
   - Checklist items (at least confirm the file format)

**Important**: Submit **one issue per OTA image**. Multiple versions should be separate issues. An automated PR will be created from your submission for review by maintainers. If processing fails, the bot comments on the issue - including the specific reason when it is a submission problem (e.g. metadata constraints no device could satisfy).

**2. Manual YAML Metadata Edits**

For updates to existing images (e.g., adding `min_current_file_version` to an existing image):

1. Fork the repository
2. Edit the `.yaml` file in the `images/` directory
3. Submit a pull request with your changes

**General Contributing Guidelines:**

- Use the GitHub issue form for OTA submissions (preferred)
- Follow the existing code style
- Add tests for new functionality
- Ensure all tests pass before submitting (`pytest`)
- Follow pre-commit hooks for code quality
- Verify legal distribution rights for firmware files (see Legal Requirements section)

### Release System

The repository uses a multi-channel release system:

**Release Channels:**

- **stable** - Production releases for end users
- **beta** - Pre-release testing versions
- **dev** - Latest development builds from the `dev` branch

Images are included in channels based on their `channel` YAML field:

- No `channel` field (default): included in stable, beta, and dev
- `channel: beta`: included in beta and dev only
- `channel: dev`: included in dev only

**Index file naming (GitHub release assets only):**

- Stable releases: `zigpy_v2_ota.json`, `z2m_v1_ota.json`, and `markdown_v1.md`
- Beta releases: `zigpy_v2_ota_beta.json`, `z2m_v1_ota_beta.json`, and `markdown_v1_beta.md`

Note: Files on the `release/files` branch use the same names (`zigpy_v2_ota.json`, `z2m_v1_ota.json`, `markdown_v1.md`) in all channel folders.

**How Releases Work:**

1. When a GitHub release is created, the index files are attached as release assets and mirrored to the `release/files` branch
2. The `release/version` branch maintains channel tracking files (`stable.json`, `beta.json`, `dev.json`) that point to the corresponding index URLs:

   ```json
   {
     "schemas": {
       "zigpy_v2": {
         "version": "0.0.15",
         "url": "https://github.com/zigpy/zigpy-ota/releases/download/0.0.15/zigpy_v2_ota.json"
       },
       "z2m_v1": {
         "version": "0.0.15",
         "url": "https://github.com/zigpy/zigpy-ota/releases/download/0.0.15/z2m_v1_ota.json"
       },
       "markdown_v1": {
         "version": "0.0.15",
         "url": "https://github.com/zigpy/zigpy-ota/releases/download/0.0.15/markdown_v1.md"
       }
     }
   }
   ```

   - `version`: The release version identifier (or `"dev"` for development builds)
   - `url`: Direct URL to the OTA metadata for that release (GitHub release asset for stable/beta, `release/files` branch for dev)
   - Schema keys (`zigpy_v2`, `z2m_v1`, `markdown_v1`) allow for future schema evolution while maintaining backward compatibility

**Pulling a Broken Release:**

The version pointers (`stable.json`, `beta.json`) always point to the latest non-draft release whose title is exactly its tag name (the "election" in `.github/scripts/update-version-pointers.sh`). A release containing a broken OTA image can be **pulled** (excluded from the election) in two ways:

1. **"Pull a release" workflow (recommended)**: Run `.github/workflows/pull-release.yml` with the tag to pull. It retitles the release to `<tag> - pulled`, prepends a caution notice to the release body (with the optional reason and a hidden state comment recording the pull date and original commit), re-points the version pointers to the previous good release, and renames the pulled release's index assets (prefixes them with `pulled_`, so clients resolving a stale version pointer fail closed with a 404 while the original assets stay preserved). Unless disabled via the `move_tag` input (on by default), it additionally re-tags the release to `pulled_<tag>` (created at the original commit, so the release keeps pointing at the code it was built from) and force-moves the original tag to the commit of the newest release older than the pulled one (NOT the currently elected release, whose newer tree still contains the pulled files): clients may cache the pulled index (whose binary URLs contain the pulled tag) for up to 24 hours and only download images on install, and moving the tag makes exactly the files added by the pulled release stop resolving while all other links keep working. The weekly `restore-pulled-tags.yml` workflow automatically restores the original tag/commit association once the pull is at least 48 hours old (so up to ~9 days after the pull; the release stays pulled). Note: moving tags requires the pushing identity to have a bypass on any tag protection ruleset.
2. **Manual title edit**: Edit the release title to `<tag> - pulled` in the GitHub web UI. The `edited` release event detects that no pull state is recorded yet and dispatches the pull workflow automatically (with its default inputs, so tags are moved too). Only works for releases tagged after this trigger logic was added.

**Disabling/removing images via PR labels:** Adding `ota-disable`, `ota-enable`, or `ota-remove` to an OTA submission PR (usually a merged one) makes the bot open a PR against the default branch that sets `disabled: true` in that PR's image YAMLs, removes the field again, or deletes the image files entirely (`ota-remove` is for legal/redistribution problems only - the normal policy is keeping disabled images). The bot PR is reviewed and merged by a maintainer; merging updates the dev index automatically. If the images already shipped in a release, additionally pull that release. The trigger label is removed after processing; re-adding it re-runs the action (e.g. to refresh a stale bot PR against the current default branch).

Any other release title fails the election loudly (the workflow errors), so a typo can't silently change which release is elected. To **un-pull** (reinstate) a release, run `.github/workflows/unpull-release.yml` (or simply edit the title back to `<tag>`, which dispatches it): it restores the tag/commit association and asset names, replaces the caution notice with a note recording the pull/re-add dates, restores the title, and re-runs the election.

**Client Access:**

- **Recommended**: Clients fetch version files via stable URLs to discover the index URL dynamically:
  - `https://raw.githubusercontent.com/zigpy/zigpy-ota/release/version/stable.json`
  - `https://raw.githubusercontent.com/zigpy/zigpy-ota/release/version/beta.json`
  - `https://raw.githubusercontent.com/zigpy/zigpy-ota/release/version/dev.json`
- The version file provides the URL to the actual `zigpy_v2_ota.json` index
- This allows programmatic discovery of the latest release for each channel
- Libraries should use this approach rather than hardcoding direct URLs

**The `release/files` Branch:**

- Contains index files organized by channel: `dev/`, `beta/`, `stable/`
- Each channel folder contains `zigpy_v2_ota.json`, `z2m_v1_ota.json`, and `markdown_v1.md`
- The `dev/` folder is automatically updated whenever a new OTA image is merged to the `dev` branch
- The `beta/` and `stable/` folders are updated when corresponding releases are made
- Dev channel accessible at: `https://raw.githubusercontent.com/zigpy/zigpy-ota/release/files/dev/zigpy_v2_ota.json`

**JSON Index Structure:**

The `zigpy_v2_ota.json` is an object containing a `firmwares` array:

```json
{
  "firmwares": [
    {
      "binary_url": "https://raw.githubusercontent.com/zigpy/zigpy-ota/dev/images/manufacturer/firmware.ota",
      "manufacturer_id": 1234,
      "image_type": 789,
      "file_version": 123456,
      "file_size": 12345678,
      "checksum": "sha3-256:dd36540218dc33264acfa82e3433bd2efeeb0318c56970c7a38a3cfc312d0124",
      "release_notes": "- Fixed issues\n- Added new features",
      "min_hardware_version": 5,
      "max_hardware_version": 10
    }
  ]
}
```

**Key fields:**

- `binary_url` - Download URL (GitHub raw for local files, external URL for third-party)
- `manufacturer_id`, `image_type`, `file_version` - Device matching identifiers
- `checksum` - SHA3-256 hash for verification
- `release_url` - Link to release notes, falling back to the PR that added the image

Repo-internal YAML fields (`source_url`, `source_file_name`, `pull_request`, `third_party_download`, `disabled`, ...) are not emitted; third-party hosting is only reflected in where `binary_url` points.

### YAML Metadata Files

There are two types of YAML metadata files in the `images/` directory:

**1. Regular (repo-hosted) OTA files:**

- Contains both `.ota` binary file AND `.ota.yaml` metadata file
- The OTA binary is stored directly in the repository
- OTA files are renamed to a standardized format: `<manufacturer_id>-<image_type>-<file_version>_<hash>.ota` (hash is first 6 chars of SHA3-256). This renaming is done automatically when submitting via the issue form.
- YAML contains basic metadata (checksum/file_size extracted from binary automatically):

  ```yaml
  # OTA metadata
  file_name: 100B-010C-01001A02_abc123.ota
  source_file_name: original_firmware.zigbee
  source_url: https://manufacturer.com/original_firmware.zigbee
  release_notes: |-
    - Bug fixes
    - New features

  # Optional fields (all types of YAML):
  manufacturer_names: [Manufacturer A, Manufacturer B]
  model_names: [Model X, Model Y]
  min_current_file_version: 100
  max_current_file_version: 200
  min_hardware_version: 5
  max_hardware_version: 10
  specificity: 3
  ```

  - `file_name`: The standardized filename in the repository (auto-generated from OTA metadata)
  - `source_file_name`: The original filename from the source (preserved for reference)

- Example: `images/signify/100B-010C-01002602_dd3654.ota` + `.yaml`

**2. Third-party (externally-hosted) OTA files:**

- Contains ONLY `.ota.yaml` metadata file (NO binary in repo)
- The OTA binary is hosted externally and referenced by URL
- YAML must include OTA metadata under `third_party_download` key (since no binary in repo):

  ```yaml
  # OTA metadata
  file_name: 100B-010C-01001A02_abc123.ota
  source_file_name: original_firmware.zigbee
  source_url: https://manufacturer.com/original_firmware.zigbee
  # OTA image metadata required for third-party hosted images:
  third_party_download:
    manufacturer_id: 1234
    image_type: 789
    file_version: 123456
    file_size: 12345678
    checksum_sha3_256: dd36540218dc33264acfa82e3433bd2efeeb0318c56970c7a38a3cfc312d0124
    checksum_sha512: abc123...
  release_notes: |-
    - Bug fixes
    - New features

  # Optional fields (all types of YAML):
  manufacturer_names: [Manufacturer A, Manufacturer B]
  model_names: [Model X, Model Y]
  min_current_file_version: 100
  max_current_file_version: 200
  min_hardware_version: 5
  max_hardware_version: 10
  specificity: 3
  ```

- Example: `images/signify/100B-010C-01002802_dd3654.ota.yaml` (no binary)

**Key differences:**

- Regular YAML: Checksum/file_size/manufacturer_id/image_type/file_version extracted from binary automatically
- Third-party YAML: Must provide all fields under the `third_party_download` key since there's no binary to extract from
- The presence of the `third_party_download` key (as an object with required fields) tells the system to use the external URL instead of looking for a local binary file

**How to create third-party YAML:**

There is **no dedicated CLI command** to generate third-party YAML metadata from an image. Use one of these approaches:

1. **GitHub Issue Form (Recommended)**: Submit via issue form (URL option) and check the "Third-party download" checkbox - this internally uses the `zigpy-ota prepare-pr` command (called by GitHub Actions) which automatically downloads the file, extracts all required metadata, and generates the third-party YAML
2. **Manual Creation**: Download the OTA file temporarily, extract metadata using zigpy, then create the YAML file manually with all required fields under `third_party_download`
3. **Temporary Download**: Download the file, use `zigpy-ota generate-stub-metadata`, then manually restructure the metadata under the `third_party_download` key

**Optional fields (available for both types):**

- `manufacturer_names` - List of manufacturer name strings for device matching
- `model_names` - List of model name strings for device matching
- `min_current_file_version` - Minimum current firmware version for update eligibility
- `max_current_file_version` - Maximum current firmware version for update eligibility
- `min_hardware_version` - Minimum hardware version compatibility
- `max_hardware_version` - Maximum hardware version compatibility
- `specificity` - Breaks ties between matching images with the same file version (higher wins; a newer file version always takes priority)
- `channel` - Release channel (omit for stable which appears in all channels; `beta` appears in beta and dev; `dev` appears only in dev)
- `pull_request` - PR number that added this image (auto-added by GitHub Actions workflow)
- `disabled` - Set to `true` to exclude from JSON indexes while keeping the file in the repo

### Workflow Examples

Real examples of the complete submission workflow can be found in `tests/__snapshots__/test_prepare_pr.ambr`:

**1. Issue Markdown** (generated by GitHub from issue form submission):

- Example: `tests/data/gh_issues/issue_hue_old_replace.md`
- Contains user-submitted data: OTA URL, manufacturer name, release notes, optional metadata
- Format matches the GitHub issue template in `.github/ISSUE_TEMPLATE/01-submit-ota-url.yml`
- Example content:

  ```markdown
  ### OTA image URL

  https://otau.meethue.com/storage/ZGB_100B_010C/.../firmware.zigbee

  ### Manufacturer name

  Hue

  ### How to handle existing images of the same type

  Keep existing images and set `min_current_file_version` to highest existing version

  ### Release notes

  - Bug fixes
  - Performance improvements

  ### Optional metadata

  model_names: [test test, test2]
  manufacturer_names: SignifyX
  min_current_file_version: 0x00010002
  ```

**2. PR Markdown** (generated by `zigpy-ota prepare-pr`):

```markdown
## OTA File Submission

### File Information

- **Filename**: `100B-010C-01001A02_879c1b.ota`
- **Manufacturer Directory**: `signify`
- **Manufacturer ID**: `0x100B` (4107)
- **Image Type**: `0x010C` (268)
- **File Version**: `0x01001A02` (16783874)
- **Hosting**: Repository file (hosted in zigpy-ota)

### Metadata

- **Manufacturer Names**: SignifyX
- **Model Names**: test test, test2
- **Source URL**: https://otau.meethue.com/...

### Release Notes

- Bug fixes
- Performance improvements
```

**3. Generated YAML Metadata** (created automatically):

```yaml
# Regular (repo-hosted)
file_name: 100B-010C-01001A02_879c1b.ota
source_file_name: firmware.zigbee
source_url: https://manufacturer.com/firmware.zigbee
release_notes: |-
  - Bug fixes
  - Performance improvements
manufacturer_names:
  - SignifyX
model_names:
  - test test
  - test2
min_current_file_version: 65538
```

```yaml
# Third-party (externally-hosted)
file_name: 100B-010C-01001A02_879c1b.ota
source_file_name: firmware.zigbee
source_url: https://manufacturer.com/firmware.zigbee
third_party_download:
  manufacturer_id: 4107
  image_type: 268
  file_version: 16783874
  file_size: 126
  checksum_sha3_256: 879c1b0d3f7d89795ca649622c4b4628651559b088dfdf306bc1c5cd8c573e3a
  checksum_sha512: abc123...
release_notes: |-
  - Bug fixes
  - Performance improvements
manufacturer_names:
  - Signify
model_names:
  - Hue Lamp
  - Hue Bulb
```

**4. Final OTA Index Entry** (in `zigpy_v2_ota.json`):

```json
{
  "binary_url": "https://raw.githubusercontent.com/zigpy/zigpy-ota/dev/images/signify/firmware.ota",
  "manufacturer_id": 4107,
  "image_type": 268,
  "file_version": 16783874,
  "file_size": 126,
  "checksum": "sha3-256:879c1b0d3f...",
  "manufacturer_names": ["SignifyX"],
  "model_names": ["test test", "test2"],
  "release_notes": "- Bug fixes\n- Performance improvements",
  "min_current_file_version": 65538
}
```

See `tests/__snapshots__/test_prepare_pr.ambr` for complete workflow examples including file replacement warnings, third-party hosting, and version management scenarios.

## Common Commands

### Development Setup

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

### Testing

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

**Critical Test: `tests/test_prepare_pr.py`**

This test is **critical** because it validates the entire `prepare-pr` workflow - the automated process that converts GitHub issue submissions into PRs. It tests end-to-end:

- Parsing issue markdown
- Downloading OTA files
- Generating YAML metadata
- Creating PR markdown
- Building the OTA index
- Schema validation

The test is **easily expandable** using parametrized fixtures. Currently tests 14 scenarios:

```python
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
        # ... 12 more scenarios
    ],
    indirect=["issue_paths", "ota_paths"],
)
def test_prepare_pr_command_with_snapshot(...):
    # Test runs prepare-pr for each scenario and validates output
```

**Current test coverage includes:**

1. Single image submissions
2. Multiple images (keep existing)
3. Multiple images (replace existing)
4. File re-uploads (same filename)
5. No optional metadata
6. Third-party hosting
7. Regular + third-party mixed
8. Third-party + regular mixed
9. Downgrades (old replacing new)
10. Middle version replacing both ends
11. Auto-set min_current_file_version
12. SET_MIN_VERSION behavior
13. Manual override warnings
14. Hardware version overrides

**To add new test coverage:**

1. Create new issue markdown file(s) in `tests/data/gh_issues/`
2. Add fixture(s) for the new issue file(s) (follow existing pattern)
3. Add new `pytest.param(...)` entry to the parametrize list with descriptive ID
4. Run `pytest --snapshot-update tests/test_prepare_pr.py` to create snapshots
5. Review snapshots in `tests/__snapshots__/test_prepare_pr.ambr` to ensure correctness
6. Commit issue files and snapshots

**Example expansion for a new scenario:**

```python
# Add fixture
@pytest.fixture
def issue_hue_new_scenario() -> Path:
    """Issue file for new scenario description."""
    return Path("tests/data/gh_issues/issue_hue_new_scenario.md")

# Add to parametrize list
pytest.param(
    ["issue_hue_new_scenario"],
    ["ota_hue_old"],
    id="descriptive_test_name",
),
```

This makes it easy to expand coverage for:

- New edge cases discovered in production
- Changes to the issue form template
- New metadata field combinations
- Different manufacturer/device scenarios
- Complex version management cases

**Other Important Tests:**

**`tests/test_ota_index.py`** - Validates the real `images/` directory:

- Tests `generate-index` command against actual repo images
- Ensures all images can be parsed and indexed
- Validates output against zigpy's `REMOTE_PROVIDER_SCHEMA`
- Tests `disabled: true` flag functionality
- Tests `--allow-missing-yaml` flag behavior
- Tests both zigpy and z2m output formats
- **Critical**: This test fails if there are problems with images or YAML in the repo

**`tests/test_parse_issue.py`** - Validates GitHub issue parsing:

- Tests parsing of issue markdown from GitHub issue form submissions
- Uses parametrized fixtures for easy expansion (see `issue_markdown_file` fixture)
- Tests both full and empty submissions
- Validates all issue fields: OTA file, URL, manufacturer, release notes, metadata, checklist
- **Easily expandable**: Add new issue markdown files to `params` list to test new scenarios

**`tests/test_cli.py`** - Tests basic CLI commands:

- `generate-stub-metadata` - Creates YAML from OTA file
- `generate-stub-metadata-all` - Batch YAML generation
- Tests error handling (nonexistent files, etc.)
- Uses snapshot testing for output validation

## CLI Validation Features

The `generate-index` command has several validation flags and output format options:

```bash
zigpy-ota generate-index [OPTIONS]
```

**Output Format Options:**

- `--format` - Output format: `zigpy` (default), `z2m` (Zigbee2MQTT), or `markdown` (human-readable)
  - `zigpy`: Generates JSON index for zigpy/Home Assistant ZHA (`zigpy_v2_ota.json`)
  - `z2m`: Generates JSON index for Zigbee2MQTT (`z2m_v1_ota.json`)
  - `markdown`: Generates human-readable index (`markdown_v1.md`) - see below
  - To generate multiple formats, run the command multiple times with different `--format` options

**Markdown Index Format:**

The `markdown` format generates a human-readable index file (`markdown_v1.md`) useful for:

- Browsing the repository contents without parsing JSON
- Documentation and reference
- Reviewing what firmware images are available

The markdown index includes:

- Channel and total image count (e.g., "42 + 3 disabled")
- Images grouped by manufacturer directory
- For each image: Original File Name, Manufacturer ID, Image Type, File Version, File Size, Binary URL, Checksum, Source URL, Header String, Hardware/File version constraints, Manufacturer/Model Names, Specificity, Release Notes, Pull Request link
- `[disabled]` marker for images with `disabled: true` in YAML
- `[stale]` marker for images that are "dominated" by newer versions

**Stale Image Detection:**

An image is considered "stale" (dominated) when a newer image exists that would match all the same devices. Specifically, image A is dominated by image B when:

- Same manufacturer ID and image type
- B has a higher file version than A
- B's constraints are a superset of A's (or both have no constraints):
  - If A has `model_names`, B must have the same or a superset
  - If A has `manufacturer_names`, B must have the same or a superset
  - If A has version constraints (`min/max_current_file_version`), B must not have constraints that would exclude devices A would match. Since an image is only offered to devices running a version below its own file version, each image's effective maximum is capped at `file_version - 1` — B's `max_current_file_version` only blocks domination if it cuts below A's effective range

This detection helps identify firmware images that are effectively obsolete because a newer version would be preferred for all matching devices.

Note: Disabled images are excluded from zigpy/z2m JSON indexes but included in markdown for visibility. Stale images are included in zigpy JSON (for reference) but excluded from z2m JSON.

**Validation Options:**

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
--allow-unreachable         # Allow images that can never be offered to any device

# Download and validate third-party/remote hosted images (not for CI/CD)
--validate-third-party
```

**Detailed flag descriptions:**

- `--allow-missing-yaml` / `--no-allow-missing-yaml` (default: fail)
  - Controls whether OTA images without corresponding YAML metadata are allowed
  - **Default behavior**: Fails if any `.zigbee` or `.ota` file lacks a `.yaml` file
  - Use `--allow-missing-yaml` to skip files without YAML (useful during development)
  - Use in CI/CD to ensure all images have metadata before release

- `--allow-missing-ota` / `--no-allow-missing-ota` (default: fail)
  - Controls whether YAML files without corresponding OTA binary are allowed
  - **Default behavior**: Fails if a `.yaml` file exists but no matching `.ota` or `.zigbee` file
  - Exception: Third-party YAML files (with `third_party_download` key) don't need local binaries
  - Use `--allow-missing-ota` during development when adding YAML before the binary

- `--allow-inconsistent-yaml` / `--no-allow-inconsistent-yaml` (default: fail)
  - Controls whether third-party YAML files can coexist with local OTA files
  - **Default behavior**: Fails if a `.yaml` has `third_party_download` key but a local `.zigbee` file exists
  - This catches mistakes where someone marks a file as third-party but also committed the binary
  - Use `--allow-inconsistent-yaml` to allow this (generally not recommended)

- `--allow-filename-mismatch` / `--no-allow-filename-mismatch` (default: fail)
  - Controls whether the YAML `file_name` field must match the actual filename
  - **Default behavior**: Fails if `file_name` in YAML doesn't match the `.ota`/`.zigbee` filename
  - Ensures consistency between metadata and actual files
  - Use `--allow-filename-mismatch` during migrations or debugging

- `--allow-invalid-yaml` / `--no-allow-invalid-yaml` (default: fail)
  - Controls whether YAML files that fail to parse are allowed
  - **Default behavior**: Fails if any `.yaml` file has syntax errors or invalid structure
  - Use `--allow-invalid-yaml` to skip problematic files during debugging

- `--allow-collisions` / `--no-allow-collisions` (default: fail)
  - Controls whether duplicate images (same manufacturer ID, image type, and file version) are allowed
  - **Default behavior**: Fails if two images would have identical matching criteria
  - Prevents ambiguous firmware matching where multiple files could apply
  - Use `--allow-collisions` only for debugging duplicate detection

- `--allow-unreachable` / `--no-allow-unreachable` (default: fail)
  - Controls whether images that can never be offered to any device are allowed
  - **Default behavior**: Fails on an empty effective current-version range (e.g. `min_current_file_version` at or above the image's own file version, since an image is only offered below its own version) or an empty hardware-version range (min above max)
  - Disabled images are skipped (they never ship in an index)
  - Validation runs across all channels regardless of `--channel` (like collision validation), so e.g. an unreachable dev-only image also fails a stable publish - intentional strictness
  - Issue-form submissions can't produce unreachable images: `prepare-pr` rejects such constraints up front with an actionable message
  - Use `--allow-unreachable` only for debugging

- `--validate-third-party` (flag, default: off)
  - Downloads and validates third-party OTA images from their URLs
  - **Default behavior**: Trusts the metadata in YAML without downloading
  - **When enabled**: Actually downloads each third-party file and validates:
    - File is accessible at the URL
    - Checksum matches
    - File size matches
    - Manufacturer ID, image type, file version match
  - **Warning**: Much slower as it downloads every external file
  - Useful before releases to ensure all third-party URLs are still valid

**Other Options:**

- `--images-path` - Path to images directory (default: `images/`)
- `--output-file` - Output JSON file path (default depends on format)
- `--tag` - Git tag/branch for GitHub raw URLs (default: from `const.py`)

### Code Quality

```bash
# Run all pre-commit hooks
pre-commit run --all-files

# Type checking (mypy)
pre-commit run mypy --all-files
# or
mypy zigpy_ota

# Linting and formatting (ruff)
ruff check zigpy_ota
ruff format zigpy_ota
```

### CLI Commands

```bash
# Generate metadata for a single OTA image
zigpy-ota generate-stub-metadata path/to/image.ota

# Generate metadata for all images in the images folder
zigpy-ota generate-stub-metadata-all

# Generate index from images
zigpy-ota generate-index --format zigpy     # zigpy JSON (default)
zigpy-ota generate-index --format z2m       # Zigbee2MQTT JSON
zigpy-ota generate-index --format markdown  # Human-readable markdown

# Parse a GitHub issue submission (for testing)
zigpy-ota parse-issue path/to/issue.md

# Prepare PR changes from a GitHub issue
zigpy-ota prepare-pr path/to/issue.md --output-pr-markdown /tmp/pr_body.md

# Generate a fake OTA image for testing
zigpy-ota generate-fake-ota output.ota --manufacturer-id 0x100B --image-type 0x010C --file-version 0x01001A02

# Replace OTA files with fake versions (for reducing test file sizes)
zigpy-ota replace-with-fake-ota tests/data/ota_files/*.zigbee
```

## Architecture

### Core Data Flow

The repository handles two main workflows:

1. **OTA Submission Processing (GitHub Issues → PR)**
   - User submits OTA via GitHub issue form (`.github/ISSUE_TEMPLATE/01-submit-ota-url.yml` or `02-submit-ota-file.yml`)
   - GitHub Actions workflow (`process-ota-submission.yml`) triggers
   - Issue data is parsed (`actions/issue/issue_parsing.py`)
   - OTA file is downloaded (URL form) or extracted from uploaded ZIP (file upload form), validated, and saved to appropriate manufacturer directory
   - Metadata YAML is generated
   - PR is automatically created with the new files

2. **Metadata Index Generation (Images + YAML → JSON)**
   - Scans `images/` directory for `.ota` and `.yaml` file pairs
   - Parses OTA files using zigpy library to extract metadata
   - Merges OTA metadata with YAML metadata
   - Generates final `zigpy_v2_ota.json` index file for zigpy consumption

### Key Modules

**`zigpy_ota/actions/`** - Core business logic organized by action type:

- `pr/` - PR preparation: downloading, extracting, validating OTA files, saving to disk
  - `prepare_files.py` - Main PR preparation logic (called by CLI and GitHub workflow)
  - `download_utils.py` - HTTP downloads, ZIP extraction
  - `pr_utils.py` - Manufacturer detection, file management, duplicate handling
- `issue/` - GitHub issue parsing from markdown format
- `metadata/` - OTA parsing, YAML generation/parsing, metadata merging
  - `ota_parsing.py` - Uses zigpy to parse and validate OTA binary files
  - `yaml_metadata_generation.py` - Creates YAML metadata files
  - `yaml_parsing.py` - Reads and validates YAML metadata
  - `merging.py` - Combines OTA + YAML metadata into final JSON index
  - `stale_validation.py` - Detects stale (dominated) images that are obsoleted by newer versions
- `markdown/` - Markdown generation utilities
  - `markdown_gen.py` - Generates human-readable markdown index of all firmware images
  - `utils.py` - Shared formatting utilities (hex/decimal formatting, list formatting)
- `testing/` - Fake OTA generation for tests

**`zigpy_ota/models/`** - Data models (using dataclasses):

- `issue_model.py` - Represents parsed GitHub issue data (`IssueData`, `OTAFile`, `IssueChecklist`)
- `yaml_metadata.py` - YAML metadata structure (`YamlMetadataFile`, `YamlMetadataThirdParty`)
- `ota_metadata.py` - OTA file metadata extracted from binary
- `index_metadata.py` - Final JSON index format for zigpy
- `pr_result.py` - Result of PR preparation with paths and metadata

**`zigpy_ota/utils/`** - Helper utilities:

- `manufacturers.py` - Manufacturer ID to directory name mapping
- `yaml_utils.py` - YAML serialization helpers
- `cli_formatting.py` - Logging and CLI output formatting

**`zigpy_ota/cli.py`** - Click-based CLI interface exposing all commands

### Important Concepts

**Third-Party Downloads**: OTA files can be hosted externally instead of stored in the repo. The YAML contains checksums and metadata under the `third_party_download` key, and the actual OTA file is downloaded from `source_url` when needed. This is controlled by the "Third-party download" checkbox in issue submissions.

**Existing Images Handling**: When a new OTA is submitted via the GitHub issue form, users must choose how to handle existing images with the same manufacturer ID and image type. This is a **required dropdown** in the issue form with two strategies:

- **Keep with version constraint** (`SET_MIN_VERSION`) - Keep existing images but automatically set `min_current_file_version` on the new image to the highest existing version (that's still older than the new image)
  - Recommended for most cases
  - Useful for multi-step upgrades where devices must upgrade through intermediate versions
  - Prevents downgrades while maintaining upgrade path
  - Example: Device at v1 must upgrade to v2 before upgrading to v3
  - **Important**: Due to how zigpy's firmware matching algorithm works, it's typically sufficient to set `min_current_file_version` on the newer image to require a previous upgrade first. Zigpy automatically prioritizes and prefers more specific images based on the device's current firmware version, so `max_current_file_version` constraints are usually not needed. For the generated Z2M index, `maxFileVersion` is automatically computed from `min_current_file_version` constraints of newer images.
- **Keep all** (`KEEP_ALL`) - Keep all existing images without setting automatic version constraints
  - For manual metadata management
  - Use when you need fine-grained control over version constraints
  - Requires manual editing of YAML metadata files to set constraints

**Note**: The "Replace existing images" option has been disabled. The repository now retains all firmware images for historic purposes and to potentially support combined changelogs across multiple OTA versions in ZHA. Since zigpy always prefers newer firmware versions, older images are only used when they have constraints (like `min_current_file_version` or `model_names`) that make them more specific to certain devices.

**Manufacturer Directories**: OTA files are organized by manufacturer in `images/manufacturer_name/`. Known manufacturers have specific directories (e.g., `aeotec/`, `frient/`), while unknown ones go to `images/other/`.

**Fake OTA Generation**: For testing purposes, minimal valid OTA files can be generated that have correct headers but minimal payload data. This is used to reduce test file sizes while maintaining valid OTA structure.

## Testing Guidelines

- Test data is located in `tests/data/`
- Snapshot testing is used with `syrupy` (snapshots in `tests/__snapshots__/`)
- OTA test files should be minimal fakes (use `zigpy-ota replace-with-fake-ota` to shrink real files)
- Mock external HTTP requests in tests (don't hit real URLs)
- Test both local file and third-party download workflows

## Legal Requirements and Licensing

### Repository License

The zigpy-ota **software code** is licensed under **GPL-3.0** (GNU General Public License v3.0). See the LICENSE file.

**Important**: Binary firmware image files in this repository are **third-party content** from their respective manufacturers and are **NOT covered by the GPL license**. These firmware files remain under their original copyright and licensing terms as set by their manufacturers. Users must comply with applicable manufacturer terms when using these firmware files.

### Firmware Contribution Requirements

Firmware files are copyrighted works. Only contribute files if you have verified legal distribution rights:

- Official manufacturer source with permitted redistribution
- Explicit written permission from copyright holder
- Open source licensed firmware
- You are the copyright holder

Always provide the original source URL in the `source_url` field if known.

## Key Dependencies

- `zigpy` - Zigbee protocol library providing OTA parsing and validation
- `click` - CLI framework
- `ruamel.yaml` - YAML serialization (preserves comments and formatting)
- `requests` - HTTP downloads
- `pytest` - Testing framework
- `ruff` - Linting and formatting
- `mypy` - Type checking
- `uv` - Fast Python package installer (recommended)

## Git Workflow

- Main branch: `dev`
- OTA submission PRs use branch naming: `bot/ota-submission-issue/{issue_number}`
- GitHub Actions bot account (`zigpy-bot`) creates automated PRs
- Pre-commit hooks enforce code quality before commits
