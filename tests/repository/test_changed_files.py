"""Focused tests for the change-aware repository-context ranking signal.

Crafted snapshots exercise path derivation deterministically, and real
throwaway repositories prove the clean-tree, dirty-tree, rename and
no-Git-metadata behaviours.  The signal must never raise, must never read
file contents, and must never return more than its documented bound.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from packages.repository.changed_files import (
    MAX_CHANGED_PATHS,
    ChangedFilesSignal,
    changed_module_paths,
    derive_changed_module_paths,
)
from packages.repository.git_changes import (
    GitChangeSnapshot,
    GitChangeStatus,
    GitFileChange,
    NotAGitRepositoryError,
    capture_change_snapshot,
)
from tests.repository.git_helpers import (
    commit_all,
    isolate_git_environment,
    make_repository,
    repository_state,
    requires_git,
    run_git,
    write_file,
)

MODIFIED = GitChangeStatus.MODIFIED
UNTRACKED = GitChangeStatus.UNTRACKED
DELETED = GitChangeStatus.DELETED
RENAMED = GitChangeStatus.RENAMED
COPIED = GitChangeStatus.COPIED
CONFLICTED = GitChangeStatus.UNMERGED
_STAGED_LETTERS: dict[GitChangeStatus, str] = {
    MODIFIED: "M",
    UNTRACKED: "?",
    DELETED: "D",
    RENAMED: "R",
    COPIED: "C",
    CONFLICTED: "U",
}


@pytest.fixture(autouse=True)
def _isolated_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep every Git invocation inside ``tmp_path``."""
    isolate_git_environment(monkeypatch, tmp_path)


def _change(
    path: str,
    status: GitChangeStatus,
    *,
    old_path: str | None = None,
    staged: bool = True,
) -> GitFileChange:
    """Build one change record with letters consistent with ``status``."""
    letter = _STAGED_LETTERS[status]
    return GitFileChange(
        index_status=letter if staged else ".",
        worktree_status="?" if status is UNTRACKED else ("M" if not staged else "."),
        status=status,
        path=path,
        old_path=old_path,
    )


def _snapshot(root: Path, **groups: tuple[GitFileChange, ...]) -> GitChangeSnapshot:
    """Build a deterministic snapshot from named change collections."""
    collected = {
        name: tuple(groups.get(name, ()))
        for name in (
            "staged",
            "unstaged",
            "untracked",
            "renamed",
            "copied",
            "deleted",
            "conflicted",
        )
    }
    return GitChangeSnapshot(
        repository_root=root,
        branch="main",
        head_commit="0" * 40,
        **collected,
    )


def _keys_for(root: Path, **groups: tuple[GitFileChange, ...]) -> set[str]:
    """Derive module keys from a crafted snapshot."""
    return set(changed_module_paths(_snapshot(root, **groups)))


def _make_directory_link(target: Path, link: Path) -> bool:
    """Create a directory link, or report that this platform refuses one.

    Windows only lets an unprivileged process create a junction, and POSIX has
    symlinks; both resolve to the same directory, which is the point.
    """
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return True
    except OSError:
        pass
    if os.name != "nt":
        return False
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0 and link.exists()


# ------------------------------------------------------------------
# Derivation
# ------------------------------------------------------------------


def test_clean_snapshot_yields_no_module_keys(tmp_path: Path) -> None:
    """A clean working tree contributes nothing to ranking."""
    root = tmp_path / "repo"
    assert changed_module_paths(_snapshot(root), index_root=root) == frozenset()


def test_modified_paths_map_to_index_module_keys(tmp_path: Path) -> None:
    """Git paths become suffix-less forward-slashed index keys."""
    root = tmp_path / "repo"
    keys = _keys_for(
        root,
        unstaged=(_change("packages/context/builder.py", MODIFIED),),
        staged=(_change("apps/gateway/main.py", MODIFIED, staged=True),),
    )
    assert keys == {"packages/context/builder", "apps/gateway/main"}


def test_untracked_paths_are_included(tmp_path: Path) -> None:
    """A new file the agent is working on is a changed file."""
    root = tmp_path / "repo"
    keys = _keys_for(root, untracked=(_change("packages/new/module.py", UNTRACKED, staged=False),))
    assert keys == {"packages/new/module"}


def test_conflicted_paths_are_included(tmp_path: Path) -> None:
    """A conflicted file is being edited, so it promotes."""
    root = tmp_path / "repo"
    keys = _keys_for(root, conflicted=(_change("packages/x/merge.py", CONFLICTED),))
    assert keys == {"packages/x/merge"}


def test_deleted_paths_never_promote(tmp_path: Path) -> None:
    """Symbols indexed from a deleted file are stale and must not rank up."""
    root = tmp_path / "repo"
    keys = _keys_for(
        root,
        deleted=(_change("packages/gone/module.py", DELETED),),
        staged=(_change("packages/gone/module.py", DELETED),),
    )
    assert keys == set()


def test_renamed_paths_promote_both_sides(tmp_path: Path) -> None:
    """A rename promotes the target and the pre-rename module.

    The repository index is built once at startup, so after a mid-session
    ``git mv`` it still holds the old module while the working tree has the
    new one.
    """
    root = tmp_path / "repo"
    rename = _change(
        "packages/context/new_name.py",
        RENAMED,
        old_path="packages/context/old_name.py",
    )
    keys = _keys_for(root, renamed=(rename,))
    assert keys == {"packages/context/new_name", "packages/context/old_name"}


def test_copied_paths_promote_both_sides(tmp_path: Path) -> None:
    """A copy promotes its destination and its source module."""
    root = tmp_path / "repo"
    keys = _keys_for(
        root,
        copied=(_change("packages/x/copy.py", COPIED, old_path="packages/x/original.py"),),
    )
    assert keys == {"packages/x/copy", "packages/x/original"}


def test_non_python_paths_are_dropped(tmp_path: Path) -> None:
    """The index holds Python modules only, so other files cannot rank up."""
    root = tmp_path / "repo"
    keys = _keys_for(
        root,
        unstaged=(
            _change("docs/STATUS.md", MODIFIED, staged=False),
            _change("README.md", MODIFIED, staged=False),
        ),
    )
    assert keys == set()


def test_paths_outside_the_index_root_are_dropped(tmp_path: Path) -> None:
    """When the index covers a subdirectory, only its own paths can match."""
    root = tmp_path / "repo"
    keys = set(
        changed_module_paths(
            _snapshot(
                root,
                unstaged=(
                    _change("packages/context/builder.py", MODIFIED, staged=False),
                    _change("apps/gateway/main.py", MODIFIED, staged=False),
                ),
            ),
            index_root=root / "packages",
        )
    )
    assert keys == {"context/builder"}


def test_absolute_and_parent_paths_are_rejected(tmp_path: Path) -> None:
    """Malformed records cannot smuggle a path into the key set."""
    root = tmp_path / "repo"
    keys = _keys_for(
        root,
        unstaged=(
            _change("/etc/passwd.py", MODIFIED, staged=False),
            _change("../outside/module.py", MODIFIED, staged=False),
            _change("C:/outside/module.py", MODIFIED, staged=False),
            _change("", MODIFIED, staged=False),
            _change("good/module.py", MODIFIED, staged=False),
        ),
    )
    assert keys == {"good/module"}


def test_paths_outside_the_index_root_are_counted(tmp_path: Path) -> None:
    """A silently dropped path must be visible in diagnostics.

    When the configured repository root and Git's working tree disagree, every
    path looks outside the root and the feature switches itself off. The count
    is what a log line can show without leaking a location.
    """
    root = tmp_path / "repo"
    derivation = derive_changed_module_paths(
        _snapshot(
            root,
            unstaged=(
                _change("../outside/module.py", MODIFIED, staged=False),
                _change("packages/a/mod.py", MODIFIED, staged=False),
            ),
        ),
        index_root=root / "packages",
    )
    assert derivation.keys == frozenset({"a/mod"})
    assert derivation.outside_root_count == 1


def test_dropped_paths_are_not_mistaken_for_outside_root(tmp_path: Path) -> None:
    """Only the "wrong root" failure mode feeds that counter."""
    root = tmp_path / "repo"
    derivation = derive_changed_module_paths(
        _snapshot(
            root,
            unstaged=(
                _change("/etc/passwd.py", MODIFIED, staged=False),
                _change("docs/readme.md", MODIFIED, staged=False),
                _change("", MODIFIED, staged=False),
            ),
        ),
        index_root=root,
    )
    assert derivation.keys == frozenset()
    assert derivation.outside_root_count == 0


def test_a_linked_index_root_is_the_same_repository(tmp_path: Path) -> None:
    """A repository reached through a link still produces keys.

    Git reports the working tree it discovered, while ``APP_REPOSITORY_PATH``
    can be a symlink, a junction, a ``subst`` drive or an 8.3 short name of the
    same directory. Comparing the two as text drops every path in silence.
    """
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    if not _make_directory_link(real, link):
        pytest.skip("this platform will not create directory links")

    derivation = derive_changed_module_paths(
        _snapshot(real, unstaged=(_change("packages/a/mod.py", MODIFIED, staged=False),)),
        index_root=link,
    )
    assert derivation.keys == frozenset({"packages/a/mod"})
    assert derivation.outside_root_count == 0


def test_duplicate_records_across_collections_collapse(tmp_path: Path) -> None:
    """A staged rename appears in two collections but contributes once."""
    root = tmp_path / "repo"
    change = _change("packages/x/new.py", RENAMED, old_path="packages/x/old.py")
    keys = _keys_for(root, staged=(change,), renamed=(change,))
    assert keys == {"packages/x/new", "packages/x/old"}


def test_result_is_bounded_and_deterministic(tmp_path: Path) -> None:
    """The smallest keys win when a tree holds more changes than the limit."""
    root = tmp_path / "repo"
    changes = tuple(
        _change(f"packages/mod_{index:02d}.py", MODIFIED, staged=False) for index in range(6)
    )
    keys = changed_module_paths(
        _snapshot(root, unstaged=changes),
        index_root=root,
        limit=2,
    )
    assert keys == frozenset({"packages/mod_00", "packages/mod_01"})


def test_default_limit_is_the_documented_bound(tmp_path: Path) -> None:
    """A huge dirty tree cannot exceed MAX_CHANGED_PATHS."""
    root = tmp_path / "repo"
    changes = tuple(
        _change(f"packages/mod_{index:04d}.py", MODIFIED, staged=False)
        for index in range(MAX_CHANGED_PATHS + 50)
    )
    keys = changed_module_paths(_snapshot(root, unstaged=changes), index_root=root)
    assert len(keys) == MAX_CHANGED_PATHS


# ------------------------------------------------------------------
# Capture policy
# ------------------------------------------------------------------


class _Clock:
    """Manually advanced monotonic clock."""

    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _Capturer:
    """Read-only snapshot boundary that records how often it is called.

    Each call consumes the next scripted result; the last entry repeats, and an
    exception entry raises.
    """

    def __init__(self, *results: GitChangeSnapshot | Exception) -> None:
        self.calls = 0
        self._results = list(results)

    def __call__(self, path: Path) -> GitChangeSnapshot:
        self.calls += 1
        item = self._results[min(self.calls - 1, len(self._results) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


def test_capture_happens_once_not_per_call(tmp_path: Path) -> None:
    """The default policy must never reach Git on every request."""
    root = tmp_path / "repo"
    capturer = _Capturer(_snapshot(root, unstaged=(_change("packages/a/mod.py", MODIFIED),)))
    signal = ChangedFilesSignal(root, capturer=capturer)

    for _ in range(5):
        assert signal.module_paths() == frozenset({"packages/a/mod"})

    assert capturer.calls == 1


def test_priming_captures_before_the_first_request(tmp_path: Path) -> None:
    """``prime`` moves the capture out of the request path entirely."""
    root = tmp_path / "repo"
    capturer = _Capturer(_snapshot(root, unstaged=(_change("packages/a/mod.py", MODIFIED),)))
    signal = ChangedFilesSignal(root, capturer=capturer)

    assert signal.prime() == frozenset({"packages/a/mod"})
    assert capturer.calls == 1
    assert signal.module_paths() == frozenset({"packages/a/mod"})
    assert capturer.calls == 1
    assert signal.capture_count == 1


def test_module_paths_never_refreshes_a_primed_signal(tmp_path: Path) -> None:
    """Reading is a cache lookup even when a TTL would allow a refresh.

    This is what keeps Git out of the request path: the only TTL-driven
    capture lives in :meth:`ChangedFilesSignal.refresh`, which the gateway
    runs on a worker thread.
    """
    root = tmp_path / "repo"
    capturer = _Capturer(_snapshot(root, unstaged=(_change("packages/a/mod.py", MODIFIED),)))
    clock = _Clock()
    signal = ChangedFilesSignal(root, ttl_seconds=1.0, capturer=capturer, clock=clock)
    signal.prime()

    for _ in range(5):
        clock.advance(60.0)
        assert signal.module_paths() == frozenset({"packages/a/mod"})

    assert capturer.calls == 1
    assert signal.is_stale is True


def test_refresh_recaptures_once_the_window_expires(tmp_path: Path) -> None:
    """A positive TTL refreshes at most once per window, and only on refresh."""
    root = tmp_path / "repo"
    first = _snapshot(root, unstaged=(_change("packages/a/mod.py", MODIFIED),))
    second = _snapshot(root, unstaged=(_change("packages/b/mod.py", MODIFIED),))
    capturer = _Capturer(first, second)
    clock = _Clock()
    signal = ChangedFilesSignal(root, ttl_seconds=30.0, capturer=capturer, clock=clock)

    assert signal.module_paths() == frozenset({"packages/a/mod"})
    assert signal.refresh() is False
    clock.advance(10.0)
    assert signal.refresh() is False
    assert signal.module_paths() == frozenset({"packages/a/mod"})
    clock.advance(20.0)
    assert signal.refresh() is True
    assert signal.module_paths() == frozenset({"packages/b/mod"})
    assert capturer.calls == 2


def test_zero_ttl_never_refreshes(tmp_path: Path) -> None:
    """The default policy cannot be revived by a caller looping on refresh."""
    root = tmp_path / "repo"
    capturer = _Capturer(_snapshot(root, unstaged=(_change("packages/a/mod.py", MODIFIED),)))
    clock = _Clock()
    signal = ChangedFilesSignal(root, ttl_seconds=0.0, capturer=capturer, clock=clock)
    signal.prime()

    for _ in range(3):
        clock.advance(3600.0)
        assert signal.refresh() is False

    assert capturer.calls == 1


def test_failed_capture_keeps_the_last_known_set(tmp_path: Path) -> None:
    """A snapshot failure must not erase a good signal or raise."""
    root = tmp_path / "repo"
    good = _snapshot(root, unstaged=(_change("packages/a/mod.py", MODIFIED),))
    capturer = _Capturer(good, RuntimeError("boom"))
    clock = _Clock()
    signal = ChangedFilesSignal(root, ttl_seconds=5.0, capturer=capturer, clock=clock)

    assert signal.module_paths() == frozenset({"packages/a/mod"})
    clock.advance(5.0)
    assert signal.refresh() is True
    assert signal.module_paths() == frozenset({"packages/a/mod"})
    assert signal.failure_count == 1
    assert signal.last_error == "RuntimeError"


def test_first_failure_yields_empty_without_raising(tmp_path: Path) -> None:
    """A repository Git cannot read degrades to today's behaviour."""
    root = tmp_path / "repo"
    signal = ChangedFilesSignal(
        root,
        capturer=_Capturer(NotAGitRepositoryError("no working tree")),
    )

    assert signal.module_paths() == frozenset()
    assert signal.last_error == "NotAGitRepositoryError"
    assert signal.failure_count == 1


def test_repeated_failure_does_not_retry_every_call(tmp_path: Path) -> None:
    """The TTL window still throttles retries after a failure."""
    root = tmp_path / "repo"
    capturer = _Capturer(NotAGitRepositoryError("no working tree"))
    clock = _Clock()
    signal = ChangedFilesSignal(root, ttl_seconds=30.0, capturer=capturer, clock=clock)

    for _ in range(10):
        assert signal.module_paths() == frozenset()
        assert signal.refresh() is False  # the window has not elapsed yet
        clock.advance(1.0)

    assert capturer.calls == 1


def test_refresh_recovers_after_a_failure(tmp_path: Path) -> None:
    """A repository Git can read again is picked up by the next window."""
    root = tmp_path / "repo"
    capturer = _Capturer(
        NotAGitRepositoryError("no working tree"),
        _snapshot(root, unstaged=(_change("packages/a/mod.py", MODIFIED),)),
    )
    clock = _Clock()
    signal = ChangedFilesSignal(root, ttl_seconds=10.0, capturer=capturer, clock=clock)

    assert signal.prime() == frozenset()
    clock.advance(10.0)
    assert signal.refresh() is True
    assert signal.module_paths() == frozenset({"packages/a/mod"})
    assert signal.failure_count == 1
    assert signal.last_error is None


def test_outside_root_paths_are_reported_as_a_count(tmp_path: Path) -> None:
    """A snapshot that escapes the indexed root says so in counts only."""
    root = tmp_path / "repo"
    capturer = _Capturer(
        _snapshot(
            root,
            unstaged=(
                _change("../elsewhere/mod.py", MODIFIED, staged=False),
                _change("packages/a/mod.py", MODIFIED, staged=False),
            ),
        ),
    )
    signal = ChangedFilesSignal(root / "packages", capturer=capturer)

    assert signal.module_paths() == frozenset({"a/mod"})
    assert signal.outside_root_count == 1


def test_error_detail_is_not_retained(tmp_path: Path) -> None:
    """Only the exception type is kept, never a message with paths."""
    root = tmp_path / "repo"
    signal = ChangedFilesSignal(
        root,
        capturer=_Capturer(NotAGitRepositoryError(f"not a repository: {root}")),
    )

    assert signal.module_paths() == frozenset()
    assert signal.last_error == "NotAGitRepositoryError"
    assert str(root) not in repr(signal.last_error)


# ------------------------------------------------------------------
# Real repositories
# ------------------------------------------------------------------


@requires_git
def test_clean_real_repository_yields_no_keys(tmp_path: Path) -> None:
    """A committed tree keeps ranking exactly as it is today."""
    repo = make_repository(tmp_path)
    write_file(repo, "packages/context/builder.py", "class ContextBuilder:\n    pass\n")
    commit_all(repo)

    assert ChangedFilesSignal(repo).module_paths() == frozenset()


@requires_git
def test_locally_modified_real_file_yields_its_module_key(tmp_path: Path) -> None:
    """An unstaged edit becomes the index key the builder can match."""
    repo = make_repository(tmp_path)
    write_file(repo, "packages/context/builder.py", "class ContextBuilder:\n    pass\n")
    commit_all(repo)
    write_file(repo, "packages/context/builder.py", "class ContextBuilder:\n    pass  # edited\n")

    assert ChangedFilesSignal(repo).module_paths() == frozenset({"packages/context/builder"})


@requires_git
def test_staged_and_untracked_real_files_yield_keys(tmp_path: Path) -> None:
    """Staged edits and brand new files both count as under edit."""
    repo = make_repository(tmp_path)
    write_file(repo, "apps/gateway/main.py", "def create_app():\n    pass\n")
    commit_all(repo)
    write_file(repo, "apps/gateway/main.py", "def create_app():\n    return None\n")
    run_git(repo, "add", "apps/gateway/main.py")
    write_file(repo, "packages/new/module.py", "def helper():\n    pass\n")

    assert ChangedFilesSignal(repo).module_paths() == frozenset(
        {"apps/gateway/main", "packages/new/module"}
    )


@requires_git
def test_renamed_real_file_yields_both_module_keys(tmp_path: Path) -> None:
    """``git mv`` promotes the new module and the pre-rename one."""
    repo = make_repository(tmp_path)
    write_file(repo, "packages/context/old_name.py", "class Thing:\n    pass\n")
    commit_all(repo)
    run_git(repo, "mv", "packages/context/old_name.py", "packages/context/new_name.py")

    assert ChangedFilesSignal(repo).module_paths() == frozenset(
        {"packages/context/old_name", "packages/context/new_name"}
    )


@requires_git
def test_deleted_real_file_yields_no_keys(tmp_path: Path) -> None:
    """A deleted file must not rank up symbols that no longer exist."""
    repo = make_repository(tmp_path)
    write_file(repo, "packages/gone/module.py", "class Gone:\n    pass\n")
    commit_all(repo)
    run_git(repo, "rm", "--quiet", "packages/gone/module.py")

    assert ChangedFilesSignal(repo).module_paths() == frozenset()


@requires_git
def test_non_python_real_file_yields_no_keys(tmp_path: Path) -> None:
    """Documentation edits cannot influence ranking."""
    repo = make_repository(tmp_path)
    write_file(repo, "docs/STATUS.md", "# Status\n")
    commit_all(repo)
    write_file(repo, "docs/STATUS.md", "# Status\n\nUpdated.\n")

    assert ChangedFilesSignal(repo).module_paths() == frozenset()


@requires_git
def test_capturing_a_real_repository_leaves_git_state_untouched(
    tmp_path: Path,
) -> None:
    """The signal stays strictly read-only: ``.git`` is byte-identical."""
    repo = make_repository(tmp_path)
    write_file(repo, "packages/context/builder.py", "class ContextBuilder:\n    pass\n")
    commit_all(repo)
    write_file(repo, "packages/context/builder.py", "class ContextBuilder:\n    pass  # edited\n")

    before = repository_state(repo)
    signal = ChangedFilesSignal(repo)
    signal.prime()
    signal.module_paths()

    assert repository_state(repo) == before


def test_directory_without_git_metadata_yields_empty(tmp_path: Path) -> None:
    """No Git metadata degrades to today's behaviour instead of raising."""
    outside = tmp_path / "not-a-repository"
    outside.mkdir()

    signal = ChangedFilesSignal(outside, capturer=capture_change_snapshot)

    assert signal.module_paths() == frozenset()
    assert signal.failure_count == 1
    assert signal.last_error is not None
