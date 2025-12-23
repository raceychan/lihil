#!/usr/bin/env python3
"""Create the next sequential version/* branch."""
import argparse
import re
import subprocess
import sys
from typing import Iterable, Tuple

VERSION_PATTERN = re.compile(r"^(?:.+?/)?(version/(\d+)\.(\d+)\.(\d+))$")


def git_output(*args: str) -> str:
    """Return stdout from git while raising on non-zero exit."""
    result = subprocess.run(
        ["git", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def extract_versions(refs: Iterable[str]) -> Iterable[Tuple[int, int, int, str]]:
    for ref in refs:
        match = VERSION_PATTERN.match(ref)
        if not match:
            continue
        _, major, minor, patch = match.groups()
        yield (int(major), int(minor), int(patch), match.group(1))


def determine_next_branch() -> Tuple[str, str]:
    refs_raw = git_output(
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/heads/version",
        "refs/remotes/origin/version",
    )
    refs = [line for line in refs_raw.splitlines() if line.strip()]
    versions = list(extract_versions(refs))
    if not versions:
        sys.exit("No version/* branches found. Create the first one manually.")

    major, minor, patch, latest_branch = max(versions)
    next_branch = f"version/{major}.{minor}.{patch + 1}"
    return latest_branch, next_branch


def ensure_base_exists(base: str) -> None:
    try:
        git_output("rev-parse", "--verify", base)
    except subprocess.CalledProcessError as exc:
        sys.exit(f"Base reference '{base}' not found: {exc.stderr or exc}")


def run_git(*args: str) -> None:
    subprocess.run(["git", *args], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the next sequential version/* branch."
    )
    parser.add_argument(
        "--base",
        default="master",
        help="Branch or ref to base the new branch on (default: master).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the branch that would be created without running git switch.",
    )
    args = parser.parse_args()

    latest_branch, next_branch = determine_next_branch()
    ensure_base_exists(args.base)

    print(f"Latest version branch: {latest_branch}")
    print(f"Next version branch : {next_branch}")
    print(f"Base reference      : {args.base}")

    if args.dry_run:
        return

    run_git("switch", "-c", next_branch, args.base)
    print(f"Created and switched to {next_branch}.")


if __name__ == "__main__":
    main()
