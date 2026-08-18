#!/usr/bin/env bash
set -euo pipefail

# Script to update version pointer files (stable.json, beta.json) in the release/version branch
# and copy index files (JSON, markdown) to stable/ and beta/ directories in the release/files branch.
#
# The desired state is recalculated from scratch on every run ("election", see below), so the
# script is idempotent: publishing a release, editing a release title, or a manual dispatch all
# converge on the same result. Event payloads are only used for logging.
#
# Required environment variables:
#   GH_TOKEN            - GitHub token for gh CLI
#
# Optional environment variables:
#   GH_REPO             - Repository in OWNER/REPO format for gh CLI context
#   GITHUB_EVENT_NAME   - GitHub event name (release, workflow_dispatch; for logging only)
#   RELEASE_CREATED_AT  - Release creation timestamp (only for release events; for logging only)
#   GITHUB_OUTPUT       - If set, the election results are appended as step outputs
#                         (stable_tag, beta_tag, update_stable, update_beta) for
#                         observability and potential downstream consumers

# Remember the original checkout so we can restore it at the end (this script switches
# to the release/version and release/files branches; later workflow steps should see
# the tree they started with). Restore on EVERY exit path: the release/* branches are
# orphans without .github/, so a failure exit mid-checkout would otherwise strand the
# workspace and break later steps that must still run (e.g. pull-release.sh finalize).
ORIGINAL_HEAD=$(git rev-parse HEAD)
# Restore on every exit path, escalating only as far as needed: a plain
# checkout first (preserves unrelated local changes, e.g. a dirty local
# invocation), then aborting a possibly in-flight rebase from push_branch's
# retry, and --force only as a last resort for a genuinely wedged tree (the
# script's own staged-but-uncommitted pointer edits are recomputed on re-run).
# A failed restore must not mask the script's exit code (warning returns 0).
restore_original_checkout() {
  git checkout --quiet "$ORIGINAL_HEAD" 2>/dev/null && return 0
  git rebase --abort >/dev/null 2>&1 || true
  git checkout --quiet "$ORIGINAL_HEAD" 2>/dev/null && return 0
  if git checkout --force --quiet "$ORIGINAL_HEAD" 2>/dev/null; then
    echo "::warning::Restoring the original checkout required --force - uncommitted changes were discarded"
  else
    echo "::warning::Could not restore the original checkout ($ORIGINAL_HEAD)"
  fi
}
trap restore_original_checkout EXIT

# Read schema config from .github/SCHEMA.json (must be done before any branch switches)
ZIGPY_JSON_FILENAME=$(jq -r '.zigpy_filename' .github/SCHEMA.json)
Z2M_JSON_FILENAME=$(jq -r '.z2m_filename' .github/SCHEMA.json)
MARKDOWN_FILENAME=$(jq -r '.markdown_filename' .github/SCHEMA.json)

ZIGPY_JSON_BETA_FILENAME=$(jq -r '.zigpy_beta_filename' .github/SCHEMA.json)
Z2M_JSON_BETA_FILENAME=$(jq -r '.z2m_beta_filename' .github/SCHEMA.json)
MARKDOWN_BETA_FILENAME=$(jq -r '.markdown_beta_filename' .github/SCHEMA.json)

ZIGPY_SCHEMA_KEY=$(jq -r '.zigpy_schema_key' .github/SCHEMA.json)
Z2M_SCHEMA_KEY=$(jq -r '.z2m_schema_key' .github/SCHEMA.json)
MARKDOWN_SCHEMA_KEY=$(jq -r '.markdown_schema_key' .github/SCHEMA.json)

# ------------------------------------------------------------------------------
# Functions
# ------------------------------------------------------------------------------

# Push a branch, retrying once after a rebase if another workflow pushed to it
# concurrently (e.g. update-dev-json.yml commits to release/files from a different
# concurrency group)
push_branch() {
  git push origin "$1" || {
    git pull --rebase origin "$1"
    git push origin "$1"
  }
}

# Checkout a branch, fetching it from the remote. The release/* branches must
# already exist: they are created once per repository as orphan branches, never
# derived from the code tree
# (e.g. git switch --orphan release/files && git commit --allow-empty -m "Init")
checkout_branch() {
  local branch=$1
  if ! git ls-remote --exit-code --heads origin "$branch" > /dev/null 2>&1; then
    echo "::error::Branch $branch not found (or the remote could not be reached). It must be created manually, once, as an orphan branch."
    exit 1
  fi
  git fetch origin "$branch:$branch"
  git checkout "$branch"
}

# Check if a release has all of the given assets ($1 = tag, $2.. = filenames).
# All per-channel assets are checked (the election can pick any historical release,
# e.g. one whose asset upload failed midway), so a version pointer never references
# a missing asset and the release/files downloads below can't fail.
# Note: uses a here-string instead of a pipeline to avoid SIGPIPE/pipefail
# interaction where grep -q exits early and kills the producer
check_release_assets() {
  local tag=$1
  shift
  local assets fname
  assets=$(gh release view "$tag" --json assets --jq '.assets[].name') || return 1
  for fname in "$@"; do
    grep -qx -- "$fname" <<<"$assets" || return 1
  done
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
       --arg zigpy_key "$ZIGPY_SCHEMA_KEY" \
       --arg z2m_key "$Z2M_SCHEMA_KEY" \
       --arg md_key "$MARKDOWN_SCHEMA_KEY" \
       '.schemas[$zigpy_key].version = $version | .schemas[$zigpy_key].url = $zigpy_url | .schemas[$z2m_key].version = $version | .schemas[$z2m_key].url = $z2m_url | .schemas[$md_key].version = $version | .schemas[$md_key].url = $markdown_url' \
       "$file" > /tmp/"$(basename "$file")"
    mv /tmp/"$(basename "$file")" "$file"
  else
    # Create new file if it doesn't exist
    echo "Creating $file (did not exist)"
    jq -n --arg version "$tag" \
       --arg zigpy_url "$zigpy_url" \
       --arg z2m_url "$z2m_url" \
       --arg markdown_url "$markdown_url" \
       --arg zigpy_key "$ZIGPY_SCHEMA_KEY" \
       --arg z2m_key "$Z2M_SCHEMA_KEY" \
       --arg md_key "$MARKDOWN_SCHEMA_KEY" \
       '{schemas: {($zigpy_key): {version: $version, url: $zigpy_url}, ($z2m_key): {version: $version, url: $z2m_url}, ($md_key): {version: $version, url: $markdown_url}}}' \
       > "$file"
  fi
}

# ------------------------------------------------------------------------------
# Determine which version pointers need to be updated
# ------------------------------------------------------------------------------

# For release events, log when the release was created
if [ "${GITHUB_EVENT_NAME:-}" = "release" ] && [ -n "${RELEASE_CREATED_AT:-}" ]; then
  CREATED_AT="${RELEASE_CREATED_AT}"
  CREATED_AT_UNIX=$(date -u -d "$CREATED_AT" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$CREATED_AT" +%s)
  NOW=$(date -u +%s)
  AGE=$((NOW - CREATED_AT_UNIX))
  echo "::notice::Release was created $AGE seconds ago (created at $CREATED_AT)"
fi

echo "::group::Determine version pointers to update"

# Elect the latest stable and beta releases. A release participates in the election
# only if its title is the tag name itself (or empty). Releases can be excluded from
# the election ("pulled", e.g. because they contain a broken OTA image) by editing
# the release title to "<tag> - pulled" (optionally followed by a reason). Releases
# whose tag starts with "pulled_" (a pulled release temporarily re-tagged by
# pull-release.sh so it keeps pointing at its original commit) are also excluded,
# regardless of title: an already-restored title on a still-re-tagged release is a
# normal transient state while an un-pull is pending. Any other title is a hard
# error, so a typo can't silently change the election.
RELEASES_JSON=$(gh release list --exclude-drafts --limit 200 --json tagName,name,isPrerelease)

INVALID_TITLES=$(jq -r '
  .[] | (.name // "") as $name
  | ((.tagName | ascii_downcase) + " - pulled") as $pulled_prefix
  | ($name | ascii_downcase | startswith($pulled_prefix)) as $has_pulled_title
  | select(
      (.tagName | startswith("pulled_") | not)
      and ($name != "" and $name != .tagName and ($has_pulled_title | not))
    )
  | "\(.tagName): \"\($name)\""' <<<"$RELEASES_JSON")
if [ -n "$INVALID_TITLES" ]; then
  echo "::error::Release title(s) must be either \"<tag>\" or \"<tag> - pulled ...\". Fix the following release title(s) and re-run this workflow: $INVALID_TITLES"
  echo "::endgroup::"
  exit 1
fi

PULLED_RELEASES=$(jq -r '
  .[] | (.name // "") as $name
  | (if (.tagName | startswith("pulled_")) then (.tagName | ltrimstr("pulled_")) else .tagName end) as $base_tag
  | (($base_tag | ascii_downcase) + " - pulled") as $pulled_prefix
  | select(
      (.tagName | startswith("pulled_"))
      or ($name | ascii_downcase | startswith($pulled_prefix))
    )
  | .tagName' <<<"$RELEASES_JSON")
if [ -n "$PULLED_RELEASES" ]; then
  # shellcheck disable=SC2086 # word splitting is intentional for display
  echo "::notice::Excluding pulled release(s) from the election:" $PULLED_RELEASES
fi

LATEST_STABLE_RELEASE=$(jq -r '
  .[] | select(
    (.tagName | startswith("pulled_") | not)
    and ((.name // "") == "" or .name == .tagName)
    and (.isPrerelease | not)
  ) | .tagName' <<<"$RELEASES_JSON" | sort -V | tail -n1)
LATEST_ANY_RELEASE=$(jq -r '
  .[] | select(
    (.tagName | startswith("pulled_") | not)
    and ((.name // "") == "" or .name == .tagName)
  ) | .tagName' <<<"$RELEASES_JSON" | sort -V | tail -n1)

echo "Latest stable: $LATEST_STABLE_RELEASE"
echo "Latest any/beta: $LATEST_ANY_RELEASE"

# Initialize update flags
UPDATE_STABLE=false
UPDATE_BETA=false
STABLE_TAG=""
BETA_TAG=""

# Check beta release
if [ -n "$LATEST_ANY_RELEASE" ]; then
  if check_release_assets "$LATEST_ANY_RELEASE" "$ZIGPY_JSON_BETA_FILENAME" "$Z2M_JSON_BETA_FILENAME" "$MARKDOWN_BETA_FILENAME"; then
    echo "All beta index assets exist in release $LATEST_ANY_RELEASE"
    UPDATE_BETA=true
    BETA_TAG="$LATEST_ANY_RELEASE"
    echo "Will update beta.json to $LATEST_ANY_RELEASE"
  else
    echo "::warning::Missing beta index asset(s) in latest beta release $LATEST_ANY_RELEASE - skipping beta.json update (regenerate them by running this workflow with tag_name=$LATEST_ANY_RELEASE)"
  fi
fi

# Check stable release
if [ -n "$LATEST_STABLE_RELEASE" ]; then
  if check_release_assets "$LATEST_STABLE_RELEASE" "$ZIGPY_JSON_FILENAME" "$Z2M_JSON_FILENAME" "$MARKDOWN_FILENAME"; then
    echo "All stable index assets exist in release $LATEST_STABLE_RELEASE"
    UPDATE_STABLE=true
    STABLE_TAG="$LATEST_STABLE_RELEASE"
    echo "Will update stable.json to $LATEST_STABLE_RELEASE"
  else
    echo "::warning::Missing stable index asset(s) in latest stable release $LATEST_STABLE_RELEASE - skipping stable.json update (regenerate them by running this workflow with tag_name=$LATEST_STABLE_RELEASE)"
  fi
fi

if [ "$UPDATE_STABLE" = false ] && [ "$UPDATE_BETA" = false ]; then
  echo "::error::No releases with JSON assets found. Nothing to update."
  echo "::endgroup::"
  exit 1
fi

# Expose the election results as step outputs (observability / potential consumers)
if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    echo "stable_tag=$STABLE_TAG"
    echo "beta_tag=$BETA_TAG"
    echo "update_stable=$UPDATE_STABLE"
    echo "update_beta=$UPDATE_BETA"
  } >> "$GITHUB_OUTPUT"
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
push_branch release/version

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
  git diff --staged --quiet || git commit -m "Update \`beta\` OTA index files to $BETA_TAG"
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
  git diff --staged --quiet || git commit -m "Update \`stable\` OTA index files to $STABLE_TAG"
  echo "::notice::Successfully updated stable/ (from $STABLE_TAG)"
fi

# Push changes
push_branch release/files

echo "::endgroup::"

# (The EXIT trap restores the original checkout, on success and failure alike)
