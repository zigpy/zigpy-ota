#!/usr/bin/env bash
set -euo pipefail

# Script to update version pointer files (stable.json, beta.json) in the release/version branch
# and copy index files (JSON, markdown) to stable/ and beta/ directories in the release/files branch.
# Determines which channels need updates based on the event type and release status.
#
# Required environment variables:
#   GH_TOKEN            - GitHub token for gh CLI
#   GITHUB_EVENT_NAME   - GitHub event name (release, workflow_dispatch)
#
# Required for release events and workflow_dispatch with tag:
#   RELEASE_TAG_NAME    - Release tag name
#   RELEASE_PRERELEASE  - Whether the release is a prerelease (true/false)
#
# Optional environment variables:
#   RELEASE_CREATED_AT  - Release creation timestamp (only for release events)
#   EVENT_ACTION        - GitHub event action (empty for workflow_dispatch)
#   RELEASE_ASSETS      - JSON array of release assets (only for release events)

# JSON asset filenames (stable channel)
ZIGPY_JSON_FILENAME="zigpy_v1_ota.json"
Z2M_JSON_FILENAME="z2m_v1_ota.json"
MARKDOWN_FILENAME="markdown_v1.md"
# JSON asset filenames (beta channel - includes stable + beta images)
ZIGPY_JSON_BETA_FILENAME="zigpy_v1_ota_beta.json"
Z2M_JSON_BETA_FILENAME="z2m_v1_ota_beta.json"
MARKDOWN_BETA_FILENAME="markdown_v1_beta.md"

# ------------------------------------------------------------------------------
# Functions
# ------------------------------------------------------------------------------

# Checkout a branch, fetching from remote or creating if needed
checkout_branch() {
  local branch=$1
  if git ls-remote --exit-code --heads origin "$branch" > /dev/null 2>&1; then
    echo "Branch $branch exists, fetching..."
    git fetch origin "$branch:$branch"
    git checkout "$branch"
  else
    echo "Branch $branch does not exist, creating..."
    git checkout -b "$branch"
  fi
}

# Check if a release has the JSON asset
# Only checks for zigpy JSON since both files are always uploaded together
check_json_asset() {
  local tag=$1
  if gh release view "$tag" --json assets --jq '.assets[].name' | grep -q "$ZIGPY_JSON_FILENAME"; then
    return 0  # Has JSON asset
  else
    return 1  # No JSON asset
  fi
}

# Update or create a JSON version pointer file
update_json() {
  local file=$1
  local tag=$2
  echo "Updating $file to point to $tag"

  # Use beta filenames for beta.json, stable filenames for stable.json
  local zigpy_filename="$ZIGPY_JSON_FILENAME"
  local z2m_filename="$Z2M_JSON_FILENAME"
  local markdown_filename="$MARKDOWN_FILENAME"
  if [ "$file" = "beta.json" ]; then
    zigpy_filename="$ZIGPY_JSON_BETA_FILENAME"
    z2m_filename="$Z2M_JSON_BETA_FILENAME"
    markdown_filename="$MARKDOWN_BETA_FILENAME"
  fi

  local zigpy_url="https://github.com/zigpy/zigpy-ota/releases/download/$tag/$zigpy_filename"
  local z2m_url="https://github.com/zigpy/zigpy-ota/releases/download/$tag/$z2m_filename"
  local markdown_url="https://github.com/zigpy/zigpy-ota/releases/download/$tag/$markdown_filename"

  if [ -f "$file" ]; then
    # Update existing file
    jq --arg version "$tag" \
       --arg zigpy_url "$zigpy_url" \
       --arg z2m_url "$z2m_url" \
       --arg markdown_url "$markdown_url" \
       '.schemas.zigpy_v1.version = $version | .schemas.zigpy_v1.url = $zigpy_url | .schemas.z2m_v1.version = $version | .schemas.z2m_v1.url = $z2m_url | .schemas.markdown_v1.version = $version | .schemas.markdown_v1.url = $markdown_url' \
       "$file" > /tmp/"$(basename "$file")"
    mv /tmp/"$(basename "$file")" "$file"
  else
    # Create new file if it doesn't exist
    echo "Creating $file (did not exist)"
    jq -n --arg version "$tag" \
       --arg zigpy_url "$zigpy_url" \
       --arg z2m_url "$z2m_url" \
       --arg markdown_url "$markdown_url" \
       '{schemas: {zigpy_v1: {version: $version, url: $zigpy_url}, z2m_v1: {version: $version, url: $z2m_url}, markdown_v1: {version: $version, url: $markdown_url}}}' \
       > "$file"
  fi
}

# ------------------------------------------------------------------------------
# Determine which version pointers need to be updated
# ------------------------------------------------------------------------------

# For release events, log when the release was created
if [ "$GITHUB_EVENT_NAME" = "release" ]; then
  CREATED_AT="${RELEASE_CREATED_AT}"
  CREATED_AT_UNIX=$(date -u -d "$CREATED_AT" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$CREATED_AT" +%s)
  NOW=$(date -u +%s)
  AGE=$((NOW - CREATED_AT_UNIX))
  echo "::notice::Release was created $AGE seconds ago (created at $CREATED_AT)"
fi

echo "::group::Determine version pointers to update"

# Get all releases and sort by version
LATEST_STABLE_RELEASE=$(gh release list --exclude-drafts --exclude-pre-releases --json tagName --jq '.[].tagName' | sort -V | tail -n1)
LATEST_ANY_RELEASE=$(gh release list --exclude-drafts --json tagName --jq '.[].tagName' | sort -V | tail -n1)

# Initialize update flags
UPDATE_STABLE=false
UPDATE_BETA=false
STABLE_TAG=""
BETA_TAG=""

# Handle different event types:
# - workflow_dispatch without tag: manual trigger, recalculate from latest releases
# - workflow_dispatch with tag: re-triggered from 'released' event, use provided tag
# - release events: use provided tag from event payload
if [ "$GITHUB_EVENT_NAME" = "workflow_dispatch" ] && [ -z "${RELEASE_TAG_NAME:-}" ]; then
  # Manual trigger without tag: recalculate and update to latest releases
  echo "Event: workflow_dispatch (manual trigger, no tag provided)"
  echo "Latest stable: $LATEST_STABLE_RELEASE"
  echo "Latest any/beta: $LATEST_ANY_RELEASE"

  # Check beta release
  if [ -n "$LATEST_ANY_RELEASE" ]; then
    if check_json_asset "$LATEST_ANY_RELEASE"; then
      echo "JSON asset: $ZIGPY_JSON_FILENAME exists in release $LATEST_ANY_RELEASE"
      UPDATE_BETA=true
      BETA_TAG="$LATEST_ANY_RELEASE"
      echo "Will update beta.json to $LATEST_ANY_RELEASE"
    else
      echo "::warning::JSON asset not found in latest beta release $LATEST_ANY_RELEASE - skipping beta.json update"
    fi
  fi

  # Check stable release
  if [ -n "$LATEST_STABLE_RELEASE" ]; then
    if check_json_asset "$LATEST_STABLE_RELEASE"; then
      echo "JSON asset: $ZIGPY_JSON_FILENAME exists in release $LATEST_STABLE_RELEASE"
      UPDATE_STABLE=true
      STABLE_TAG="$LATEST_STABLE_RELEASE"
      echo "Will update stable.json to $LATEST_STABLE_RELEASE"
    else
      echo "::warning::JSON asset not found in latest stable release $LATEST_STABLE_RELEASE - skipping stable.json update"
    fi
  fi

  if [ "$UPDATE_STABLE" = false ] && [ "$UPDATE_BETA" = false ]; then
    echo "::error::No releases with JSON assets found. Nothing to update."
    echo "::endgroup::"
    exit 1
  fi
else
  # Release event OR workflow_dispatch with tag (re-triggered from 'released' event)
  CURRENT_TAG="${RELEASE_TAG_NAME}"
  IS_PRERELEASE="${RELEASE_PRERELEASE}"
  ACTION="${EVENT_ACTION:-}"

  if [ "$GITHUB_EVENT_NAME" = "workflow_dispatch" ]; then
    echo "Event: workflow_dispatch (with tag $CURRENT_TAG)"
  else
    echo "Event: $ACTION"
  fi
  echo "Current release: $CURRENT_TAG (prerelease=$IS_PRERELEASE)"
  echo "Latest stable: $LATEST_STABLE_RELEASE"
  echo "Latest any/beta: $LATEST_ANY_RELEASE"

  # Check if JSON asset exists in current release (from event payload or by querying)
  # For 'published' events, the asset may not be in the payload yet since it's uploaded in the same workflow
  # For workflow_dispatch, we need to query the release directly
  HAS_JSON=false
  if [ "$GITHUB_EVENT_NAME" = "workflow_dispatch" ]; then
    # Query release directly for workflow_dispatch
    if check_json_asset "$CURRENT_TAG"; then
      echo "JSON asset: $ZIGPY_JSON_FILENAME exists in release $CURRENT_TAG"
      HAS_JSON=true
    else
      echo "JSON asset: $ZIGPY_JSON_FILENAME NOT found in release $CURRENT_TAG"
    fi
  elif [ -n "${RELEASE_ASSETS:-}" ] && echo "$RELEASE_ASSETS" | jq -e --arg name "$ZIGPY_JSON_FILENAME" '.[] | select(.name == $name)' > /dev/null 2>&1; then
    # Release event with asset in payload
    echo "JSON asset: $ZIGPY_JSON_FILENAME exists in release payload for $CURRENT_TAG"
    HAS_JSON=true
  else
    # Release event without asset in payload (e.g., 'published' event before upload completes)
    echo "JSON asset: $ZIGPY_JSON_FILENAME NOT found in release payload for $CURRENT_TAG"
  fi

  # Update beta.json if this is the latest release (including pre-releases)
  if [ "$CURRENT_TAG" = "$LATEST_ANY_RELEASE" ]; then
    UPDATE_BETA=true
    BETA_TAG="$CURRENT_TAG"
    echo "Will update beta.json to $CURRENT_TAG (this is the latest beta)"
  fi

  # Update stable.json if this is NOT a pre-release AND is the latest stable release
  if [ "$IS_PRERELEASE" != "true" ] && [ "$CURRENT_TAG" = "$LATEST_STABLE_RELEASE" ]; then
    UPDATE_STABLE=true
    STABLE_TAG="$CURRENT_TAG"
    echo "Will update stable.json to $CURRENT_TAG (this is the latest stable)"
  fi

  # Exit early if nothing to update
  if [ "$UPDATE_STABLE" = false ] && [ "$UPDATE_BETA" = false ]; then
    echo "::notice::This is not the latest release. Skipping version pointer updates."
    echo "::endgroup::"
    exit 0
  fi

  # Verify JSON asset exists before proceeding
  # For 'published' events, JSON was generated and uploaded earlier in the workflow
  # but isn't present in the event's release assets payload
  if [ "$HAS_JSON" != true ] && [ "$ACTION" != "published" ]; then
    echo "::notice::JSON asset not found in release $CURRENT_TAG - skipping version pointer update"
    echo "::endgroup::"
    exit 0
  fi
fi

echo "::endgroup::"

# ------------------------------------------------------------------------------
# Update version pointer files in release/version branch
# ------------------------------------------------------------------------------

echo "::group::Update version pointer files"

checkout_branch "release/version"

# Update beta.json
if [ "$UPDATE_BETA" = true ]; then
  update_json "beta.json" "$BETA_TAG"
  git add beta.json
  git diff --staged --quiet || git commit -m "Update \`beta\` version to $BETA_TAG"
  echo "::notice::Successfully updated beta.json (to $BETA_TAG)"
fi

# Update stable.json
if [ "$UPDATE_STABLE" = true ]; then
  update_json "stable.json" "$STABLE_TAG"
  git add stable.json
  git diff --staged --quiet || git commit -m "Update \`stable\` version to $STABLE_TAG"
  echo "::notice::Successfully updated stable.json (to $STABLE_TAG)"
fi

# Push changes
git push origin release/version

echo "::endgroup::"

# ------------------------------------------------------------------------------
# Copy index files to release/files branch, for direct download by OTA clients
# ------------------------------------------------------------------------------

echo "::group::Copy index files to release/files branch"

checkout_branch "release/files"

# Download and commit beta index files
if [ "$UPDATE_BETA" = true ]; then
  echo "Downloading index files from release $BETA_TAG for beta channel..."
  mkdir -p beta
  # Download beta channel files and rename to standard names
  gh release download "$BETA_TAG" --pattern "$ZIGPY_JSON_BETA_FILENAME" --dir beta --clobber
  gh release download "$BETA_TAG" --pattern "$Z2M_JSON_BETA_FILENAME" --dir beta --clobber
  gh release download "$BETA_TAG" --pattern "$MARKDOWN_BETA_FILENAME" --dir beta --clobber
  mv "beta/$ZIGPY_JSON_BETA_FILENAME" "beta/$ZIGPY_JSON_FILENAME"
  mv "beta/$Z2M_JSON_BETA_FILENAME" "beta/$Z2M_JSON_FILENAME"
  mv "beta/$MARKDOWN_BETA_FILENAME" "beta/$MARKDOWN_FILENAME"
  git add beta/
  git diff --staged --quiet || git commit -m "Update \`beta\` OTA index files"
  echo "::notice::Successfully updated beta/ (from $BETA_TAG)"
fi

# Download and commit stable index files
if [ "$UPDATE_STABLE" = true ]; then
  echo "Downloading index files from release $STABLE_TAG for stable channel..."
  mkdir -p stable
  gh release download "$STABLE_TAG" --pattern "$ZIGPY_JSON_FILENAME" --dir stable --clobber
  gh release download "$STABLE_TAG" --pattern "$Z2M_JSON_FILENAME" --dir stable --clobber
  gh release download "$STABLE_TAG" --pattern "$MARKDOWN_FILENAME" --dir stable --clobber
  git add stable/
  git diff --staged --quiet || git commit -m "Update \`stable\` OTA index files"
  echo "::notice::Successfully updated stable/ (from $STABLE_TAG)"
fi

# Push changes
git push origin release/files

echo "::endgroup::"
