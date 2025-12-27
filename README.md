# zigpy-ota `release/files` Branch

This branch hosts the generated OTA metadata indexes for the zigpy-ota project.

## Purpose

The `release/files` branch contains OTA firmware image indexes for different release channels (stable, beta, and dev).

## Folder Structure

- **dev/** - Development channel, automatically updated whenever a new OTA image is merged
- **beta/** - Beta channel, updated when a new beta release is made
- **stable/** - Stable channel, updated when a new stable release is made

Each folder contains:
- **zigpy_v1_ota.json** - The OTA metadata index for zigpy
- **z2m_v1_ota.json** - The OTA metadata index for Zigbee2MQTT
- **markdown_v1.md** - A human-readable index of all firmware images

## Updates

The `dev/` index files are automatically updated whenever a new OTA image is merged into the repository. The `beta/` and `stable/` index files are updated when corresponding releases are made. All files contain metadata about available firmware images, including download URLs, device compatibility information, and version details.

## Accessing the Index

**Recommended**: Discover the index URL dynamically by fetching the appropriate version file:

```
https://raw.githubusercontent.com/zigpy/zigpy-ota/release/version/stable.json
https://raw.githubusercontent.com/zigpy/zigpy-ota/release/version/beta.json
https://raw.githubusercontent.com/zigpy/zigpy-ota/release/version/dev.json
```

These version files contain the canonical URL for the current release index. Libraries should use this approach to always fetch the latest index URL rather than hardcoding direct URLs.

For more information on the version file structure and usage, refer to the [README.md in the `release/version` branch](https://github.com/zigpy/zigpy-ota/blob/release/version/README.md).

**Alternative (not preferred)**: The index files can also be accessed directly via raw GitHub URLs:

```
https://raw.githubusercontent.com/zigpy/zigpy-ota/release/files/stable/zigpy_v1_ota.json
https://raw.githubusercontent.com/zigpy/zigpy-ota/release/files/beta/zigpy_v1_ota.json
https://raw.githubusercontent.com/zigpy/zigpy-ota/release/files/dev/zigpy_v1_ota.json
```

## Usage

Clients can fetch these indexes to discover available OTA firmware images for Zigbee devices. Choose the appropriate channel based on your needs:
- **stable** - Production-ready firmware images
- **beta** - Pre-release firmware for testing
- **dev** - Latest development images

Currently, the `zigpy_v1`, `z2m_v1`, and `markdown_v1` schemas are available, though additional schema versions may be introduced in the future.

**Note:** Schemas may be replaced or removed at any time as the project evolves. Applications fetching these files should handle the case where their expected schema is no longer present.
