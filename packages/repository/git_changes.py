"""Read-only Git change snapshot (Git Change Snapshot v1).

Produces a deterministic, structured view of what has changed in a Git
working tree - staged, unstaged, untracked, renamed, copied, deleted, and
conflicted paths - without touching the repository.

Ownership
---------

This module belongs to :mod:`packages.repository`, the package that owns
all repository analysis. No other package may shell out to Git.

Data flow
---------

.. code-block:: text

    git --no-optional-locks status --porcelain=v2 -z --branch
        |
        v
    parse_porcelain_v2()
        |
        v
    GitChangeSnapshot (immutable, deterministically ordered)

Read-only guarantees
--------------------

The Git surface is a single narrow subprocess boundary
(:func:`run_git_command`) that enforces an exact command allowlist. The
only vectors it will ever start are:

- ``git rev-parse --show-toplevel``
- ``git --no-optional-locks status --porcelain=v2 -z --branch
  --untracked-files=all``

Anything else - mutating commands, and even prefix, suffix or reordered
variants of an allowed command - raises :class:`GitUnsafeCommandError`
before a process is created. The boundary never uses the shell and never
builds a command string, so no staging, committing, resetting, checking
out, cleaning, fetching or pushing can happen here.

- ``--no-optional-locks`` keeps ``git status`` from writing a refreshed
  index back into ``.git``
- every invocation runs under a wall-clock budget
  (:data:`GIT_COMMAND_TIMEOUT_SECONDS`), so a stalled Git process cannot
  stall the caller with it
- the only output is the returned snapshot; nothing is persisted
- the allowlist lives in :func:`run_git_command` itself, not in its
  callers; a test that injects its own ``runner`` replaces the boundary
  instead of bypassing it

Usage
-----

.. code-block:: python

    from pathlib import Path

    from packages.repository.git_changes import capture_change_snapshot

    snapshot = capture_change_snapshot(Path("."))
    print(snapshot.branch, snapshot.head_commit)
    for change in snapshot.staged:
        print(change.status.value, change.path)

Command-line entry point: ``scripts/git_change_snapshot.py``.

Constraints
-----------

- Immutable models (``frozen=True``, ``slots=True``).
- Repository-relative paths, always with forward slashes.
- Deterministic ordering (every collection sorted by path, then old path).
- No diffs, no patch generation, no semantic analysis, no persistence.
- No gateway or context-ranking wiring in v1.
- No third-party dependency (porcelain v2 is parsed directly).
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final, NoReturn, Protocol

__all__ = [
    "GitChangeSnapshot",
    "GitChangeStatus",
    "GitCommandError",
    "GitCommandResult",
    "GitCommandRunner",
    "GitError",
    "GitPorcelainParseError",
    "GitTimeoutError",
    "GitUnavailableError",
    "GitUnsafeCommandError",
    "NotAGitRepositoryError",
    "capture_change_snapshot",
    "parse_porcelain_v2",
    "run_git_command",
]

#: Version tag of the dictionary layout produced by
#: :meth:`GitChangeSnapshot.to_dict`.
SCHEMA_VERSION: Final[int] = 1

_GIT_EXECUTABLE: Final[str] = "git"

#: Hard wall-clock budget for one read-only Git invocation. ``git status`` can
#: stall - an index lock, an enormous working tree, an unreachable network
#: share - and a stalled Git must not be able to stall anything else, so the
#: process boundary owns the deadline instead of every caller.
GIT_COMMAND_TIMEOUT_SECONDS: Final[float] = 30.0

#: The two read-only Git commands this module is built around; the allowlist
#: below is what actually enforces them at the subprocess boundary.
_ROOT_ARGS: Final[tuple[str, ...]] = ("rev-parse", "--show-toplevel")
_STATUS_ARGS: Final[tuple[str, ...]] = (
    "--no-optional-locks",
    "status",
    "--porcelain=v2",
    "-z",
    "--branch",
    "--untracked-files=all",
)

#: The complete read-only Git surface, enforced as an exact allowlist by
#: :func:`run_git_command`. Vectors are matched in full, so a prefix, a
#: suffix, a reordering, or an extra flag of an allowed command is refused.
_ALLOWED_COMMAND_VECTORS: Final[tuple[tuple[str, ...], ...]] = (_ROOT_ARGS, _STATUS_ARGS)
_ALLOWED_COMMANDS: Final[frozenset[tuple[str, ...]]] = frozenset(_ALLOWED_COMMAND_VECTORS)

#: Porcelain v2 branch-header sentinels.
_INITIAL_OID: Final[str] = "(initial)"
_DETACHED_HEAD: Final[str] = "(detached)"

#: Status letters understood in the ``<XY>`` field of porcelain v2.
_KNOWN_LETTERS: Final[frozenset[str]] = frozenset(".MADRCTU?!")

#: Letters that mean "this column records no change for this path".
_NON_CHANGE_LETTERS: Final[frozenset[str]] = frozenset({".", "?", "!"})

#: Substrings that identify a "no working tree" failure in Git messages.
_NOT_A_REPOSITORY_MARKERS: Final[tuple[str, ...]] = (
    "not a git repository",
    "must be run in a work tree",
    "cannot chdir",
)

_AHEAD_BEHIND_PATTERN: Final[re.Pattern[str]] = re.compile(r"\+(\d+) -(\d+)")
_OBJECT_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{7,64}")
_NUL_BYTE: Final[bytes] = b"\x00"


class GitChangeStatus(str, Enum):
    """Change classification of a single repository path.

    Derived from the porcelain v2 ``<XY>`` field, where ``X`` compares
    HEAD with the index and ``Y`` compares the index with the working
    tree.

    Attributes:
        ADDED: Path added to the index (``A``).
        MODIFIED: Path with content or mode differences (``M``).
        DELETED: Path removed from the index or from the working tree (``D``).
        RENAMED: Path recorded as a rename (``R``).
        COPIED: Path recorded as a copy (``C``).
        TYPE_CHANGED: Path type changed, for example file to symlink (``T``).
        UNMERGED: Path is conflicted and carries more than one index stage.
        UNTRACKED: Path exists in the working tree but not in the index.
        IGNORED: Path is ignored (only reported when Git emits ``!`` rows).
        UNKNOWN: A status letter this parser does not recognise.
    """

    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    TYPE_CHANGED = "type_changed"
    UNMERGED = "unmerged"
    UNTRACKED = "untracked"
    IGNORED = "ignored"
    UNKNOWN = "unknown"


_LETTER_STATUS: Final[Mapping[str, GitChangeStatus]] = {
    "A": GitChangeStatus.ADDED,
    "M": GitChangeStatus.MODIFIED,
    "D": GitChangeStatus.DELETED,
    "R": GitChangeStatus.RENAMED,
    "C": GitChangeStatus.COPIED,
    "T": GitChangeStatus.TYPE_CHANGED,
    "U": GitChangeStatus.UNMERGED,
    "?": GitChangeStatus.UNTRACKED,
    "!": GitChangeStatus.IGNORED,
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GitError(RuntimeError):
    """Base class for every failure raised by this module."""


class GitUnavailableError(GitError):
    """Raised when the ``git`` executable cannot be found or started."""


class NotAGitRepositoryError(GitError):
    """Raised when the requested path is not inside a Git working tree."""


class GitCommandError(GitError):
    """Raised when a read-only Git command exits with a nonzero status.

    Attributes:
        command: The full argument vector passed to the Git executable.
        returncode: The exit code Git returned.
        stderr: The decoded standard error output of the command.
    """

    def __init__(
        self,
        message: str,
        *,
        command: Sequence[str],
        returncode: int,
        stderr: str,
    ) -> None:
        """Store the failing command alongside the human-readable message."""
        joined = " ".join(command)
        super().__init__(f"{message} [git {joined}] exit={returncode} stderr={stderr.strip()!r}")
        self.command = tuple(command)
        self.returncode = returncode
        self.stderr = stderr


class GitPorcelainParseError(GitError):
    """Raised when porcelain v2 output does not match the documented format."""


class GitTimeoutError(GitError):
    """Raised when a read-only Git command exceeds its wall-clock budget.

    A ``git status`` can stall on an index lock, an enormous working tree or an
    unreachable network share. Every caller that reaches Git from a long-lived
    process depends on that stall being finite, so the subprocess boundary -
    not the callers - owns the deadline.

    Attributes:
        command: The full argument vector passed to the Git executable.
        timeout_seconds: The budget that expired.
    """

    def __init__(
        self,
        message: str,
        *,
        command: Sequence[str],
        timeout_seconds: float,
    ) -> None:
        """Store the timed-out command alongside the human-readable message."""
        joined = " ".join(command)
        super().__init__(f"{message} [git {joined}] timed out after {timeout_seconds:g}s")
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds


class GitUnsafeCommandError(GitError):
    """Raised when a command outside the read-only allowlist is requested.

    Nothing runs in this case: :func:`run_git_command` rejects the vector
    before :func:`subprocess.run` is reached, so the repository cannot be
    affected.

    Attributes:
        command: The rejected argument vector.
        allowed: Every argument vector this module may run.
    """

    def __init__(
        self,
        message: str,
        *,
        command: Sequence[str],
        allowed: Sequence[tuple[str, ...]] = _ALLOWED_COMMAND_VECTORS,
    ) -> None:
        """Store the rejected vector alongside the human-readable message."""
        rejected = " ".join(command)
        permitted = " and ".join(f"git {' '.join(args)}" for args in allowed)
        super().__init__(
            f"{message} [rejected git {rejected!r}]; "
            f"the read-only allowlist permits only: {permitted}"
        )
        self.command = tuple(command)
        self.allowed = tuple(allowed)


# ---------------------------------------------------------------------------
# Subprocess boundary
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GitCommandResult:
    """Outcome of one read-only Git invocation.

    Attributes:
        command: The argument vector that was executed, excluding the
            executable itself.
        returncode: Process exit code.
        stdout: Raw standard output; paths are decoded by the caller
            because porcelain ``-z`` output is byte oriented.
        stderr: Decoded standard error, for error messages only.
    """

    command: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: str


class GitCommandRunner(Protocol):
    """Callable shape of the Git subprocess boundary.

    Tests inject a stand-in to feed recorded porcelain output without
    touching a repository. Injecting a runner replaces the boundary, so it
    also replaces the read-only allowlist check that lives inside
    :func:`run_git_command`; the production path never skips it.
    """

    def __call__(self, command: Sequence[str], cwd: Path) -> GitCommandResult: ...


def run_git_command(
    command: Sequence[str],
    cwd: Path,
    *,
    timeout_seconds: float = GIT_COMMAND_TIMEOUT_SECONDS,
) -> GitCommandResult:
    """Run one allowlisted read-only Git command and return its raw result.

    This is the only place in the platform that starts a Git process, and
    the only gate through which a Git command line can reach Git. The
    argument vector is matched against :data:`_ALLOWED_COMMANDS` in full
    before anything is started, and the process is given a hard wall-clock
    budget so no caller can inherit an endless ``git status``.

    Args:
        command: Git arguments, exactly one of ``_ROOT_ARGS`` or
            ``_STATUS_ARGS``; any other vector is rejected.
        cwd: Directory Git should run in.
        timeout_seconds: How long the process may run before it is killed and
            :class:`GitTimeoutError` is raised.

    Returns:
        A :class:`GitCommandResult`; no exception is raised for a
        nonzero exit code, so callers can classify the failure.

    Raises:
        GitUnsafeCommandError: If ``command`` is not one of the two
            read-only vectors, without a process having been started.
        GitUnavailableError: If the ``git`` executable is missing or
            cannot be started.
        GitTimeoutError: If the process outlives ``timeout_seconds``.
    """
    args = tuple(command)
    if args not in _ALLOWED_COMMANDS:
        raise GitUnsafeCommandError(
            "refusing to run a Git command outside the read-only allowlist",
            command=args,
        )

    try:
        completed = subprocess.run(
            [_GIT_EXECUTABLE, *args],
            cwd=str(cwd),
            capture_output=True,
            shell=False,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as error:
        raise GitUnavailableError(
            f"Git executable {_GIT_EXECUTABLE!r} was not found on PATH"
        ) from error
    except OSError as error:
        raise GitUnavailableError(
            f"Could not start Git executable {_GIT_EXECUTABLE!r}: {error}"
        ) from error
    except subprocess.TimeoutExpired as error:
        raise GitTimeoutError(
            "read-only Git command exceeded its time budget",
            command=args,
            timeout_seconds=float(error.timeout or timeout_seconds),
        ) from error

    return GitCommandResult(
        command=tuple(command),
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=_decode(completed.stderr),
    )


def _decode(raw: bytes) -> str:
    """Decode Git output without ever failing on odd bytes.

    Porcelain ``-z`` records are UTF-8 and unquoted. Bytes that are not
    valid UTF-8 become ``U+FFFD`` so that a single exotic filename can
    never abort a whole snapshot; JSON output then stays escapable.
    """
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GitFileChange:
    """One repository-relative path reported by Git.

    Attributes:
        path: Repository-relative path using forward slashes. For a
            rename or a copy this is the target (new) path.
        status: Classification derived from the porcelain ``<XY>`` field.
        index_status: The ``X`` letter, comparing HEAD with the index.
            ``"."`` means nothing is staged for this path; ``"?"`` and
            ``"!"`` mark untracked and ignored rows.
        worktree_status: The ``Y`` letter, comparing the index with the
            working tree. ``"."`` means the working tree matches the index.
        old_path: Source path of a rename or copy, ``None`` otherwise.
    """

    path: str
    status: GitChangeStatus
    index_status: str
    worktree_status: str
    old_path: str | None = None

    @property
    def is_staged(self) -> bool:
        """Report whether this path differs from HEAD in the index."""
        return self.index_status not in _NON_CHANGE_LETTERS

    @property
    def is_unstaged(self) -> bool:
        """Report whether this path differs from the index in the worktree."""
        return self.worktree_status not in _NON_CHANGE_LETTERS

    @property
    def sort_key(self) -> tuple[str, str]:
        """Deterministic ordering key: path first, then rename source."""
        return (self.path, self.old_path or "")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable view with stable key ordering."""
        return {
            "path": self.path,
            "old_path": self.old_path,
            "status": self.status.value,
            "index_status": self.index_status,
            "worktree_status": self.worktree_status,
        }


@dataclass(frozen=True, slots=True)
class GitChangeSnapshot:
    """Complete read-only picture of one Git working tree at one instant.

    Every collection is sorted by :attr:`GitFileChange.sort_key`, so two
    snapshots of an unchanged repository are equal and serialize to the
    same JSON text.

    The collections overlap by design: a path that is both staged and
    modified appears in both :attr:`staged` and :attr:`unstaged`; an
    index rename appears in both :attr:`staged` and :attr:`renamed`; a
    staged deletion appears in both :attr:`staged` and :attr:`deleted`.

    Attributes:
        repository_root: Absolute root of the Git working tree.
        branch: Current branch name, or ``None`` on a detached HEAD.
        head_commit: Object name HEAD points at, or ``None`` on an unborn
            branch, where no commit exists yet.
        upstream: Configured upstream branch, or ``None``.
        ahead: Commits ahead of the upstream, or ``None`` when no
            upstream is configured or its tip is not known locally.
        behind: Commits behind the upstream, or ``None``.
        staged: Paths whose index differs from HEAD.
        unstaged: Paths whose working tree differs from the index.
        untracked: Paths present in the working tree but not in the index.
        renamed: Index renames, carrying both ``old_path`` and ``path``.
        copied: Index copies, carrying both ``old_path`` and ``path``.
        deleted: Paths deleted from the index or from the working tree.
        conflicted: Unmerged paths. They are kept out of :attr:`staged`
            and :attr:`unstaged` because Git records them as several index
            stages, not as staged or unstaged content.
        ignored: Ignored paths. Always empty here, because the underlying
            status command does not request ignored rows.
    """

    repository_root: Path
    branch: str | None = None
    head_commit: str | None = None
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None
    staged: tuple[GitFileChange, ...] = ()
    unstaged: tuple[GitFileChange, ...] = ()
    untracked: tuple[GitFileChange, ...] = ()
    renamed: tuple[GitFileChange, ...] = ()
    copied: tuple[GitFileChange, ...] = ()
    deleted: tuple[GitFileChange, ...] = ()
    conflicted: tuple[GitFileChange, ...] = ()
    ignored: tuple[GitFileChange, ...] = ()

    @property
    def is_clean(self) -> bool:
        """Report whether the working tree holds no changes at all."""
        return not self.is_dirty

    @property
    def is_dirty(self) -> bool:
        """Report whether anything is staged, unstaged, untracked, or conflicted."""
        return bool(
            self.staged
            or self.unstaged
            or self.untracked
            or self.renamed
            or self.copied
            or self.deleted
            or self.conflicted
        )

    @property
    def counts(self) -> dict[str, int]:
        """Return the size of every change collection."""
        return {
            "staged": len(self.staged),
            "unstaged": len(self.unstaged),
            "untracked": len(self.untracked),
            "renamed": len(self.renamed),
            "copied": len(self.copied),
            "deleted": len(self.deleted),
            "conflicted": len(self.conflicted),
            "ignored": len(self.ignored),
        }

    def to_dict(self) -> dict[str, Any]:
        """Return the stable machine-readable document used by ``--json``."""
        return {
            "schema_version": SCHEMA_VERSION,
            "repository_root": str(self.repository_root),
            "branch": self.branch,
            "head_commit": self.head_commit,
            "upstream": self.upstream,
            "ahead": self.ahead,
            "behind": self.behind,
            "clean": self.is_clean,
            "staged": [change.to_dict() for change in self.staged],
            "unstaged": [change.to_dict() for change in self.unstaged],
            "untracked": [change.to_dict() for change in self.untracked],
            "renamed": [change.to_dict() for change in self.renamed],
            "copied": [change.to_dict() for change in self.copied],
            "deleted": [change.to_dict() for change in self.deleted],
            "conflicted": [change.to_dict() for change in self.conflicted],
            "ignored": [change.to_dict() for change in self.ignored],
            "counts": self.counts,
        }



# ---------------------------------------------------------------------------
# Porcelain v2 parser
# ---------------------------------------------------------------------------

#: Field counts of each porcelain v2 record kind, including the kind
#: character itself, plus the index of the path field.
_TRACKED_KINDS: Final[Mapping[str, tuple[int, int]]] = {
    "1": (9, 8),
    "2": (10, 9),
    "u": (11, 10),
}


def parse_porcelain_v2(output: bytes, *, repository_root: Path) -> GitChangeSnapshot:
    """Turn raw porcelain v2 ``-z`` bytes into a :class:`GitChangeSnapshot`.

    Args:
        output: Untouched standard output of
            ``git status --porcelain=v2 -z --branch``.
        repository_root: Root the relative paths belong to.

    Returns:
        A deterministic snapshot with every collection sorted by path.

    Raises:
        GitPorcelainParseError: If any record deviates from the
            documented porcelain v2 layout.
    """
    tokens = _split_records(output)
    branch: str | None = None
    head_commit: str | None = None
    upstream: str | None = None
    ahead: int | None = None
    behind: int | None = None
    changes: list[GitFileChange] = []

    position = 0
    while position < len(tokens):
        record = tokens[position]
        position += 1
        if not record:
            raise GitPorcelainParseError("porcelain v2 stream contains an empty record")

        if record.startswith("#"):
            key, _, value = record[1:].strip().partition(" ")
            if key == "branch.oid":
                head_commit = _parse_branch_oid(record, value)
            elif key == "branch.head":
                branch = _parse_branch_head(record, value)
            elif key == "branch.upstream":
                upstream = _parse_required_value(record, value)
            elif key == "branch.ab":
                ahead, behind = _parse_ahead_behind(record, value)
            continue  # any other header is optional and ignored by design

        change, position = _parse_change_record(tokens, position, record)
        changes.append(change)

    return GitChangeSnapshot(
        repository_root=repository_root,
        branch=branch,
        head_commit=head_commit,
        upstream=upstream,
        ahead=ahead,
        behind=behind,
        **_group_changes(changes),
    )


def _split_records(output: bytes) -> list[str]:
    """Split NUL-terminated porcelain output into decoded records.

    Args:
        output: Raw bytes of the status command.

    Returns:
        The records in stream order, without their NUL terminators.

    Raises:
        GitPorcelainParseError: If the stream is empty.
    """
    if not output:
        raise GitPorcelainParseError("git produced no porcelain v2 output")

    raw_tokens = output.split(_NUL_BYTE)
    if raw_tokens and raw_tokens[-1] == b"":
        raw_tokens.pop()  # porcelain terminates the final record with a NUL
    if not raw_tokens:
        raise GitPorcelainParseError("git produced no porcelain v2 records")

    return [_decode(token) for token in raw_tokens]


def _parse_change_record(
    tokens: Sequence[str],
    position: int,
    record: str,
) -> tuple[GitFileChange, int]:
    """Parse one non-header record, consuming a rename source when present.

    Args:
        tokens: All decoded records of the stream.
        position: Index of the record after ``record``.
        record: The record to parse.

    Returns:
        The parsed change and the index of the next unread record.

    Raises:
        GitPorcelainParseError: If the record is malformed or refers to a
            rename source that the stream does not carry.
    """
    kind = record[0]

    if kind in ("?", "!"):
        fields = record.split(" ", 1)
        if len(fields) != 2 or not fields[1]:
            raise GitPorcelainParseError(
                f"porcelain v2 {kind!r} record needs a path: {record!r}"
            )
        status = (
            GitChangeStatus.UNTRACKED if kind == "?" else GitChangeStatus.IGNORED
        )
        return (
            GitFileChange(
                path=fields[1],
                status=status,
                index_status=kind,
                worktree_status=kind,
            ),
            position,
        )

    layout = _TRACKED_KINDS.get(kind)
    if layout is None:
        raise GitPorcelainParseError(f"unknown porcelain v2 record kind {kind!r}: {record!r}")

    field_count, path_index = layout
    fields = record.split(" ", field_count - 1)
    if len(fields) != field_count or any(not field for field in fields):
        raise GitPorcelainParseError(
            f"porcelain v2 {kind!r} record needs {field_count} fields: {record!r}"
        )

    index_status, worktree_status = _parse_status_letters(kind, fields[1], record)
    old_path: str | None = None
    if kind == "2":
        if position >= len(tokens) or not tokens[position]:
            raise GitPorcelainParseError(
                f"porcelain v2 rename/copy record is missing its source path: {record!r}"
            )
        old_path = tokens[position]
        position += 1

    return (
        GitFileChange(
            path=fields[path_index],
            status=_resolve_status(kind, index_status, worktree_status),
            index_status=index_status,
            worktree_status=worktree_status,
            old_path=old_path,
        ),
        position,
    )


def _parse_status_letters(kind: str, combined: str, record: str) -> tuple[str, str]:
    """Split and validate the ``<XY>`` field of a tracked record."""
    if len(combined) != 2 or any(letter not in _KNOWN_LETTERS for letter in combined):
        raise GitPorcelainParseError(
            f"invalid porcelain v2 status field {combined!r}: {record!r}"
        )
    return combined[0], combined[1]


def _resolve_status(kind: str, index_status: str, worktree_status: str) -> GitChangeStatus:
    """Classify one record from its kind and its ``X``/``Y`` letters.

    Conflict letters win over content letters, because an unmerged path is
    reported by Git as several index stages rather than as content that
    could be committed as is.
    """
    if kind == "u":
        return GitChangeStatus.UNMERGED
    letters = (index_status, worktree_status)
    if "U" in letters:
        return GitChangeStatus.UNMERGED
    for letter in letters:
        status = _LETTER_STATUS.get(letter)
        if status is not None:
            return status
    return GitChangeStatus.UNKNOWN


def _group_changes(changes: Sequence[GitFileChange]) -> dict[str, tuple[GitFileChange, ...]]:
    """Partition parsed changes into the snapshot's ordered collections."""

    def ordered(keep: Callable[[GitFileChange], bool]) -> tuple[GitFileChange, ...]:
        return tuple(sorted((change for change in changes if keep(change)), key=_sort_key))

    def not_conflicted(change: GitFileChange) -> bool:
        return change.status is not GitChangeStatus.UNMERGED

    return {
        "staged": ordered(
            lambda change: not_conflicted(change) and change.is_staged
        ),
        "unstaged": ordered(
            lambda change: not_conflicted(change) and change.is_unstaged
        ),
        "untracked": ordered(lambda change: change.status is GitChangeStatus.UNTRACKED),
        "renamed": ordered(lambda change: change.status is GitChangeStatus.RENAMED),
        "copied": ordered(lambda change: change.status is GitChangeStatus.COPIED),
        "deleted": ordered(
            lambda change: not_conflicted(change)
            and "D" in (change.index_status, change.worktree_status)
        ),
        "conflicted": ordered(lambda change: change.status is GitChangeStatus.UNMERGED),
        "ignored": ordered(lambda change: change.status is GitChangeStatus.IGNORED),
    }


def _sort_key(change: GitFileChange) -> tuple[str, str]:
    """Order changes by path, then by rename source."""
    return change.sort_key


def _parse_branch_oid(record: str, value: str) -> str | None:
    """Read the ``# branch.oid`` header, mapping ``(initial)`` to ``None``."""
    if not value:
        raise GitPorcelainParseError(f"porcelain v2 branch.oid header has no value: {record!r}")
    if value == _INITIAL_OID:
        return None
    if _OBJECT_NAME_PATTERN.fullmatch(value) is None:
        raise GitPorcelainParseError(f"porcelain v2 branch.oid header is malformed: {record!r}")
    return value


def _parse_branch_head(record: str, value: str) -> str | None:
    """Read the ``# branch.head`` header, mapping ``(detached)`` to ``None``."""
    if not value:
        raise GitPorcelainParseError(f"porcelain v2 branch.head header has no value: {record!r}")
    if value == _DETACHED_HEAD:
        return None
    return value


def _parse_required_value(record: str, value: str) -> str:
    """Return a header value that must not be empty."""
    if not value:
        raise GitPorcelainParseError(f"porcelain v2 header has no value: {record!r}")
    return value


def _parse_ahead_behind(record: str, value: str) -> tuple[int, int]:
    """Read the ``# branch.ab +<ahead> -<behind>`` header."""
    match = _AHEAD_BEHIND_PATTERN.fullmatch(value)
    if match is None:
        raise GitPorcelainParseError(f"porcelain v2 branch.ab header is malformed: {record!r}")
    return int(match.group(1)), int(match.group(2))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def capture_change_snapshot(
    path: Path | None = None,
    *,
    runner: GitCommandRunner = run_git_command,
) -> GitChangeSnapshot:
    """Capture a read-only change snapshot of a Git working tree.

    Two read-only Git commands run: ``rev-parse --show-toplevel`` to
    locate the repository root, then ``status --porcelain=v2 -z --branch``
    started from that root so every reported path is repository relative.
    ``--no-optional-locks`` keeps Git from writing its index refresh back
    to disk, so taking a snapshot does not mutate the repository.

    Args:
        path: Directory inside a Git working tree. Defaults to the
            current working directory.
        runner: Subprocess boundary override, used by tests to feed
            recorded porcelain output.

    Returns:
        A deterministic :class:`GitChangeSnapshot`.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        NotADirectoryError: If ``path`` is not a directory.
        GitUnavailableError: If the Git executable is missing or fails
            to start.
        NotAGitRepositoryError: If ``path`` is not inside a Git working
            tree, including bare repositories.
        GitCommandError: If a read-only Git command exits nonzero.
        GitPorcelainParseError: If Git's output is not valid porcelain v2.
    """
    start = Path.cwd() if path is None else Path(path)
    if not start.exists():
        raise FileNotFoundError(f"Path does not exist: {start}")
    if not start.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {start}")

    root = _resolve_repository_root(start, runner)
    result = runner(_STATUS_ARGS, root)
    if result.returncode != 0:
        _raise_command_error("could not read the repository status", result)
    return parse_porcelain_v2(result.stdout, repository_root=root)


def _resolve_repository_root(path: Path, runner: GitCommandRunner) -> Path:
    """Return the working-tree root that contains ``path``.

    Args:
        path: Directory to start Git's own discovery from.
        runner: The subprocess boundary to use.

    Returns:
        The absolute repository root Git reports.

    Raises:
        NotAGitRepositoryError: If Git reports no working tree.
        GitCommandError: If the command fails for another reason.
        GitPorcelainParseError: If Git reports an empty root.
    """
    result = runner(_ROOT_ARGS, path)
    if result.returncode != 0:
        _raise_command_error("could not resolve the repository root", result)

    toplevel = _decode(result.stdout).strip()
    if not toplevel:
        raise GitPorcelainParseError(f"git reported an empty repository root for {path}")
    return Path(toplevel)


def _raise_command_error(message: str, result: GitCommandResult) -> NoReturn:
    """Turn a failed read-only Git command into a typed error.

    Args:
        message: What the caller was trying to do.
        result: The failed command result.

    Raises:
        NotAGitRepositoryError: When Git says there is no working tree.
        GitCommandError: For every other nonzero exit.
    """
    lowered = result.stderr.lower()
    if any(marker in lowered for marker in _NOT_A_REPOSITORY_MARKERS):
        raise NotAGitRepositoryError(
            f"{message}: the path is not inside a Git working tree "
            f"[git exit={result.returncode}] {result.stderr.strip()}"
        )
    raise GitCommandError(
        message,
        command=result.command,
        returncode=result.returncode,
        stderr=result.stderr,
    )
