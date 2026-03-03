"""Bump the OTA schema version for individual schemas or all at once.

Usage:
    python .github/scripts/bump-schema-version.py zigpy --apply        # Auto-increment zigpy
    python .github/scripts/bump-schema-version.py z2m v3 --apply       # Set z2m to v3
    python .github/scripts/bump-schema-version.py all --apply          # Auto-increment all
    python .github/scripts/bump-schema-version.py all v2 --apply       # Set all to v2
    python .github/scripts/bump-schema-version.py zigpy                # Dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_JSON_PATH = REPO_ROOT / ".github" / "SCHEMA.json"

SCHEMAS = ("zigpy", "z2m", "markdown")

# Files that contain schema version references (besides SCHEMA.json itself)
TARGET_FILES = [
    "README.md",
    "CLAUDE.md",
]


# Suffix templates per schema: (filename_suffix, beta_filename_suffix)
SCHEMA_SUFFIXES = {
    "zigpy": ("_ota.json", "_ota_beta.json"),
    "z2m": ("_ota.json", "_ota_beta.json"),
    "markdown": (".md", "_beta.md"),
}


def generate_schema_entries(schema: str, version: str) -> dict[str, str]:
    """Generate SCHEMA.json entries for a single schema at the given version."""
    suffix, beta_suffix = SCHEMA_SUFFIXES[schema]
    prefix = f"{schema}_{version}"
    return {
        f"{schema}_version": version,
        f"{schema}_schema_key": prefix,
        f"{schema}_filename": f"{prefix}{suffix}",
        f"{schema}_beta_filename": f"{prefix}{beta_suffix}",
    }


def detect_current_version(schema: str) -> str:
    """Read current version for a specific schema from SCHEMA.json."""
    if not SCHEMA_JSON_PATH.exists():
        print("Error: SCHEMA.json file not found", file=sys.stderr)
        sys.exit(1)
    data = json.loads(SCHEMA_JSON_PATH.read_text())
    key = f"{schema}_version"
    if key not in data:
        print(f"Error: '{key}' not found in SCHEMA.json", file=sys.stderr)
        sys.exit(1)
    return data[key]


def validate_version(version: str) -> None:
    """Validate that a version string matches the expected format (v<number>)."""
    if not re.fullmatch(r"v(\d+)", version):
        print(
            f"Error: Invalid version '{version}' (expected format: v<number>)",
            file=sys.stderr,
        )
        sys.exit(1)


def increment_version(version: str) -> str:
    """Increment a version string like 'v1' to 'v2'."""
    validate_version(version)
    num = int(version[1:])
    return f"v{num + 1}"


def bump_file(
    path: Path,
    bumps: list[tuple[str, str, str]],
    *,
    apply: bool,
) -> int:
    """Replace schema version references in a single file for all bumps.

    Each bump is a (schema, old_version, new_version) tuple.
    Returns the total number of replacements made.
    """
    if not path.exists():
        print(f"  SKIP {path.relative_to(REPO_ROOT)} (file not found)")
        return 0

    content = path.read_text()
    total = 0

    for schema, old_ver, new_ver in bumps:
        old = f"{schema}_{old_ver}"
        new = f"{schema}_{new_ver}"
        # Use word boundary (\b) to avoid substring matches (e.g. v1 inside v10)
        pattern = re.compile(re.escape(old) + r"(?!\d)")
        content, count = pattern.subn(new, content)
        total += count

    rel = path.relative_to(REPO_ROOT)
    if total == 0:
        print(f"  SKIP {rel} (no matches)")
    else:
        print(f"  {'WRITE' if apply else 'WOULD'} {rel} ({total} replacements)")
        if apply:
            path.write_text(content)

    return total


def validate_no_remaining(bumps: list[tuple[str, str, str]]) -> list[str]:
    """Check that no target files still contain old version references."""
    issues = []

    for rel in TARGET_FILES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        content = path.read_text()
        for schema, old_ver, _new_ver in bumps:
            old = f"{schema}_{old_ver}"
            if re.search(re.escape(old) + r"(?!\d)", content):
                issues.append(f"  {rel} still contains '{old}'")

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bump OTA schema version across the repository."
    )
    parser.add_argument(
        "schema",
        choices=[*SCHEMAS, "all"],
        help="Which schema to bump (zigpy, z2m, markdown, or all)",
    )
    parser.add_argument(
        "new_version",
        nargs="?",
        default=None,
        help="New schema version (e.g. v2). Omit to auto-increment.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write changes (default is dry-run)",
    )
    args = parser.parse_args()

    if args.new_version:
        validate_version(args.new_version)

    schemas_to_bump = list(SCHEMAS) if args.schema == "all" else [args.schema]

    # Collect bumps: [(schema, old_version, new_version), ...]
    bumps: list[tuple[str, str, str]] = []
    for schema in schemas_to_bump:
        old = detect_current_version(schema)
        new = args.new_version or increment_version(old)
        if old == new:
            print(f"Skipping {schema}: already at {old}")
            continue
        bumps.append((schema, old, new))

    if not bumps:
        print("Nothing to bump.")
        sys.exit(2)

    # Write to GITHUB_OUTPUT if running in GitHub Actions
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            labels = []
            titles = []
            details = []
            for schema, old, new in bumps:
                f.write(f"{schema}_old_version={old}\n")
                f.write(f"{schema}_new_version={new}\n")
                labels.append(f"{schema}-{new}")
                titles.append(f"{schema} {new}")
                details.append(f"{schema} {old} \u2192 {new}")
            f.write(f"bump_label={'-'.join(labels)}\n")
            f.write(f"bump_title={', '.join(titles)}\n")
            f.write("bump_details<<EOF\n")
            f.write("Bumps the following OTA schema versions:\n\n")
            for detail in details:
                f.write(f"- {detail}\n")
            f.write("EOF\n")

    mode = "APPLY" if args.apply else "DRY-RUN"
    for schema, old, new in bumps:
        print(f"  {schema}: {old} -> {new}")
    print(f"  [{mode}]\n")

    # Update SCHEMA.json
    schema_data = json.loads(SCHEMA_JSON_PATH.read_text())
    for schema, _old, new in bumps:
        schema_data.update(generate_schema_entries(schema, new))
    action = "WRITE" if args.apply else "WOULD"
    print(f"  {action} .github/SCHEMA.json")
    if args.apply:
        SCHEMA_JSON_PATH.write_text(json.dumps(schema_data, indent=2) + "\n")

    # Update target files
    total = 0
    for rel in TARGET_FILES:
        path = REPO_ROOT / rel
        total += bump_file(path, bumps, apply=args.apply)

    print(f"\nTotal: {total} replacements across {len(TARGET_FILES)} target files")

    if args.apply:
        issues = validate_no_remaining(bumps)
        if issues:
            print("\nWarning: old version references still found:")
            for issue in issues:
                print(issue)
            sys.exit(1)
        else:
            print("\nValidation passed: no remaining old version references.")
    else:
        print("\nRe-run with --apply to write changes.")


if __name__ == "__main__":
    main()
