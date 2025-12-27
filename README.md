# zigpy-ota `release/version` Branch

This branch contains version tracking files for the zigpy-ota firmware image repository.

## Purpose

This branch maintains JSON files that track the latest release versions and metadata locations across different release channels. These files allow clients to programmatically discover and fetch the appropriate OTA metadata based on their preferred release channel and schema version.

## Files

- **stable.json** - Points to the latest stable release metadata
- **beta.json** - Points to the latest beta release metadata
- **dev.json** - Points to the latest development release metadata

## Structure

Each JSON file follows this schema:

```json
{
  "schemas": {
    "zigpy_v1": {
      "version": "x.y.z",
      "url": "https://github.com/zigpy/zigpy-ota/releases/download/x.y.z/zigpy_v1_ota.json"
    },
    "z2m_v1": {
      "version": "x.y.z",
      "url": "https://github.com/zigpy/zigpy-ota/releases/download/x.y.z/z2m_v1_ota.json"
    },
    "markdown_v1": {
      "version": "x.y.z",
      "url": "https://github.com/zigpy/zigpy-ota/releases/download/x.y.z/markdown_v1.md"
    }
  }
}
```

- `version`: The release version identifier
- `url`: Direct URL to the OTA metadata JSON for that release
- Schema keys (e.g., `zigpy_v1`) allow for future schema evolution while maintaining backward compatibility

**Note:** Schemas may be replaced or removed at any time as the project evolves. Applications fetching these files should handle the case where their expected schema is no longer present.

## Usage

Clients can fetch these version files to determine the latest available release for their desired channel and schema version, then use the provided URL to retrieve the full OTA metadata.

### Accessing Version Files

The version files can be accessed via stable raw GitHub URLs:

- **Stable**: `https://raw.githubusercontent.com/zigpy/zigpy-ota/release/version/stable.json`
- **Beta**: `https://raw.githubusercontent.com/zigpy/zigpy-ota/release/version/beta.json`
- **Dev**: `https://raw.githubusercontent.com/zigpy/zigpy-ota/release/version/dev.json`

These URLs always point to the latest version information for each release channel.
