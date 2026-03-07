#!/usr/bin/env bash
# Creates or updates a PR for an OTA submission
#
# Required environment variables:
#   GH_TOKEN            - GitHub token for gh CLI
#   BRANCH_NAME         - Branch name for the PR
#   ISSUE_NUMBER        - GitHub issue number
#   ISSUE_TITLE         - GitHub issue title
#   ISSUE_AUTHOR_LOGIN  - GitHub username of issue creator
#   ISSUE_AUTHOR_ID     - GitHub user ID of issue creator
#   PR_BODY_FILE        - Path to file containing PR body markdown
#
# Optional environment variables:
#   COMMIT_MSG_FILE     - Path to file containing detailed commit message
#   GH_REPO             - Repository in OWNER/REPO format for gh CLI context

set -euo pipefail

# Add pull_request field to YAML files and commit
# Returns 0 if changes were committed, 1 if no YAML files to update
add_pr_to_yaml_files() {
  local pr_number="$1"
  local yaml_files
  yaml_files=$(git diff --name-only HEAD~1 HEAD -- 'images/*.yaml' 'images/**/*.yaml' || true)

  if [ -z "$yaml_files" ]; then
    echo "No YAML files to update"
    return 1
  fi

  echo "Adding pull_request field to YAML files..."
  for yaml_file in $yaml_files; do
    if [ -f "$yaml_file" ] && ! grep -q "^pull_request:" "$yaml_file"; then
      echo "Updating $yaml_file"
      # Insert pull_request after source_url if present, otherwise after source_file_name
      if grep -q "^source_url:" "$yaml_file"; then
        sed -i "s|^source_url:.*|&\npull_request: $pr_number|" "$yaml_file"
      else
        sed -i "s|^source_file_name:.*|&\npull_request: $pr_number|" "$yaml_file"
      fi
    fi
  done

  git add images/
  if git diff --cached --quiet; then
    echo "No changes to commit (all files already had pull_request field)"
    return 1
  fi
  git commit -m "Add PR number to YAML metadata"
  return 0
}

# Check if PR already exists (for resubmits) so we can get PR number early
EXISTING_PR_NUMBER=$(gh pr view "$BRANCH_NAME" --json number --jq '.number' 2>/dev/null || echo "")
if [ -n "$EXISTING_PR_NUMBER" ]; then
  echo "Existing PR found: #$EXISTING_PR_NUMBER"
fi

# Delete local branch if it exists and create new one
git branch -D "$BRANCH_NAME" 2>/dev/null || true
git checkout -b "$BRANCH_NAME"

# Add changes in images directory
git add images/

# Get issue creator information for co-authoring
ISSUE_AUTHOR_NAME=$(gh api /users/"$ISSUE_AUTHOR_LOGIN" --jq '.name // .login')
ISSUE_AUTHOR_EMAIL="${ISSUE_AUTHOR_ID}+${ISSUE_AUTHOR_LOGIN}@users.noreply.github.com"

# First commit: Add OTA files
COMMIT_TITLE="Add OTA files from issue #${ISSUE_NUMBER}"
COMMIT_FOOTER="Closes: #${ISSUE_NUMBER}
Co-authored-by: ${ISSUE_AUTHOR_NAME} <${ISSUE_AUTHOR_EMAIL}>"

if [ -n "${COMMIT_MSG_FILE:-}" ] && [ -f "$COMMIT_MSG_FILE" ]; then
  # Include commit file as body with footer
  COMMIT_BODY=$(cat "$COMMIT_MSG_FILE")
  FULL_MSG=$(printf '%s\n\n%s\n\n%s' "$COMMIT_TITLE" "$COMMIT_BODY" "$COMMIT_FOOTER")
  git commit -m "$FULL_MSG"
else
  git commit -m "$COMMIT_TITLE" -m "$COMMIT_FOOTER"
fi

# Build PR body with footer
PR_BODY=$(cat "$PR_BODY_FILE")
PR_BODY_WITH_FOOTER="${PR_BODY}

---

- Closes #${ISSUE_NUMBER}
- Submitted by @${ISSUE_AUTHOR_LOGIN}"

if [ -n "$EXISTING_PR_NUMBER" ]; then
  # Resubmit: We have the PR number, so we can create both commits and push once
  add_pr_to_yaml_files "$EXISTING_PR_NUMBER" || true
  git push --force-with-lease origin "$BRANCH_NAME"
  gh pr edit "$EXISTING_PR_NUMBER" --title "$ISSUE_TITLE" --body "$PR_BODY_WITH_FOOTER"
else
  # New PR: Must push first to create PR, then add second commit
  git push --force-with-lease origin "$BRANCH_NAME"

  echo "Creating new PR..."
  PR_URL=$(gh pr create \
    --title "$ISSUE_TITLE" \
    --body "$PR_BODY_WITH_FOOTER" \
    --label "ota-submit" \
    --base dev)
  PR_NUMBER="${PR_URL##*/}"

  add_pr_to_yaml_files "$PR_NUMBER" || true
  git push origin "$BRANCH_NAME"
fi

# Add "ota-processed" label to the issue
gh issue edit "$ISSUE_NUMBER" --add-label "ota-processed"
