"""Change-aware repository-context ranking signal.

Turns the read-only Git change snapshot owned by
:mod:`packages.repository.git_changes` into the bounded set of *index module
keys* that repository-context ranking matches symbols against:

.. code-block:: text

    capture_change_snapshot(root)          # git status, read-only
        |
        v
    changed_module_paths(snapshot, index_root)  # pure path derivation
        |
        v
    frozenset[str]  ->  RankingEngine(changed_modules=...)

Ownership and read-only guarantees
----------------------------------

This module never starts a process and never imports ``subprocess``. The only
Git vectors it can ever cause to run are the two allowlisted read-only commands
inside :func:`packages.repository.git_changes.run_git_command`, each under its
own wall-clock budget. Nothing is persisted, and only paths are handled - never
file contents - so the signal cannot leak repository content through logs or
diagnostics. TTL refreshing is deliberately not a concern of this module:
:mod:`packages.repository.changed_files_refresh` runs it on a worker thread, so
no request path ever waits on Git.

Path translation
----------------

Repository index keys are produced by the Python AST extractor as root
relative, forward slashed paths with the ``.py`` suffix removed
(``packages/context/builder``). Git paths are working-tree relative and keep
the suffix, so every path is re-based onto the directory the index was built
from before it is compared. Both roots are resolved with ``realpath`` first:
Git reports the working tree it discovered while the index root comes from
configuration, and on Windows the same directory can be reached through a
symlink, a junction, a ``subst`` drive or an 8.3 short name. Without resolving
those, every path would look outside the root and the signal would switch
itself off in silence - so the count of such paths is exposed as a diagnostic.
Non-Python paths cannot influence ranking because the index holds Python
modules only.

Changes that do not name a file an agent can still be editing are dropped:

- deletions never promote, because their indexed symbols are stale
- rename and copy sources promote as well as their targets, because the index
  is built once at gateway startup and may still hold the pre-rename module
- conflicted paths promote: they are being edited right now
- ignored paths never promote (the snapshot reports none)

Constraints
-----------

- Bounded output: at most :data:`MAX_CHANGED_PATHS` keys.
- No gateway, pipeline, or context imports - this is repository-side only.
- Snapshot failures are recorded as counters, never raised or logged with
  filesystem paths.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

from packages.repository.git_changes import (
    GitChangeSnapshot,
    GitChangeStatus,
    GitFileChange,
    capture_change_snapshot,
)

__all__ = [
    "MAX_CHANGED_PATHS",
    "ChangedFilesSignal",
    "ChangedModuleSource",
    "ChangedPathDerivation",
    "SnapshotCapturer",
    "changed_module_paths",
    "derive_changed_module_paths",
]

#: Upper bound on how many changed module keys take part in ranking. A huge
#: dirty tree must not be able to spread the bonus over the whole index.
MAX_CHANGED_PATHS: Final[int] = 200

#: Signature of the read-only snapshot capture used by the signal, injectable
#: so tests can feed recorded snapshots without touching Git.
SnapshotCapturer = Callable[[Path], GitChangeSnapshot]


class ChangedModuleSource(Protocol):
    """Anything that can supply index module keys of locally changed files."""

    def module_paths(self) -> frozenset[str]:
        """Return the bounded set of changed index module keys."""
        ...


def changed_module_paths(
    snapshot: GitChangeSnapshot,
    *,
    index_root: Path | None = None,
    limit: int = MAX_CHANGED_PATHS,
) -> frozenset[str]:
    """Derive the bounded set of index module keys a snapshot implies.

    Args:
        snapshot: A deterministic snapshot from
            :func:`packages.repository.git_changes.capture_change_snapshot`.
        index_root: Directory the repository index was built from. ``None``
            means the snapshot's own repository root.
        limit: Maximum number of keys to return. When the tree holds more,
            the lexicographically smallest keys are kept so the result never
            depends on Git's per-collection ordering.

    Returns:
        A frozen set of index module keys - empty for a clean tree, for a
        tree whose changes are all deletions, and for changes that lie
        outside ``index_root``.  Use :func:`derive_changed_module_paths` to
        learn how many paths were dropped.
    """
    return derive_changed_module_paths(
        snapshot,
        index_root=index_root,
        limit=limit,
    ).keys


@dataclass(frozen=True, slots=True)
class ChangedPathDerivation:
    """Module keys plus the counts of the paths that could not become keys.

    Attributes:
        keys: The bounded set of index module keys.
        outside_root_count: How many changed paths resolved to a location
            outside the index root. Only the count is kept - a path is a
            filesystem location and must not reach a log line.
    """

    keys: frozenset[str]
    outside_root_count: int = 0


def derive_changed_module_paths(
    snapshot: GitChangeSnapshot,
    *,
    index_root: Path | None = None,
    limit: int = MAX_CHANGED_PATHS,
) -> ChangedPathDerivation:
    """Derive module keys and report how many paths had to be dropped.

    Args:
        snapshot: A deterministic snapshot from
            :func:`packages.repository.git_changes.capture_change_snapshot`.
        index_root: Directory the repository index was built from. ``None``
            means the snapshot's own repository root.
        limit: Maximum number of keys to return.

    Returns:
        A :class:`ChangedPathDerivation`; keys are empty for a clean tree, for
        a tree whose changes are all deletions, and for changes that lie
        outside ``index_root``.
    """
    base = _canonical_root(snapshot.repository_root)
    target = _canonical_root(index_root) if index_root is not None else base
    keys: set[str] = set()
    outside_root = 0
    for change in _promotable_changes(snapshot):
        for raw_path in _paths_of(change):
            key, fell_outside = _module_key(raw_path, base=base, target=target)
            if key is not None:
                keys.add(key)
            elif fell_outside:
                outside_root += 1
    if 0 <= limit < len(keys):
        return ChangedPathDerivation(frozenset(sorted(keys)[:limit]), outside_root)
    return ChangedPathDerivation(frozenset(keys), outside_root)


def _canonical_root(path: Path | str) -> str:
    """Return the symlink-free form of a directory root.

    Git reports the working tree it discovered, while the index root comes from
    configuration. Either side can reach the same directory through a symlink,
    a junction, a ``subst`` drive or an 8.3 short name, and comparing those
    spellings textually drops every path - the feature would switch itself off
    without a trace. Resolving both sides first compares directories instead of
    strings.

    Args:
        path: A root that may or may not exist; resolution is best effort.

    Returns:
        The canonical absolute form, or the absolute form when the filesystem
        refuses to resolve the path.
    """
    text = str(path)
    try:
        return os.path.realpath(text)
    except OSError:  # unreadable mount point, invalid drive, loop
        return os.path.abspath(text)


def _module_key(
    raw_path: str,
    *,
    base: str,
    target: str,
) -> tuple[str | None, bool]:
    """Translate one working-tree relative Git path into an index module key.

    Args:
        raw_path: Repository-relative path from a Git change record.
        base: Canonical absolute Git working-tree root the path is relative to.
        target: Canonical absolute directory the index keys are relative to.

    Returns:
        A ``(key, fell_outside_root)`` pair. The key is ``None`` when the path
        is malformed, lies outside ``target``, or is not a Python file; only
        the "outside the root" case is reported as a second value, because it
        is the one that silently disables the feature.
    """
    cleaned = raw_path.replace("\\", "/").strip()
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if not cleaned or cleaned.startswith("/") or "\x00" in cleaned:
        return None, False
    if ":" in cleaned[:3]:  # drive or alternate-data-stream prefix - never repo relative
        return None, False
    absolute = os.path.join(base, *cleaned.split("/"))
    try:
        relative = os.path.relpath(absolute, target).replace("\\", "/")
    except ValueError:  # different drives on Windows - no shared mapping
        return None, True
    if relative == "." or relative.startswith("../"):
        return None, True
    if not relative.lower().endswith(".py"):
        return None, False
    return relative[:-3] or None, False


def _promotable_changes(snapshot: GitChangeSnapshot) -> list[GitFileChange]:
    """Return the distinct changed records that may earn the bonus.

    The snapshot's collections overlap by design - a staged rename appears in
    both ``staged`` and ``renamed`` - so records are deduplicated by their
    deterministic sort key and deletions are dropped.
    """
    groups: Iterable[tuple[GitFileChange, ...]] = (
        snapshot.staged,
        snapshot.unstaged,
        snapshot.untracked,
        snapshot.renamed,
        snapshot.copied,
        snapshot.conflicted,
    )
    distinct: dict[tuple[str, str], GitFileChange] = {}
    for group in groups:
        for change in group:
            if change.status is GitChangeStatus.DELETED:
                continue
            distinct[change.sort_key] = change
    return sorted(distinct.values(), key=lambda change: change.sort_key)


def _paths_of(change: GitFileChange) -> tuple[str, ...]:
    """Return the module paths one change record can promote."""
    if change.status in (GitChangeStatus.RENAMED, GitChangeStatus.COPIED):
        return (change.path, change.old_path) if change.old_path else (change.path,)
    return (change.path,)


class ChangedFilesSignal(ChangedModuleSource):
    """Cached, TTL-bounded provider of changed index module keys.

    Capture is meant to happen outside the request path: the gateway builds
    the signal during application lifespan startup and calls :meth:`prime`
    there, so :meth:`module_paths` - the only method the pipeline stage uses -
    is a frozen-set read for the whole lifetime of the process.  When
    ``ttl_seconds`` is greater than zero a background
    :class:`~packages.repository.changed_files_refresh.ChangedFilesRefresher`
    calls :meth:`refresh` on a worker thread; with the default TTL of ``0``
    even that is skipped, and no request can ever reach Git.

    Failures never propagate. A snapshot that raises - missing path, no Git
    metadata, a nonzero exit, a timeout, malformed output - keeps the
    previously known set and records the exception *type name* only, so neither
    a filesystem path nor repository content can reach a log line.
    """

    def __init__(
        self,
        root: Path,
        *,
        ttl_seconds: float = 0.0,
        limit: int = MAX_CHANGED_PATHS,
        capturer: SnapshotCapturer = capture_change_snapshot,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Initialise the signal.

        Args:
            root: Directory to capture - the same path the repository index
                was built from, which is also what Git paths are re-based
                onto.
            ttl_seconds: Minimum seconds between two captures. ``0`` (the
                default) means "capture once and never again". Only
                :meth:`refresh` honours the window; reading through
                :meth:`module_paths` never triggers a capture once the signal
                has been primed.
            limit: Upper bound on the number of module keys returned.
            capturer: Read-only snapshot boundary, overridable in tests.
            clock: Monotonic time source, overridable in tests.
        """
        self._root = root
        self._ttl_seconds = ttl_seconds if ttl_seconds > 0 else 0.0
        self._limit = limit
        self._capturer = capturer
        self._clock = clock
        self._paths: frozenset[str] = frozenset()
        self._captured_at = float("-inf")
        self._primed = False
        self._capture_count = 0
        self._failure_count = 0
        self._outside_root_count = 0
        self._last_error: str | None = None

    @property
    def root(self) -> Path:
        """The directory snapshots are captured from."""
        return self._root

    @property
    def ttl_seconds(self) -> float:
        """Minimum seconds between two captures; ``0`` disables refreshing."""
        return self._ttl_seconds

    @property
    def capture_count(self) -> int:
        """How many snapshots have been attempted."""
        return self._capture_count

    @property
    def failure_count(self) -> int:
        """How many snapshots have failed."""
        return self._failure_count

    @property
    def outside_root_count(self) -> int:
        """How many changed paths resolved to outside the indexed root.

        A nonzero count with an empty key set means the configured repository
        path and Git's working tree disagree about where the repository lives.
        Only the count is exposed - never the paths themselves.
        """
        return self._outside_root_count

    @property
    def last_error(self) -> str | None:
        """Class name of the most recent capture failure, or ``None``.

        Only the exception type is kept - never its message, which can carry
        filesystem paths.
        """
        return self._last_error

    def prime(self) -> frozenset[str]:
        """Capture now, bypassing the TTL.

        The gateway calls this during application startup, which is the only
        capture allowed to run where a request could notice.

        Returns:
            The changed module keys derived from this capture.
        """
        self._capture()
        return self._paths

    def module_paths(self) -> frozenset[str]:
        """Return the cached changed module keys; never refresh here.

        Safe to call from a request: a primed signal only reads a frozen set.
        The one exception is a signal that was never primed, which captures
        once so a pipeline built without a gateway lifespan still works.
        Callers that must keep Git out of the path entirely - the gateway -
        prime during startup and refresh through
        :meth:`refresh` on a worker thread.

        Returns:
            A frozen set of index module keys; empty for a clean repository,
            for a directory without Git metadata, and when every capture has
            failed.
        """
        if not self._primed:
            self._capture()
        return self._paths

    @property
    def is_stale(self) -> bool:
        """Whether calling :meth:`refresh` would take a new snapshot."""
        if not self._primed:
            return True
        if self._ttl_seconds <= 0.0:
            return False
        return self._clock() - self._captured_at >= self._ttl_seconds

    def refresh(self) -> bool:
        """Capture once the TTL has elapsed, and do nothing otherwise.

        This is the only TTL-driven capture. It blocks until Git answers, so
        it must run off the event loop - see
        :mod:`packages.repository.changed_files_refresh`.

        Returns:
            ``True`` when a snapshot was taken, ``False`` when the cached one
            was still fresh or the TTL disables refreshing entirely.
        """
        if not self.is_stale:
            return False
        self._capture()
        return True

    def _capture(self) -> None:
        """Run one read-only capture, keeping the last known set on failure.

        The clock is advanced even when the capture fails, so a repository
        Git cannot read does not get retried on every call. The derived set is
        published last so that a reader on another thread always sees a whole
        frozen set, never a half-updated one.
        """
        self._primed = True
        self._captured_at = self._clock()
        self._capture_count += 1
        try:
            snapshot = self._capturer(self._root)
        except Exception as error:  # graceful degradation, never raised
            self._failure_count += 1
            self._last_error = type(error).__name__
            return
        derivation = derive_changed_module_paths(
            snapshot,
            index_root=self._root,
            limit=self._limit,
        )
        self._last_error = None
        self._outside_root_count += derivation.outside_root_count
        self._paths = derivation.keys
