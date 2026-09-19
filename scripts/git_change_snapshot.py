"""Print a read-only Git change snapshot of a repository.

Reads staged, unstaged, untracked, renamed, copied, deleted, and
conflicted paths straight from ``git status --porcelain=v2 -z --branch``.

This script is read-only: it writes nothing except stdout and stderr, and
it never stages, commits, resets, checks out, cleans, fetches, or pushes.
Only the two read-only Git commands owned by
:mod:`packages.repository.git_changes` run, with ``--no-optional-locks``
so Git does not write its index refresh back to ``.git``.

Examples
--------
    .\\uv.exe run --no-cache python scripts\\git_change_snapshot.py
    .\\uv.exe run --no-cache python scripts\\git_change_snapshot.py --json .
    .\\uv.exe run --no-cache python scripts\\git_change_snapshot.py --json ..\\other-repo

Exit codes: ``0`` on success, ``1`` on an operational error (Git missing,
path outside a repository, command failure, malformed Git output).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.repository.git_changes import (  # noqa: E402
    GitChangeSnapshot,
    GitError,
    GitFileChange,
    capture_change_snapshot,
)

EXIT_OK = 0
EXIT_ERROR = 1

_RULE = "-" * 80


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="git_change_snapshot.py",
        description="Print a read-only, deterministic Git change snapshot.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="repository path to inspect (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the stable machine-readable document instead of a table",
    )
    return parser.parse_args(argv)


def _change_line(change: GitFileChange) -> str:
    """Render one change as ``status  path`` (with the rename source)."""
    if change.old_path is not None:
        return f"  {change.status.value:<13}{change.path}  <-  {change.old_path}"
    return f"  {change.status.value:<13}{change.path}"


def _section(lines: list[str], title: str, changes: tuple[GitFileChange, ...]) -> None:
    """Append one titled section, or nothing when the collection is empty."""
    if not changes:
        return
    lines.append(f"{title} ({len(changes)})")
    lines.extend(_change_line(change) for change in changes)


def format_table(snapshot: GitChangeSnapshot) -> str:
    """Render the snapshot as a readable table."""
    lines = ["=" * 80, "GIT CHANGE SNAPSHOT", _RULE]
    lines.append(f"repository : {snapshot.repository_root}")
    lines.append(
        f"branch     : {snapshot.branch or '(detached)'}"
        f"      head     : {snapshot.head_commit or '(no commits yet)'}"
    )
    if snapshot.upstream is None:
        upstream = "(no upstream configured)"
    else:
        ahead = "?" if snapshot.ahead is None else snapshot.ahead
        behind = "?" if snapshot.behind is None else snapshot.behind
        upstream = f"{snapshot.upstream}  (+{ahead} -{behind})"
    lines.append(f"upstream   : {upstream}")
    lines.append(f"state      : {'clean' if snapshot.is_clean else 'dirty'}")
    lines.append(_RULE)

    for title, changes in (
        ("STAGED", snapshot.staged),
        ("UNSTAGED", snapshot.unstaged),
        ("UNTRACKED", snapshot.untracked),
        ("RENAMED", snapshot.renamed),
        ("COPIED", snapshot.copied),
        ("DELETED", snapshot.deleted),
        ("CONFLICTED", snapshot.conflicted),
        ("IGNORED", snapshot.ignored),
    ):
        _section(lines, title, changes)

    if snapshot.is_clean:
        lines.append("nothing to commit, working tree clean")
    lines.append("=" * 80)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """Print a Git change snapshot and return the process exit code."""
    args = parse_args(argv)
    try:
        snapshot = capture_change_snapshot(Path(args.path))
    except GitError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except (FileNotFoundError, NotADirectoryError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR

    if args.json:
        print(json.dumps(snapshot.to_dict(), indent=2))
        return EXIT_OK

    print(format_table(snapshot))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
