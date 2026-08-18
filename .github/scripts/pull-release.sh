#!/usr/bin/env bash
set -euo pipefail

# Script to pull (and un-pull) a broken release. Used by pull-release.yml,
# unpull-release.yml, and restore-pulled-tags.yml. Takes one subcommand argument:
#
#   mark          - Validate the release and retitle it to "<tag> - pulled", which
#                   excludes it from the version pointer election in update-version-pointers.sh.
#                   Also prepends a caution notice to the release body, including a hidden
#                   state comment recording when the release was pulled, the reason, and the
#                   original tag commit (consumed by 'unpull' and 'restore-tags').
#
#   finalize      - Rename the pulled release's index assets (prefix them with "pulled_"), so
#                   any client still resolving a stale version pointer fails closed with a 404
#                   instead of downloading the pulled index. Renaming (instead of replacing)
#                   preserves the original assets, including their upload date and download
#                   count, and is trivially reversible.
#                   With MOVE_TAG, additionally re-tag the GitHub release to "pulled_<tag>"
#                   (created at the original commit, so the release keeps pointing at the code
#                   it was actually built from) and force-move the original tag to the commit
#                   of the newest release older than the pulled one. This makes binary URLs
#                   baked into still-cached indexes stop resolving for exactly the files the
#                   pulled release added, while all other files keep working (image file names
#                   are unique per version, so files added by the pulled release don't exist
#                   at older commits - but they do still exist at newer commits, since pulled
#                   images are only disabled in the index, never deleted).
#
#   unpull        - Reinstate a pulled release: restore the original tag/commit association
#                   (undoing MOVE_TAG if needed, including deleting the "pulled_<tag>" tag),
#                   rename the "pulled_*" index assets back to their original names, replace
#                   the caution notice in the release body with a note recording the
#                   pull/re-add dates (repeated cycles stack one note each), and restore the
#                   release title to "<tag>" (which re-includes the release in the version
#                   pointer election).
#
#   sync-pull-state - Dispatch pull-release.yml / unpull-release.yml for releases whose
#                   title disagrees with their recorded pull state (self-healing for
#                   lost `edited`-event dispatches; see cmd_sync_pull_state).
#
#   restore-tags  - For releases that remain pulled but had their tag moved: restore the
#                   original tag to its original commit (for reference purposes), re-tag the
#                   release back from "pulled_<tag>" to "<tag>", and delete the "pulled_<tag>"
#                   tag - once the pull is old enough that OTA clients can no longer hold a
#                   cached index referencing the tag (RESTORE_DELAY_HOURS; zigpy caches
#                   indexes for up to 24 hours). Run periodically by restore-pulled-tags.yml.
#                   The releases stay pulled (title, body notice, and renamed assets remain).
#
# Required environment variables:
#   GH_TOKEN               - GitHub token for gh CLI (release edits/assets; tag pushes use
#                            the credentials of the checkout)
#   PULL_TAG               - Tag of the release to pull/un-pull (not used by
#                            'restore-tags' and 'sync-pull-state')
#
# Required for 'finalize' (tag move only):
#   ORIGINAL_COMMIT        - The release's original tag commit ('mark' output)
#
# Optional environment variables:
#   GH_REPO                - Repository in OWNER/REPO format for gh CLI context
#   PULL_REASON            - Short reason, added to the caution notice in the release
#                            body ('mark')
#   MOVE_TAG               - "true" to re-tag the release and force-move the original tag
#                            ('finalize')
#   RESTORE_DELAY_HOURS    - Minimum age (hours) of a pull before its tag is restored
#                            ('restore-tags', default 48)
#   GITHUB_OUTPUT          - If set, 'mark' appends step outputs (original_commit)

# Read schema config from .github/SCHEMA.json
ZIGPY_JSON_FILENAME=$(jq -r '.zigpy_filename' .github/SCHEMA.json)
Z2M_JSON_FILENAME=$(jq -r '.z2m_filename' .github/SCHEMA.json)
MARKDOWN_FILENAME=$(jq -r '.markdown_filename' .github/SCHEMA.json)

ZIGPY_JSON_BETA_FILENAME=$(jq -r '.zigpy_beta_filename' .github/SCHEMA.json)
Z2M_JSON_BETA_FILENAME=$(jq -r '.z2m_beta_filename' .github/SCHEMA.json)
MARKDOWN_BETA_FILENAME=$(jq -r '.markdown_beta_filename' .github/SCHEMA.json)

INDEX_ASSET_FILENAMES=(
  "$ZIGPY_JSON_FILENAME" "$Z2M_JSON_FILENAME" "$MARKDOWN_FILENAME"
  "$ZIGPY_JSON_BETA_FILENAME" "$Z2M_JSON_BETA_FILENAME" "$MARKDOWN_BETA_FILENAME"
)

# Normalize the input tag: accept both "<tag>" and "pulled_<tag>"
# (PULL_TAG is unset for 'restore-tags', which scans all pulled releases)
PULL_TAG="${PULL_TAG:-}"
PULL_TAG="${PULL_TAG#pulled_}"

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

# Print the tag under which the release for $PULL_TAG currently lives: the tag
# itself, or "pulled_<tag>" if the release was re-tagged by 'finalize' (MOVE_TAG)
resolve_release_tag() {
  if gh release view "$PULL_TAG" --json name > /dev/null 2>&1; then
    echo "$PULL_TAG"
  elif gh release view "pulled_$PULL_TAG" --json name > /dev/null 2>&1; then
    echo "pulled_$PULL_TAG"
  else
    echo "::error::No release found for tag $PULL_TAG (or pulled_$PULL_TAG)" >&2
    return 1
  fi
}

# Extract the JSON payload of the hidden pull state comment from a release body
# (passed on stdin); prints nothing if the comment is absent
extract_state() {
  # Second sed (instead of `head -n1`) reads all input, avoiding a SIGPIPE/pipefail
  # failure if a body ever contains more than one state comment
  sed -n 's/^<!-- pulled-release-state \(.*\) -->$/\1/p' | sed -n '1p'
}

# Create or force-update a tag ref ($1 = tag, $2 = commit sha) using the checkout's
# git credentials. Note: GitHub rejects pushes that create or update a tag ref whose
# tree contains workflow files differing from the default branch unless the pushing
# credentials may modify workflow files - a GitHub App with the Workflows (write)
# permission or a classic PAT with the `workflow` scope (the workflow GITHUB_TOKEN
# can never do this).
update_tag() {
  git push origin "$2:refs/tags/$1" --force
}

# Delete a tag ref ($1 = tag) using the checkout's git credentials
delete_tag() {
  git push origin ":refs/tags/$1"
}

# Re-tag a release ($1 = current release tag, $2 = new tag, $3 = commit sha for the
# new tag). The tag ref must be created/updated first: the releases API refuses to
# update a release to a tag that doesn't exist (it does not create tags on update,
# unlike on release creation). Creation goes through the REST API since git pushes
# creating tag refs whose workflow files differ from the default branch are rejected
# for some credential types (e.g. fine-grained PATs even with the Workflows
# permission). Returns nonzero if the tag could not be created.
retag_release() {
  if git ls-remote --exit-code origin "refs/tags/$2" > /dev/null 2>&1; then
    update_tag "$2" "$3"
  elif ! gh api -X POST "repos/{owner}/{repo}/git/refs" -f ref="refs/tags/$2" -f sha="$3" > /dev/null; then
    return 1
  fi
  gh release edit "$1" --tag "$2"
}

# Check if a release title marks the release as pulled ($1 = base tag, $2 = title)
is_pulled_title() {
  local lower_name lower_prefix
  lower_name=$(tr '[:upper:]' '[:lower:]' <<<"$2")
  lower_prefix=$(tr '[:upper:]' '[:lower:]' <<<"$1 - pulled")
  [ "${lower_name:0:${#lower_prefix}}" = "$lower_prefix" ]
}

# Parse an ISO 8601 UTC timestamp to a Unix epoch (GNU and BSD date compatible)
parse_iso_epoch() {
  date -u -d "$1" +%s 2>/dev/null || date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$1" +%s
}

# Check if a release has all of the given assets ($1 = tag, $2.. = filenames).
# Mirrors check_release_assets in update-version-pointers.sh.
has_release_assets() {
  local tag=$1
  shift
  local assets fname
  assets=$(gh release view "$tag" --json assets --jq '.assets[].name') || return 1
  for fname in "$@"; do
    grep -qx -- "$fname" <<<"$assets" || return 1
  done
}

# Add or remove the moved-tag note in the caution notice of a pulled release
# ($1 = tag the release currently lives under, $2 = "add" or "remove",
# $3 = the original tag commit, only for "add").
# The note tells readers that the tag temporarily points at an older release;
# restore-tags removes it again (unpull drops the whole caution anyway). The
# marker comment sits on its own line: inline, it would break the markdown
# rendering of the following bold text.
update_tag_status_note() {
  local release_tag=$1 action=$2 original_commit=${3:-}
  local marker="<!-- pulled-tag-status -->"
  local body
  body=$(gh release view "$release_tag" --json body --jq '.body // ""' | tr -d '\r')

  if [ "$action" = "add" ]; then
    if grep -qF "$marker" <<<"$body"; then
      return 0
    fi
    if ! grep -q '^> \*\*This release has been pulled\*\*' <<<"$body"; then
      echo "::warning::Could not find the caution notice in the release body of $release_tag - not adding the moved-tag note"
      return 0
    fi
    # The full commit hash is used (without code formatting) so GitHub renders it
    # as a clickable, abbreviated commit link
    awk -v marker="$marker" -v sha="$original_commit" '
      { print }
      /^> \*\*This release has been pulled\*\*/ {
        print ">"
        print "> " marker
        print "> The git tag has been temporarily moved to a previous release, so cached download links stop working. The tag will be restored in the next few days. Original commit: " sha
      }' <<<"$body" > /tmp/tag-status-body.md
    echo "Added the moved-tag note to the caution notice of $release_tag"
  else
    if ! grep -qF "$marker" <<<"$body"; then
      return 0
    fi
    # Remove the marker line, the note line after it, and the ">" separator before it
    awk -v marker="> $marker" '
      { if (skip_text) { skip_text = 0; next } }
      $0 == marker { hold = 0; skip_text = 1; next }
      { if (hold) { print ">"; hold = 0 } }
      $0 == ">" { hold = 1; next }
      { print }
      END { if (hold) print ">" }' <<<"$body" > /tmp/tag-status-body.md
    echo "Removed the moved-tag note from the caution notice of $release_tag"
  fi
  gh release edit "$release_tag" --notes-file /tmp/tag-status-body.md
}

# ------------------------------------------------------------------------------
# mark: validate the release and retitle it as pulled
# ------------------------------------------------------------------------------

cmd_mark() {
  # Keep the reason single-line and free of "-->" so it can't corrupt the caution
  # notice or the hidden state comment
  PULL_REASON=$(printf '%s' "${PULL_REASON:-}" | tr '\r\n' '  ' | sed 's/-->/->/g')

  local release_tag info name is_draft is_prerelease body
  release_tag=$(resolve_release_tag)
  info=$(gh release view "$release_tag" --json name,isDraft,isPrerelease,body)
  is_draft=$(jq -r '.isDraft' <<<"$info")
  name=$(jq -r '.name // ""' <<<"$info")
  is_prerelease=$(jq -r '.isPrerelease' <<<"$info")
  body=$(jq -r '.body // ""' <<<"$info" | tr -d '\r')

  if [ "$is_draft" = "true" ]; then
    echo "::error::Release $PULL_TAG is a draft. Only published releases can be pulled."
    exit 1
  fi

  # Refuse to pull if an affected channel would have no electable release to fall
  # back to. This mirrors the election in update-version-pointers.sh exactly: the
  # newest remaining candidate per channel must have all of that channel's index
  # assets (the election does not fall back to older releases when the newest
  # candidate's assets are missing - it just skips the channel, which would leave
  # the version pointer referencing the pulled release). Pulling a stable release
  # affects both channels (stable releases also participate in the beta election);
  # pulling a pre-release only affects the beta channel.
  local releases_json invalid_titles candidates_json beta_fallback stable_fallback
  releases_json=$(gh release list --exclude-drafts --limit 200 --json tagName,name,isPrerelease)

  # Warn up front about malformed release titles (using the election's exact
  # detection from update-version-pointers.sh) but DO NOT refuse the pull: during
  # an incident, containing the broken release matters more than a clean run.
  # The fallback pre-check below already excludes malformed titles from the
  # candidates, so proceeding is sound; the later pointer reconcile still fails
  # loudly on the same titles (leaving the channel on the designed fail-closed
  # 404 state via finalize), and a re-run of the reconcile heals the pointers
  # once the titles are fixed.
  # (The pulled release's own title is handled separately below with a hard
  # error, so it is excluded here to avoid contradictory annotations)
  invalid_titles=$(jq -r --arg tag "$PULL_TAG" '
    .[] | (.name // "") as $name
    | ((.tagName | ascii_downcase) + " - pulled") as $pulled_prefix
    | ($name | ascii_downcase | startswith($pulled_prefix)) as $has_pulled_title
    | select(
        .tagName != $tag
        and (.tagName | startswith("pulled_") | not)
        and ($name != "" and $name != .tagName and ($has_pulled_title | not))
      )
    | "\(.tagName): \"\($name)\""' <<<"$releases_json")
  if [ -n "$invalid_titles" ]; then
    echo "::warning::Unrelated release title(s) must be either \"<tag>\" or \"<tag> - pulled ...\". The pull proceeds, but the pointer update will fail until these are fixed (then re-run publish-release-json.yml): $invalid_titles"
  fi

  candidates_json=$(jq --arg tag "$PULL_TAG" '
        [.[] | select(.tagName != $tag and (.tagName | startswith("pulled_") | not))
        | (.name // "") as $name
        | select($name == "" or $name == .tagName)]' <<<"$releases_json")
  beta_fallback=$(jq -r '.[].tagName' <<<"$candidates_json" | sort -V | tail -n1)
  if [ -z "$beta_fallback" ] \
    || ! has_release_assets "$beta_fallback" "$ZIGPY_JSON_BETA_FILENAME" "$Z2M_JSON_BETA_FILENAME" "$MARKDOWN_BETA_FILENAME"; then
    echo "::error::No other (non-pulled) release with beta index assets exists to fall back to. Refusing to pull $PULL_TAG. If the fallback release ($beta_fallback) is missing assets, regenerate them first (publish-release-json.yml with tag_name)."
    exit 1
  fi
  if [ "$is_prerelease" != "true" ]; then
    stable_fallback=$(jq -r '.[] | select(.isPrerelease | not) | .tagName' <<<"$candidates_json" | sort -V | tail -n1)
    if [ -z "$stable_fallback" ] \
      || ! has_release_assets "$stable_fallback" "$ZIGPY_JSON_FILENAME" "$Z2M_JSON_FILENAME" "$MARKDOWN_FILENAME"; then
      echo "::error::No other (non-pulled) stable release with index assets exists to fall back to. Refusing to pull $PULL_TAG. If the fallback release ($stable_fallback) is missing assets, regenerate them first (publish-release-json.yml with tag_name)."
      exit 1
    fi
  fi

  # Determine the release's original commit: from a previous pull's recorded state
  # if present, otherwise from the tag the release currently lives under
  git fetch origin --tags --force --quiet
  local state original_commit
  state=$(extract_state <<<"$body")
  if [ -n "$state" ]; then
    original_commit=$(jq -r '.original_commit // empty' <<<"$state")
  else
    original_commit=$(git rev-parse "refs/tags/$release_tag^{commit}")
  fi

  # Determine the new title (idempotent if already marked as pulled)
  local new_title
  if is_pulled_title "$PULL_TAG" "$name"; then
    echo "::notice::Release $PULL_TAG is already marked as pulled (title: \"$name\")"
    new_title="$name"
  elif [ -n "$name" ] && [ "$name" != "$PULL_TAG" ]; then
    echo "::error::Release $PULL_TAG has an unexpected title (\"$name\"). Fix the title first."
    exit 1
  else
    new_title="$PULL_TAG - pulled"
  fi

  # Prepend a caution notice to the release body, with a hidden state comment used by
  # 'unpull' and 'restore-tags' (idempotent: skipped if a state comment is present)
  if [ -z "$state" ]; then
    local state_json
    state_json=$(jq -cn \
      --arg pulled_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      --arg original_commit "$original_commit" \
      --arg reason "${PULL_REASON:-}" \
      '{pulled_at: $pulled_at, original_commit: $original_commit}
       + (if $reason != "" then {reason: $reason} else {} end)')
    {
      echo "<!-- pulled-release-state $state_json -->"
      echo "> [!CAUTION]"
      echo "> **This release has been pulled** (on $(date -u +%Y-%m-%d))${PULL_REASON:+: $PULL_REASON}."
      echo
      echo "$body"
    } > /tmp/pulled-release-body.md
    gh release edit "$release_tag" --title "$new_title" --notes-file /tmp/pulled-release-body.md
  else
    gh release edit "$release_tag" --title "$new_title"
  fi
  echo "::notice::Marked release $PULL_TAG as pulled (title: \"$new_title\")"

  # Expose results to the other workflow steps
  if [ -n "${GITHUB_OUTPUT:-}" ]; then
    echo "original_commit=$original_commit" >> "$GITHUB_OUTPUT"
  fi
}

# ------------------------------------------------------------------------------
# finalize: rename the pulled release's index assets and optionally move the tag
# ------------------------------------------------------------------------------

cmd_finalize() {
  local release_tag
  release_tag=$(resolve_release_tag)

  # Rename each index asset (prefix with "pulled_") so its original URL stops
  # resolving. Clients still holding a stale version pointer fail closed with a
  # 404 (zigpy keeps its previously-cached images on index fetch errors) instead
  # of downloading the pulled index. Renaming preserves the original assets
  # (upload date, download count) and is trivially reversible, unlike replacing
  # or deleting them.
  local assets_json
  assets_json=$(gh api "repos/{owner}/{repo}/releases/tags/$release_tag" --jq '[.assets[] | {id, name}]')

  local fname asset_id
  for fname in "${INDEX_ASSET_FILENAMES[@]}"; do
    asset_id=$(jq -r --arg name "$fname" '.[] | select(.name == $name) | .id' <<<"$assets_json")
    if [ -n "$asset_id" ]; then
      gh api -X PATCH "repos/{owner}/{repo}/releases/assets/$asset_id" -f name="pulled_$fname" > /dev/null
      echo "Renamed asset $fname to pulled_$fname on $PULL_TAG"
    elif jq -e --arg name "pulled_$fname" '.[] | select(.name == $name)' <<<"$assets_json" > /dev/null; then
      echo "Asset $fname on $PULL_TAG is already renamed to pulled_$fname"
    else
      echo "::warning::Asset $fname not found on $PULL_TAG - nothing to rename"
    fi
  done

  # Optionally re-tag the release and force-move the original tag
  if [ "${MOVE_TAG:-false}" != "true" ]; then
    echo "Not moving the git tag (move_tag input not set)"
    return
  fi

  if [ -z "${ORIGINAL_COMMIT:-}" ]; then
    echo "::error::ORIGINAL_COMMIT is not set - cannot move the tag"
    exit 1
  fi

  # Move the tag to the newest non-pulled release *older* than the pulled one -
  # NOT the currently elected (newest) release: a newer release's tree still
  # contains the pulled image files (pulled images are only disabled in the
  # index, the files stay in the repo), so only an older tree makes exactly the
  # files added by the pulled release stop resolving
  local candidates target_tag
  candidates=$(gh release list --exclude-drafts --limit 200 --json tagName,name \
    | jq -r --arg tag "$PULL_TAG" '
        .[] | select(.tagName != $tag and (.tagName | startswith("pulled_") | not))
        | (.name // "") as $name
        | select($name == "" or $name == .tagName)
        | .tagName')
  # (sed instead of `head -n1` to avoid SIGPIPE-under-pipefail, as elsewhere;
  # grep -F so tags are matched literally, not as regexes)
  target_tag=$(printf '%s\n' "$candidates" "$PULL_TAG" | sort -V | grep -Fx -B1 -- "$PULL_TAG" | sed -n '1p')
  if [ -z "$target_tag" ] || [ "$target_tag" = "$PULL_TAG" ]; then
    echo "::error::Cannot move tag $PULL_TAG: no older release to point it at"
    exit 1
  fi

  git fetch origin --tags --force --quiet

  # Re-tag the release to "pulled_<tag>" (at the original commit) so the release keeps
  # pointing at the code it was built from while the original tag is moved
  local retagged=true
  if [ "$release_tag" = "$PULL_TAG" ]; then
    if retag_release "$PULL_TAG" "pulled_$PULL_TAG" "$ORIGINAL_COMMIT"; then
      echo "::notice::Re-tagged release $PULL_TAG to pulled_$PULL_TAG (at original commit $ORIGINAL_COMMIT)"
    else
      # Not fatal: the release then stays on its original tag (pointing at the older
      # release's commit until restore-pulled-tags.yml restores it); the original
      # commit remains recorded in the release body
      retagged=false
      echo "::warning::Could not create tag pulled_$PULL_TAG (the token cannot create tag refs whose workflow files differ from the default branch) - the release stays on tag $PULL_TAG"
    fi
  else
    echo "Release is already re-tagged to $release_tag"
  fi

  # Force-move the original tag to the target (next-older) release's commit
  local target_commit current_commit
  target_commit=$(git rev-parse "refs/tags/$target_tag^{commit}")
  current_commit=$(git rev-parse "refs/tags/$PULL_TAG^{commit}")
  if [ "$target_commit" = "$current_commit" ]; then
    echo "::notice::Tag $PULL_TAG already points at $target_commit - nothing to move"
  else
    update_tag "$PULL_TAG" "$target_commit"
    if [ "$retagged" = true ]; then
      echo "::notice::Force-moved tag $PULL_TAG from $current_commit to $target_commit (the commit of $target_tag). The original commit is recorded in the release body and tagged as pulled_$PULL_TAG."
    else
      echo "::notice::Force-moved tag $PULL_TAG from $current_commit to $target_commit (the commit of $target_tag). The original commit is recorded in the release body."
    fi
  fi

  # Note the moved tag in the caution notice (removed again by restore-tags; unpull
  # replaces the whole caution). The release may have been re-tagged above.
  release_tag=$(resolve_release_tag)
  update_tag_status_note "$release_tag" add "$ORIGINAL_COMMIT"
}

# ------------------------------------------------------------------------------
# unpull: reinstate a pulled release
# ------------------------------------------------------------------------------

cmd_unpull() {
  local release_tag info name is_draft body
  release_tag=$(resolve_release_tag)
  info=$(gh release view "$release_tag" --json name,isDraft,body)
  is_draft=$(jq -r '.isDraft' <<<"$info")
  name=$(jq -r '.name // ""' <<<"$info")
  body=$(jq -r '.body // ""' <<<"$info" | tr -d '\r')

  if [ "$is_draft" = "true" ]; then
    echo "::error::Release $PULL_TAG is a draft. Only published releases can be un-pulled."
    exit 1
  fi

  local state pulled_at original_commit reason
  state=$(extract_state <<<"$body")
  pulled_at=""
  original_commit=""
  reason=""
  if [ -n "$state" ]; then
    pulled_at=$(jq -r '.pulled_at // empty' <<<"$state")
    original_commit=$(jq -r '.original_commit // empty' <<<"$state")
    reason=$(jq -r '.reason // empty' <<<"$state")
  fi

  # The title may already be restored (e.g. un-pull via a manual title edit, which
  # dispatches this via the `edited` release event) - then only the remaining pull
  # state (tag/commit association, assets, body notice) needs to be cleaned up
  if ! is_pulled_title "$PULL_TAG" "$name"; then
    if [ -n "$name" ] && [ "$name" != "$PULL_TAG" ]; then
      echo "::error::Release $PULL_TAG has an unexpected title (\"$name\"). Fix the title first."
      exit 1
    fi
    if [ -z "$state" ] && [ "$release_tag" = "$PULL_TAG" ]; then
      echo "::notice::Release $PULL_TAG is not pulled - nothing to un-pull."
      return 0
    fi
    echo "Title of $PULL_TAG is already restored - cleaning up the remaining pull state"
  fi
  if [ -z "$state" ]; then
    echo "::warning::Release $PULL_TAG has no recorded pull state in its body (pulled manually?)"
  fi

  # Restore the original tag/commit association if the tag was moved
  git fetch origin --tags --force --quiet
  if [ -n "$original_commit" ]; then
    local current_commit
    current_commit=$(git rev-parse "refs/tags/$PULL_TAG^{commit}" 2>/dev/null || echo "")
    if [ "$current_commit" != "$original_commit" ]; then
      update_tag "$PULL_TAG" "$original_commit"
      echo "::notice::Restored tag $PULL_TAG to its original commit $original_commit"
    else
      echo "Tag $PULL_TAG already points at its original commit"
    fi
  elif [ "$release_tag" != "$PULL_TAG" ]; then
    echo "No recorded original commit for $PULL_TAG - restoring the tag from the release's current $release_tag tag"
  else
    echo "::warning::No recorded original commit for $PULL_TAG - not touching the git tag"
  fi
  if [ "$release_tag" != "$PULL_TAG" ]; then
    retag_release "$release_tag" "$PULL_TAG" "${original_commit:-$(git rev-parse "refs/tags/$release_tag^{commit}")}"
    delete_tag "$release_tag"
    echo "::notice::Re-tagged release back from $release_tag to $PULL_TAG and deleted the $release_tag tag"
    release_tag="$PULL_TAG"
  fi

  # Rename the index assets back to their original names
  local assets_json fname asset_id duplicate_id
  assets_json=$(gh api "repos/{owner}/{repo}/releases/tags/$release_tag" --jq '[.assets[] | {id, name}]')
  for fname in "${INDEX_ASSET_FILENAMES[@]}"; do
    asset_id=$(jq -r --arg name "pulled_$fname" '.[] | select(.name == $name) | .id' <<<"$assets_json")
    if [ -n "$asset_id" ]; then
      # A same-named asset may exist (e.g. regenerated while the release was pulled);
      # the pulled_* one is the original - delete the duplicate so the rename can't
      # fail with a name conflict
      duplicate_id=$(jq -r --arg name "$fname" '.[] | select(.name == $name) | .id' <<<"$assets_json")
      if [ -n "$duplicate_id" ]; then
        gh api -X DELETE "repos/{owner}/{repo}/releases/assets/$duplicate_id" > /dev/null
        echo "::warning::Deleted duplicate asset $fname from $PULL_TAG (uploaded while the release was pulled)"
      fi
      gh api -X PATCH "repos/{owner}/{repo}/releases/assets/$asset_id" -f name="$fname" > /dev/null
      echo "Renamed asset pulled_$fname back to $fname on $PULL_TAG"
    fi
  done

  # Replace the caution notice (and hidden state comment) with a note recording the
  # pull/re-add cycle. Notes from earlier cycles further down in the body are kept,
  # so repeated pulls/un-pulls stack one note each.
  {
    echo "> [!NOTE]"
    echo "> This release was temporarily pulled${pulled_at:+ on ${pulled_at%%T*}}${reason:+ (${reason})} and re-added on $(date -u +%Y-%m-%d)."
    echo
  } > /tmp/unpull-note.md
  if [ -n "$state" ]; then
    awk -v note_file=/tmp/unpull-note.md '
      /^<!-- pulled-release-state / {
        while ((getline line < note_file) > 0) print line
        skip = 1
        next
      }
      skip && /^>/ { next }
      skip { skip = 0; if ($0 ~ /^[[:space:]]*$/) next }
      { print }
    ' <<<"$body" > /tmp/unpulled-release-body.md
  else
    cat /tmp/unpull-note.md > /tmp/unpulled-release-body.md
    echo "$body" >> /tmp/unpulled-release-body.md
  fi

  # Restore the title, re-including the release in the version pointer election
  gh release edit "$release_tag" --title "$PULL_TAG" --notes-file /tmp/unpulled-release-body.md
  echo "::notice::Un-pulled release $PULL_TAG (title restored to \"$PULL_TAG\")"
}

# ------------------------------------------------------------------------------
# restore-tags: restore moved tags of still-pulled releases after a delay
# ------------------------------------------------------------------------------

cmd_restore_tags() {
  local delay_hours="${RESTORE_DELAY_HOURS:-48}"
  # A non-numeric delay would make the age comparison below error out, which an
  # `if` treats as "old enough" - i.e. tags would be restored immediately
  if ! [[ "$delay_hours" =~ ^[0-9]+$ ]]; then
    echo "::error::RESTORE_DELAY_HOURS must be a whole number of hours (got \"$delay_hours\")"
    exit 1
  fi
  local now restore_failures=0
  now=$(date -u +%s)
  git fetch origin --tags --force --quiet

  local pulled_releases
  pulled_releases=$(gh release list --exclude-drafts --limit 200 --json tagName,name | jq -c '
    .[] | (.name // "") as $name
    | (if (.tagName | startswith("pulled_")) then (.tagName | ltrimstr("pulled_")) else .tagName end) as $base
    | (($base | ascii_downcase) + " - pulled") as $pulled_prefix
    | select(
        (.tagName | startswith("pulled_"))
        or ($name | ascii_downcase | startswith($pulled_prefix))
      )
    | {release_tag: .tagName, base_tag: $base}')
  if [ -z "$pulled_releases" ]; then
    echo "No pulled releases found - nothing to do"
    return
  fi

  # Loop input on fd 3 so commands in the body can't consume the entry list
  local entry release_tag base_tag body state original_commit pulled_at base_commit pulled_epoch age_hours
  while IFS= read -r -u 3 entry; do
    release_tag=$(jq -r '.release_tag' <<<"$entry")
    base_tag=$(jq -r '.base_tag' <<<"$entry")

    body=$(gh release view "$release_tag" --json body --jq '.body // ""' | tr -d '\r')
    state=$(extract_state <<<"$body")
    # Plain echo (not ::warning::): sync-pull-state re-dispatches the
    # corrective run for exactly this case (pulled title, no state marker),
    # so it self-heals
    if [ -z "$state" ]; then
      echo "Pulled release $base_tag has no recorded pull state - skipping"
      continue
    fi
    # Guard the jq parses: a hand-edited/truncated state comment must skip this
    # release, not abort the whole sweep (set -e would kill the loop otherwise).
    # Not counted as a failure: a malformed body never becomes valid by
    # retrying, and counting it would keep the weekly run red forever
    if ! original_commit=$(jq -r '.original_commit // empty' <<<"$state" 2>/dev/null) \
      || ! pulled_at=$(jq -r '.pulled_at // empty' <<<"$state" 2>/dev/null); then
      echo "::warning::Pulled release $base_tag has malformed pull state - skipping"
      continue
    fi
    # ::warning:: (like the malformed-state skip) so the stall is visible on
    # an otherwise green weekly run - sync-pull-state won't self-heal these
    if [ -z "$original_commit" ] || [ -z "$pulled_at" ]; then
      echo "::warning::Pulled release $base_tag has incomplete pull state - skipping"
      continue
    fi

    base_commit=$(git rev-parse "refs/tags/$base_tag^{commit}" 2>/dev/null || echo "")
    if [ "$base_commit" = "$original_commit" ] && [ "$release_tag" = "$base_tag" ]; then
      # Already restored - but still sweep up leftovers of a partially-failed
      # earlier restore (a lingering pulled_ tag or moved-tag note)
      if git ls-remote --exit-code origin "refs/tags/pulled_$base_tag" > /dev/null 2>&1; then
        delete_tag "pulled_$base_tag" \
          || { echo "::warning::Failed to delete leftover tag pulled_$base_tag"; restore_failures=$((restore_failures + 1)); }
      fi
      update_tag_status_note "$base_tag" remove \
        || { echo "::warning::Failed to remove the moved-tag note of $base_tag"; restore_failures=$((restore_failures + 1)); }
      echo "Tag $base_tag already points at its original commit"
      continue
    fi

    if ! pulled_epoch=$(parse_iso_epoch "$pulled_at" 2>/dev/null); then
      echo "::warning::Cannot parse pulled_at timestamp (\"$pulled_at\") of $base_tag - skipping"
      continue
    fi
    age_hours=$(( (now - pulled_epoch) / 3600 ))
    if [ "$age_hours" -lt "$delay_hours" ]; then
      echo "Tag $base_tag was moved, but the pull is only ${age_hours}h old (< ${delay_hours}h) - skipping for now"
      continue
    fi

    # Isolate failures per release (&&-chained: `set -e` is ineffective inside an
    # `if` condition) so one stuck restore - e.g. a rejected tag push - can't
    # starve the remaining releases
    if ! { { [ "$base_commit" = "$original_commit" ] || update_tag "$base_tag" "$original_commit"; } \
      && { [ "$release_tag" = "$base_tag" ] || { retag_release "$release_tag" "$base_tag" "$original_commit" && delete_tag "$release_tag"; }; } \
      && update_tag_status_note "$base_tag" remove; }; then
      echo "::warning::Failed to restore the tag of $base_tag - skipping (retried on the next run)"
      restore_failures=$((restore_failures + 1))
      continue
    fi
    echo "::notice::Restored tag $base_tag to its original commit $original_commit (pull is ${age_hours}h old; the release stays pulled)"
  done 3<<<"$pulled_releases"

  if [ "$restore_failures" -gt 0 ]; then
    echo "::error::$restore_failures tag restore(s) failed"
    return 1
  fi
}

# ------------------------------------------------------------------------------
# sync-pull-state: dispatch pull/un-pull for releases whose title disagrees with
# their recorded pull state
# ------------------------------------------------------------------------------

# Self-healing for lost `edited`-event dispatches: GitHub keeps at most one pending
# workflow run per concurrency group and cancels older pending ones, so a corrective
# pull/un-pull run dispatched by publish-release-json.yml can be silently cancelled
# while queued. Run periodically by restore-pulled-tags.yml. Requires a GH_TOKEN
# with `actions: write` to dispatch workflows.
cmd_sync_pull_state() {
  # The REST list endpoint includes release bodies, so one call per page covers
  # everything; --paginate emits one object per release across all pages
  local releases count
  releases=$(gh api --paginate "repos/{owner}/{repo}/releases?per_page=100" --jq '
    .[] | select(.draft | not) | {tag: .tag_name, name: (.name // ""), body: (.body // "")}' \
    | jq -s '.')
  count=$(jq 'length' <<<"$releases")
  if [ "$count" -eq 0 ]; then
    echo "No releases found - nothing to do"
    return
  fi

  local i entry release_tag base_tag name body title_pulled has_state assets
  for ((i = 0; i < count; i++)); do
    entry=$(jq -c ".[$i]" <<<"$releases")
    release_tag=$(jq -r '.tag' <<<"$entry")
    name=$(jq -r '.name' <<<"$entry")
    body=$(jq -r '.body' <<<"$entry" | tr -d '\r')
    base_tag="${release_tag#pulled_}"

    title_pulled=false
    if is_pulled_title "$base_tag" "$name"; then
      title_pulled=true
    elif [ -n "$name" ] && [ "$name" != "$base_tag" ]; then
      # Unexpected title (on "pulled_"-tagged releases this includes the tag name
      # itself): un-pull would refuse it, so don't dispatch anything
      echo "::warning::Release $release_tag has an unexpected title (\"$name\") - skipping"
      continue
    fi

    has_state=false
    if grep -q '<!-- pulled-release-state ' <<<"$body"; then
      has_state=true
    fi

    # Note: with several inconsistent releases at once, dispatches beyond the
    # first may be dropped (pull/unpull share a concurrency group that keeps
    # at most one pending run) - the rest heal on the next scheduled sweep
    if [ "$title_pulled" = true ] && [ "$has_state" = false ]; then
      gh workflow run pull-release.yml -f tag_name="$base_tag"
      echo "::notice::Release $base_tag is titled as pulled but has no recorded pull state - dispatched pull-release.yml"
    elif [ "$title_pulled" = false ] && { [ "$has_state" = true ] || [ "$release_tag" != "$base_tag" ]; }; then
      gh workflow run unpull-release.yml -f tag_name="$base_tag"
      echo "::notice::Release $base_tag is no longer titled as pulled but still has pull state - dispatched unpull-release.yml"
    elif [ "$title_pulled" = true ]; then
      # Title and state agree, but a pull whose finalize step failed can still
      # have its original-named (reachable) index assets - re-dispatch the
      # idempotent pull to complete the asset renames and tag move
      assets=$(gh release view "$release_tag" --json assets --jq '.assets[].name' 2>/dev/null || true)
      if grep -qx -- "$ZIGPY_JSON_FILENAME" <<<"$assets"; then
        gh workflow run pull-release.yml -f tag_name="$base_tag"
        echo "::notice::Release $base_tag is pulled but still has original-named index assets - dispatched pull-release.yml to complete the pull"
      fi
    fi
  done
}

# ------------------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------------------

case "${1:-}" in
  mark)
    cmd_mark
    ;;
  finalize)
    cmd_finalize
    ;;
  unpull)
    cmd_unpull
    ;;
  restore-tags)
    cmd_restore_tags
    ;;
  sync-pull-state)
    cmd_sync_pull_state
    ;;
  *)
    echo "Usage: $0 {mark|finalize|unpull|restore-tags|sync-pull-state}" >&2
    exit 1
    ;;
esac
