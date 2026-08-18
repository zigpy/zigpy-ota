#!/usr/bin/env bash
set -euo pipefail

# Acts on the OTA image files a labeled PR added: opens a bot PR against the
# default branch that disables, re-enables, or removes those images. Used by
# manage-ota-images.yml.
#
# Required environment variables:
#   GH_TOKEN         - GitHub token for gh CLI (PR creation/comments; branch pushes
#                      use the credentials of the checkout)
#   GH_REPO          - Repository in OWNER/REPO format for gh CLI context
#   LABEL_NAME       - The label that triggered this (ota-disable|ota-enable|ota-remove)
#   SOURCE_PR        - Number of the labeled PR
#   DEFAULT_BRANCH   - The repository default branch (base for the bot PR)

case "$LABEL_NAME" in
  ota-disable)
    ACTION="disable"
    ACTION_TITLE="Disable"
    ;;
  ota-enable)
    ACTION="enable"
    ACTION_TITLE="Re-enable"
    ;;
  ota-remove)
    ACTION="remove"
    ACTION_TITLE="Remove"
    ;;
  *)
    echo "::error::Unexpected label: $LABEL_NAME"
    exit 1
    ;;
esac

comment_on_source_pr() {
  gh pr comment "$SOURCE_PR" --body "$1"
}

# ------------------------------------------------------------------------------
# Collect the labeled PR's image files that exist on the default branch
# ------------------------------------------------------------------------------

# File paths from the git tree are safe to use as arguments (git forbids ".."
# path components), and everything below passes them as quoted list elements.
# Filenames containing control characters (e.g. newlines, which would split into
# multiple lines and could alias unrelated files) are rejected outright. The API
# call is a separate hard-failing step so an API error can't be mistaken for
# "this PR has no image files".
pr_files=$(gh api --paginate "repos/{owner}/{repo}/pulls/$SOURCE_PR/files" \
  --jq 'if any(.[]; .filename | test("[[:cntrl:]]")) then error("control character in a PR filename") else .[].filename end')
mapfile -t pr_image_files < <(grep '^images/' <<<"$pr_files" || true)

existing_files=()
yaml_files=()
for f in "${pr_image_files[@]}"; do
  if [ -f "$f" ]; then
    existing_files+=("$f")
    case "$f" in
      *.yaml) yaml_files+=("$f") ;;
    esac
  fi
done

if [ "${#existing_files[@]}" -eq 0 ]; then
  echo "::notice::No image files from PR #$SOURCE_PR exist on $DEFAULT_BRANCH - nothing to $ACTION"
  comment_on_source_pr "No image files from this PR exist on \`$DEFAULT_BRANCH\` - nothing to $ACTION."
  exit 0
fi

# disable/enable edit the YAML metadata; a PR can touch image binaries without
# any YAML files existing on the default branch
if [ "$ACTION" != "remove" ] && [ "${#yaml_files[@]}" -eq 0 ]; then
  echo "::notice::No image YAML files from PR #$SOURCE_PR exist on $DEFAULT_BRANCH - nothing to $ACTION"
  comment_on_source_pr "No image YAML files from this PR exist on \`$DEFAULT_BRANCH\` - nothing to $ACTION."
  exit 0
fi

# ------------------------------------------------------------------------------
# Apply the action on a bot branch
# ------------------------------------------------------------------------------

BRANCH_NAME="bot/ota-$ACTION/pr-$SOURCE_PR"
git checkout -B "$BRANCH_NAME"

case "$ACTION" in
  disable)
    uv run zigpy-ota set-image-disabled "${yaml_files[@]}"
    git add images/
    ;;
  enable)
    uv run zigpy-ota set-image-disabled --enable "${yaml_files[@]}"
    git add images/
    ;;
  remove)
    git rm -q -- "${existing_files[@]}"
    ;;
esac

if git diff --cached --quiet; then
  echo "::notice::Images from PR #$SOURCE_PR are already in the desired state - nothing to change"
  # An open bot PR for an opposite action would change this state when merged -
  # point it out so the intent behind this label isn't silently lost
  sibling_note=""
  for other_action in disable enable remove; do
    [ "$other_action" = "$ACTION" ] && continue
    other_pr=$(gh pr list --head "bot/ota-$other_action/pr-$SOURCE_PR" --state open --json number --jq '.[0].number // empty' 2>/dev/null || echo "")
    if [ -n "$other_pr" ]; then
      sibling_note="$sibling_note Note: #$other_pr (ota-$other_action) is still open and would change this state when merged."
    fi
  done
  comment_on_source_pr "The images from this PR are already in the desired state on \`$DEFAULT_BRANCH\` - nothing to $ACTION.$sibling_note"
  exit 0
fi

# List the affected files in the commit body: the upstream repo squash-merges
# PRs with all commit bodies included, so this is what ends up in the history
CHANGED_FILES=$(git diff --cached --name-only)
FILE_LIST=$(sed 's/^/- `/;s/$/`/' <<<"$CHANGED_FILES")

# Each YAML file corresponds to one image (for `remove`, the changed files also
# include the binaries)
IMAGE_COUNT=$(grep -c '\.yaml$' <<<"$CHANGED_FILES" || true)
if [ "$IMAGE_COUNT" -eq 0 ]; then
  IMAGE_COUNT=$(wc -l <<<"$CHANGED_FILES" | tr -d ' ')
fi
NOUN="images"
if [ "$IMAGE_COUNT" -eq 1 ]; then
  NOUN="image"
fi

case "$ACTION" in
  disable)
    COMMIT_BODY="Disabled $NOUN:"
    ;;
  enable)
    COMMIT_BODY="Re-enabled $NOUN:"
    ;;
  remove)
    COMMIT_BODY="Removed files:"
    ;;
esac
COMMIT_BODY="$COMMIT_BODY
$(sed 's/^/- /' <<<"$CHANGED_FILES")"

git commit -q -m "$ACTION_TITLE OTA $NOUN from #$SOURCE_PR" -m "$COMMIT_BODY"
# The bot branch is rebuilt from the default branch every run; the lease avoids
# clobbering pushes made to it (e.g. by a maintainer) after this run's fetch
git push --force-with-lease origin "$BRANCH_NAME"

# ------------------------------------------------------------------------------
# Create (or note the update of) the bot PR and link it from the source PR
# ------------------------------------------------------------------------------

PR_BODY="## $ACTION_TITLE OTA $NOUN

Requested via the \`$LABEL_NAME\` label on #$SOURCE_PR. Affected files:

$FILE_LIST"

EXISTING_PR=$(gh pr list --head "$BRANCH_NAME" --state open --json number --jq '.[0].number' 2>/dev/null || echo "")
if [ -n "$EXISTING_PR" ]; then
  gh pr edit "$EXISTING_PR" --title "$ACTION_TITLE OTA $NOUN from #$SOURCE_PR" --body "$PR_BODY"
  PR_URL=$(gh pr view "$EXISTING_PR" --json url --jq '.url')
  PR_VERB="Updated"
  echo "::notice::Updated existing PR #$EXISTING_PR"
else
  PR_URL=$(gh pr create \
    --title "$ACTION_TITLE OTA $NOUN from #$SOURCE_PR" \
    --body "$PR_BODY" \
    --base "$DEFAULT_BRANCH")
  PR_VERB="Opened"
  echo "::notice::Created PR: $PR_URL"
fi

# The work is done at this point - a failed comment shouldn't fail the run
comment_on_source_pr "$PR_VERB $PR_URL to $ACTION the $NOUN from this PR (via the \`$LABEL_NAME\` label)." \
  || echo "::warning::Could not comment on PR #$SOURCE_PR"
