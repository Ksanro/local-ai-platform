"""Focused tests for the read-only Git change snapshot.

Real throwaway repositories prove that the porcelain v2 stream is parsed
the way Git actually emits it (NUL-delimited paths, spaces, Unicode
names, renames, detached HEAD, missing upstreams). Crafted streams cover
the shapes that are expensive to build on disk, and every mutating Git
command stays in test setup where it can only touch a temporary
directory. Tests skip with an explicit reason when Git is not installed.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from packages.repository import git_changes
from packages.repository.git_changes import (
    GitChangeSnapshot,
    GitChangeStatus,
    GitCommandError,
    GitCommandResult,
    GitError,
    GitFileChange,
    GitPorcelainParseError,
    GitTimeoutError,
    GitUnavailableError,
    GitUnsafeCommandError,
    NotAGitRepositoryError,
    capture_change_snapshot,
    parse_porcelain_v2,
    run_git_command,
)
from tests.repository.git_helpers import (
    commit_all,
    configure_identity,
    head_commit,
    isolate_git_environment,
    make_bare_repository,
    make_repository,
    repository_state,
    requires_git,
    run_git,
    write_file,
)

_ROOT_COMMAND = ("rev-parse", "--show-toplevel")
_STATUS_COMMAND = (
    "--no-optional-locks",
    "status",
    "--porcelain=v2",
    "-z",
    "--branch",
    "--untracked-files=all",
)

#: Git verbs that would change a repository if they ever reached Git.
_FORBIDDEN_GIT_VERBS = frozenset(
    {
        "add",
        "am",
        "apply",
        "checkout",
        "cherry-pick",
        "clean",
        "clone",
        "commit",
        "config",
        "fetch",
        "gc",
        "init",
        "merge",
        "mv",
        "prune",
        "push",
        "rebase",
        "reflog",
        "reset",
        "restore",
        "revert",
        "rm",
        "stash",
        "switch",
        "tag",
        "update-index",
        "update-ref",
        "worktree",
        "write-tree",
    }
)

#: A realistic ``1 <XY> <sub> <mH> <mI> <mW> <hH> <hI> <path>`` prefix.
_TRACKED_FIELDS = ("N...", "100644", "100644", "100644", "0" * 40, "0" * 40)


@pytest.fixture(autouse=True)
def _isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every Git invocation away from machine-wide configuration."""
    isolate_git_environment(monkeypatch, tmp_path)


def _records(*entries: str) -> bytes:
    """Join porcelain v2 records exactly the way ``-z`` terminates them."""
    return "".join(f"{entry}\x00" for entry in entries).encode("utf-8")


def _tracked(xy: str, path: str) -> str:
    """Build one ordinary changed-entry record from its ``<XY>`` letters."""
    return " ".join(("1", xy, *_TRACKED_FIELDS, path))


def _rows(changes: tuple[GitFileChange, ...]) -> list[tuple[str, str, str, str]]:
    """Reduce changes to comparable ``(path, status, index, worktree)`` rows."""
    return [(c.path, c.status.value, c.index_status, c.worktree_status) for c in changes]


@requires_git
class TestRealRepositorySnapshots:
    """Snapshots of real temporary repositories built with Git itself."""

    def test_clean_repository_reports_no_changes(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        commit_all(repository, "initial")

        snapshot = capture_change_snapshot(repository)

        assert snapshot.is_clean
        assert not snapshot.is_dirty
        assert snapshot.staged == ()
        assert snapshot.unstaged == ()
        assert snapshot.untracked == ()
        assert snapshot.renamed == ()
        assert snapshot.copied == ()
        assert snapshot.deleted == ()
        assert snapshot.conflicted == ()
        assert snapshot.branch == "main"
        assert snapshot.head_commit == head_commit(repository)
        assert snapshot.upstream is None
        assert snapshot.ahead is None
        assert snapshot.behind is None
        assert snapshot.repository_root.resolve() == repository.resolve()

    def test_staged_modification_is_reported_in_staged_only(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        commit_all(repository, "initial")
        write_file(repository, "tracked.txt", "two staged\n")
        run_git(repository, "add", "tracked.txt")

        snapshot = capture_change_snapshot(repository)

        assert _rows(snapshot.staged) == [("tracked.txt", "modified", "M", ".")]
        assert snapshot.unstaged == ()
        assert snapshot.deleted == ()
        assert snapshot.is_dirty

    def test_unstaged_modification_is_reported_in_unstaged_only(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        commit_all(repository, "initial")
        write_file(repository, "tracked.txt", "two unstaged\n")

        snapshot = capture_change_snapshot(repository)

        assert _rows(snapshot.unstaged) == [("tracked.txt", "modified", ".", "M")]
        assert snapshot.staged == ()

    def test_same_file_can_be_staged_and_unstaged(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        commit_all(repository, "initial")
        write_file(repository, "tracked.txt", "two staged\n")
        run_git(repository, "add", "tracked.txt")
        write_file(repository, "tracked.txt", "three on top, unstaged\n")

        snapshot = capture_change_snapshot(repository)

        assert _rows(snapshot.staged) == [("tracked.txt", "modified", "M", "M")]
        assert _rows(snapshot.unstaged) == [("tracked.txt", "modified", "M", "M")]
        assert snapshot.staged == snapshot.unstaged
        assert snapshot.counts["staged"] == 1
        assert snapshot.counts["unstaged"] == 1

    def test_added_file_is_staged(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "seed.txt", "seed\n")
        commit_all(repository, "initial")
        write_file(repository, "brand new file.txt", "new\n")
        run_git(repository, "add", "brand new file.txt")

        snapshot = capture_change_snapshot(repository)

        assert _rows(snapshot.staged) == [("brand new file.txt", "added", "A", ".")]
        assert snapshot.untracked == ()

    def test_untracked_files_are_listed_recursively(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        commit_all(repository, "initial")
        write_file(repository, "untracked dir/sub/deep file.txt", "deep\n")
        write_file(repository, "untracked dir/top.txt", "top\n")

        snapshot = capture_change_snapshot(repository)

        assert [change.path for change in snapshot.untracked] == [
            "untracked dir/sub/deep file.txt",
            "untracked dir/top.txt",
        ]
        assert [change.status for change in snapshot.untracked] == [
            GitChangeStatus.UNTRACKED,
            GitChangeStatus.UNTRACKED,
        ]
        assert all(not change.is_staged for change in snapshot.untracked)
        assert all(not change.is_unstaged for change in snapshot.untracked)
        assert snapshot.staged == ()
        assert snapshot.is_dirty

    def test_worktree_deletion_is_unstaged_and_deleted(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "keep.txt", "keep\n")
        write_file(repository, "gone.txt", "gone\n")
        commit_all(repository, "initial")
        (repository / "gone.txt").unlink()

        snapshot = capture_change_snapshot(repository)

        assert _rows(snapshot.unstaged) == [("gone.txt", "deleted", ".", "D")]
        assert _rows(snapshot.deleted) == [("gone.txt", "deleted", ".", "D")]
        assert snapshot.deleted == snapshot.unstaged
        assert snapshot.staged == ()

    def test_staged_deletion_is_staged_and_deleted(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "keep.txt", "keep\n")
        write_file(repository, "gone.txt", "gone\n")
        commit_all(repository, "initial")
        run_git(repository, "rm", "--quiet", "gone.txt")

        snapshot = capture_change_snapshot(repository)

        assert _rows(snapshot.staged) == [("gone.txt", "deleted", "D", ".")]
        assert _rows(snapshot.deleted) == [("gone.txt", "deleted", "D", ".")]
        assert snapshot.untracked == ()

    def test_rename_with_spaces_keeps_old_and_new_path(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "old name with spaces.txt", "payload\n")
        commit_all(repository, "initial")
        run_git(repository, "mv", "old name with spaces.txt", "new name with spaces.txt")

        snapshot = capture_change_snapshot(repository)

        renamed = snapshot.renamed[0]
        assert renamed.path == "new name with spaces.txt"
        assert renamed.old_path == "old name with spaces.txt"
        assert renamed.status is GitChangeStatus.RENAMED
        assert (renamed.index_status, renamed.worktree_status) == ("R", ".")
        assert renamed in snapshot.staged
        assert snapshot.deleted == ()
        assert snapshot.counts["renamed"] == 1

    def test_unicode_paths_survive_the_nul_delimited_stream(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        accented = "caf\u00e9-\u00fcni\u00efcode.txt"
        spaced_cjk = "\u65e5\u672c \u8a9e file.txt"
        renamed_cjk = "\u65e5\u672c\u8a9e-renamed.txt"
        write_file(repository, accented, "one\n")
        write_file(repository, spaced_cjk, "one\n")
        commit_all(repository, "initial")
        write_file(repository, accented, "two\n")
        run_git(repository, "mv", spaced_cjk, renamed_cjk)

        snapshot = capture_change_snapshot(repository)

        assert _rows(snapshot.unstaged) == [(accented, "modified", ".", "M")]
        assert [(change.path, change.old_path) for change in snapshot.renamed] == [
            (renamed_cjk, spaced_cjk)
        ]

    def test_detached_head_has_no_branch_but_keeps_the_commit(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        first = commit_all(repository, "first")
        write_file(repository, "tracked.txt", "two\n")
        commit_all(repository, "second")
        run_git(repository, "checkout", "--detach", "--quiet", first)

        snapshot = capture_change_snapshot(repository)

        assert snapshot.branch is None
        assert snapshot.head_commit == first
        assert snapshot.upstream is None
        assert snapshot.ahead is None
        assert snapshot.behind is None
        assert snapshot.is_clean

    def test_repository_without_upstream_reports_none(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        commit_all(repository, "initial")
        write_file(repository, "tracked.txt", "two\n")

        snapshot = capture_change_snapshot(repository)

        assert snapshot.branch == "main"
        assert snapshot.upstream is None
        assert snapshot.ahead is None
        assert snapshot.behind is None

    def test_upstream_ahead_and_behind_counts(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        remote = make_bare_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        commit_all(repository, "first")
        run_git(repository, "remote", "add", "origin", remote.as_posix())
        run_git(repository, "push", "--quiet", "--set-upstream", "origin", "main")

        snapshot = capture_change_snapshot(repository)
        assert snapshot.upstream == "origin/main"
        assert (snapshot.ahead, snapshot.behind) == (0, 0)

        write_file(repository, "local.txt", "local\n")
        commit_all(repository, "local commit")
        clone = tmp_path / "clone"
        run_git(tmp_path, "clone", "--quiet", "--branch", "main", remote.as_posix(), clone.name)
        configure_identity(clone)
        write_file(clone, "from-remote.txt", "remote\n")
        commit_all(clone, "remote commit")
        run_git(clone, "push", "--quiet", "origin", "main")
        run_git(repository, "fetch", "--quiet", "origin")

        snapshot = capture_change_snapshot(repository)
        assert snapshot.upstream == "origin/main"
        assert (snapshot.ahead, snapshot.behind) == (1, 1)

    def test_collections_are_ordered_deterministically(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        for name in ("zeta.txt", "alpha.txt", "mid/file.txt", "mid/beta.txt"):
            write_file(repository, name, f"original {name}\n")
        commit_all(repository, "initial")
        run_git(repository, "rm", "--quiet", "zeta.txt")
        for name in ("alpha.txt", "mid/file.txt", "mid/beta.txt"):
            write_file(repository, name, f"modified {name}\n")
        run_git(repository, "add", "alpha.txt")
        write_file(repository, "alpha.txt", "modified alpha.txt, also unstaged\n")
        for name in ("untracked_b.txt", "untracked_a.txt"):
            write_file(repository, name, f"new {name}\n")

        snapshot = capture_change_snapshot(repository)
        repeated = capture_change_snapshot(repository)

        assert [change.path for change in snapshot.staged] == ["alpha.txt", "zeta.txt"]
        assert [change.path for change in snapshot.unstaged] == [
            "alpha.txt",
            "mid/beta.txt",
            "mid/file.txt",
        ]
        assert [change.path for change in snapshot.untracked] == [
            "untracked_a.txt",
            "untracked_b.txt",
        ]
        assert [change.path for change in snapshot.deleted] == [
            "zeta.txt",
        ]
        assert snapshot == repeated
        assert json.dumps(snapshot.to_dict()) == json.dumps(repeated.to_dict())

    def test_paths_stay_relative_when_called_from_a_subdirectory(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "packages/deep/tracked.txt", "one\n")
        commit_all(repository, "initial")
        write_file(repository, "packages/deep/tracked.txt", "two\n")
        write_file(repository, "packages/deep/new.txt", "new\n")

        snapshot = capture_change_snapshot(repository / "packages" / "deep")

        assert snapshot.repository_root.resolve() == repository.resolve()
        assert [change.path for change in snapshot.unstaged] == ["packages/deep/tracked.txt"]
        assert [change.path for change in snapshot.untracked] == ["packages/deep/new.txt"]

    def test_unborn_branch_has_no_head_commit(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "first.txt", "one\n")

        untracked = capture_change_snapshot(repository)
        run_git(repository, "add", "first.txt")
        staged = capture_change_snapshot(repository)

        assert untracked.branch == "main"
        assert untracked.head_commit is None
        assert [change.path for change in untracked.untracked] == ["first.txt"]
        assert staged.head_commit is None
        assert _rows(staged.staged) == [("first.txt", "added", "A", ".")]

    def test_bare_repository_is_not_supported(self, tmp_path: Path) -> None:
        bare = make_bare_repository(tmp_path)

        with pytest.raises(NotAGitRepositoryError):
            capture_change_snapshot(bare)

    def test_path_outside_any_repository_raises_typed_error(self, tmp_path: Path) -> None:
        plain = tmp_path / "plain-directory"
        plain.mkdir()

        with pytest.raises(NotAGitRepositoryError) as error:
            capture_change_snapshot(plain)

        assert "not inside a Git working tree" in str(error.value)

    def test_missing_path_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            capture_change_snapshot(tmp_path / "does-not-exist")

    def test_file_path_raises_not_a_directory(self, tmp_path: Path) -> None:
        a_file = tmp_path / "a-file.txt"
        a_file.write_text("content\n", encoding="utf-8")

        with pytest.raises(NotADirectoryError):
            capture_change_snapshot(a_file)


class TestPorcelainV2Parsing:
    """Every porcelain v2 record shape, fed as captured byte streams.

    These need no Git installation, so they also document the exact
    contract the parser implements.
    """

    def test_branch_headers_populate_the_snapshot(self) -> None:
        output = _records(
            "# branch.oid " + "1" * 40,
            "# branch.head feature/git-snapshot",
            "# branch.upstream origin/feature/git-snapshot",
            "# branch.ab +12 -3",
        )

        snapshot = parse_porcelain_v2(output, repository_root=Path("/repository"))

        assert snapshot.head_commit == "1" * 40
        assert snapshot.branch == "feature/git-snapshot"
        assert snapshot.upstream == "origin/feature/git-snapshot"
        assert (snapshot.ahead, snapshot.behind) == (12, 3)
        assert snapshot.is_clean

    def test_sentinel_headers_become_none(self) -> None:
        detached = parse_porcelain_v2(
            _records("# branch.oid " + "2" * 40, "# branch.head (detached)"),
            repository_root=Path("/repository"),
        )
        unborn = parse_porcelain_v2(
            _records("# branch.oid (initial)", "# branch.head main"),
            repository_root=Path("/repository"),
        )

        assert detached.branch is None
        assert detached.head_commit == "2" * 40
        assert unborn.branch == "main"
        assert unborn.head_commit is None

    def test_unknown_headers_are_ignored(self) -> None:
        output = _records(
            "# branch.oid " + "3" * 40,
            "# branch.head main",
            "# stash 2",
            "# totally.future.header whatever",
            _tracked("M.", "tracked.txt"),
        )

        snapshot = parse_porcelain_v2(output, repository_root=Path("/repository"))

        assert [change.path for change in snapshot.staged] == ["tracked.txt"]

    def test_rename_record_keeps_both_paths_from_the_nul_stream(self) -> None:
        output = _records(
            "# branch.oid " + "4" * 40,
            "# branch.head main",
            " ".join(("2", "R.", *_TRACKED_FIELDS, "R100", "new name with spaces.txt")),
            "old name with spaces.txt",
        )

        snapshot = parse_porcelain_v2(output, repository_root=Path("/repository"))

        assert _rows(snapshot.renamed) == [("new name with spaces.txt", "renamed", "R", ".")]
        assert snapshot.renamed[0].old_path == "old name with spaces.txt"
        assert snapshot.renamed == snapshot.staged
        assert snapshot.copied == ()

    def test_copy_record_is_reported_as_copied(self) -> None:
        output = _records(
            " ".join(("2", "C.", *_TRACKED_FIELDS, "C75", "copied/target.txt")),
            "copied/source.txt",
        )

        snapshot = parse_porcelain_v2(output, repository_root=Path("/repository"))

        assert _rows(snapshot.copied) == [("copied/target.txt", "copied", "C", ".")]
        assert snapshot.copied[0].old_path == "copied/source.txt"
        assert snapshot.renamed == ()

    def test_type_change_record_classifies_the_path(self) -> None:
        snapshot = parse_porcelain_v2(
            _records(_tracked("T.", "notes")),
            repository_root=Path("/repository"),
        )

        assert _rows(snapshot.staged) == [("notes", "type_changed", "T", ".")]

    def test_unmerged_record_is_conflicted_only(self) -> None:
        conflict = " ".join(
            (
                "u",
                "UU",
                "N...",
                "100644",
                "100644",
                "100644",
                "100644",
                "0" * 40,
                "1" * 40,
                "2" * 40,
                "both changed.txt",
            )
        )

        snapshot = parse_porcelain_v2(_records(conflict), repository_root=Path("/repository"))

        assert _rows(snapshot.conflicted) == [("both changed.txt", "unmerged", "U", "U")]
        assert snapshot.staged == ()
        assert snapshot.unstaged == ()
        assert snapshot.deleted == ()
        assert snapshot.is_dirty

    def test_ignored_record_never_marks_the_tree_dirty(self) -> None:
        snapshot = parse_porcelain_v2(
            _records("! build/output.bin"),
            repository_root=Path("/repository"),
        )

        assert _rows(snapshot.ignored) == [("build/output.bin", "ignored", "!", "!")]
        assert snapshot.is_clean

    def test_paths_with_spaces_and_unicode_are_not_quoted(self) -> None:
        accented = "caf\u00e9 \u00fcni\u00efc\u00f8de.txt"
        snapshot = parse_porcelain_v2(
            _records(_tracked(".M", accented), f"? another {accented}"),
            repository_root=Path("/repository"),
        )

        assert [change.path for change in snapshot.unstaged] == [accented]
        assert [change.path for change in snapshot.untracked] == [f"another {accented}"]

    def test_path_whitespace_is_preserved_not_stripped(self) -> None:
        snapshot = parse_porcelain_v2(
            _records(_tracked(".M", " trailing space.txt "), "?  leading space.txt"),
            repository_root=Path("/repository"),
        )

        assert [change.path for change in snapshot.unstaged] == [" trailing space.txt "]
        assert [change.path for change in snapshot.untracked] == [" leading space.txt"]

    def test_untracked_record_without_path_raises_parse_error(self) -> None:
        with pytest.raises(GitPorcelainParseError, match="record needs a path"):
            parse_porcelain_v2(_records("?"), repository_root=Path("/repo"))


    def test_records_are_ordered_regardless_of_stream_order(self) -> None:
        snapshot = parse_porcelain_v2(
            _records(
                _tracked(".M", "zulu.txt"),
                "? yankee.txt",
                _tracked("M.", "alpha.txt"),
                _tracked(".D", "mike.txt"),
            ),
            repository_root=Path("/repository"),
        )

        assert [change.path for change in snapshot.unstaged] == ["mike.txt", "zulu.txt"]
        assert [change.path for change in snapshot.staged] == ["alpha.txt"]
        assert [change.path for change in snapshot.deleted] == ["mike.txt"]
        assert [change.path for change in snapshot.untracked] == ["yankee.txt"]

    def test_missing_branch_headers_stay_none(self) -> None:
        snapshot = parse_porcelain_v2(
            _records(_tracked("M.", "tracked.txt")),
            repository_root=Path("/repository"),
        )

        assert snapshot.branch is None
        assert snapshot.head_commit is None
        assert snapshot.upstream is None
        assert snapshot.ahead is None
        assert snapshot.behind is None

    def test_empty_stream_raises_parse_error(self) -> None:
        with pytest.raises(GitPorcelainParseError, match="no porcelain v2 output"):
            parse_porcelain_v2(b"", repository_root=Path("/repository"))

    def test_empty_record_raises_parse_error(self) -> None:
        with pytest.raises(GitPorcelainParseError, match="empty record"):
            parse_porcelain_v2(
                _records("# branch.head main", ""),
                repository_root=Path("/repository"),
            )

    def test_unknown_record_kind_raises_parse_error(self) -> None:
        with pytest.raises(GitPorcelainParseError, match="unknown porcelain v2 record kind"):
            parse_porcelain_v2(_records("9 M. N... 100644 path"), repository_root=Path("/repo"))

    def test_truncated_record_raises_parse_error(self) -> None:
        with pytest.raises(GitPorcelainParseError, match="needs 9 fields"):
            parse_porcelain_v2(_records("1 M. N... 100644"), repository_root=Path("/repo"))

    def test_invalid_status_letters_raise_parse_error(self) -> None:
        with pytest.raises(GitPorcelainParseError, match="invalid porcelain v2 status field"):
            parse_porcelain_v2(_records(_tracked("Z.", "x.txt")), repository_root=Path("/repo"))

    def test_rename_without_source_path_raises_parse_error(self) -> None:
        record = " ".join(("2", "R.", *_TRACKED_FIELDS, "R100", "new.txt"))

        with pytest.raises(GitPorcelainParseError, match="missing its source path"):
            parse_porcelain_v2(_records(record), repository_root=Path("/repo"))

    def test_malformed_ahead_behind_header_raises_parse_error(self) -> None:
        with pytest.raises(GitPorcelainParseError, match="branch.ab header is malformed"):
            parse_porcelain_v2(
                _records("# branch.ab two -zero"),
                repository_root=Path("/repo"),
            )

    def test_malformed_object_name_header_raises_parse_error(self) -> None:
        with pytest.raises(GitPorcelainParseError, match="branch.oid header is malformed"):
            parse_porcelain_v2(
                _records("# branch.oid not-a-commit"),
                repository_root=Path("/repo"),
            )

    def test_header_without_value_raises_parse_error(self) -> None:
        with pytest.raises(GitPorcelainParseError, match="has no value"):
            parse_porcelain_v2(_records("# branch.oid"), repository_root=Path("/repo"))


class _RecordingRun:
    """Stand-in for :func:`subprocess.run` that never starts a process."""

    def __init__(self, stdout: bytes = b"") -> None:
        self.argv: list[tuple[str, ...]] = []
        self.kwargs: list[dict[str, object]] = []
        self._stdout = stdout

    def __call__(self, argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        self.argv.append(tuple(argv))
        self.kwargs.append(dict(kwargs))
        return subprocess.CompletedProcess(
            args=list(argv), returncode=0, stdout=self._stdout, stderr=b""
        )

    @property
    def started_a_process(self) -> bool:
        return bool(self.argv)


class TestSubprocessBoundary:
    """The narrow Git boundary only ever starts allowlisted read-only commands."""

    def test_allowlist_holds_exactly_the_two_read_only_commands(self) -> None:
        assert git_changes._ALLOWED_COMMAND_VECTORS == (_ROOT_COMMAND, _STATUS_COMMAND)
        assert set(git_changes._ALLOWED_COMMANDS) == {_ROOT_COMMAND, _STATUS_COMMAND}

    @pytest.mark.parametrize(
        "command",
        [_ROOT_COMMAND, _STATUS_COMMAND],
        ids=["rev-parse", "status"],
    )
    def test_allowed_commands_reach_subprocess_run(
        self,
        command: tuple[str, ...],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run = _RecordingRun()
        monkeypatch.setattr(git_changes.subprocess, "run", run)

        result = run_git_command(command, tmp_path)

        assert run.started_a_process
        assert run.argv == [("git", *command)]
        assert result.command == command
        assert result.returncode == 0

    @pytest.mark.parametrize(
        "command",
        [
            ("reset", "--hard"),
            ("clean", "-fd"),
            ("fetch", "origin"),
            ("push", "origin", "main"),
            ("checkout", "main"),
            ("add", "."),
            ("commit", "-m", "snapshot"),
            ("apply", "--cached", "patch.diff"),
            ("update-index", "--refresh"),
            ("worktree", "add", "../other"),
        ],
        ids=[
            "reset",
            "clean",
            "fetch",
            "push",
            "checkout",
            "add",
            "commit",
            "apply",
            "update-index",
            "worktree",
        ],
    )
    def test_mutating_commands_are_rejected_before_any_process_starts(
        self,
        command: tuple[str, ...],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run = _RecordingRun()
        monkeypatch.setattr(git_changes.subprocess, "run", run)

        with pytest.raises(GitUnsafeCommandError) as error:
            run_git_command(command, tmp_path)

        assert not run.started_a_process
        assert run.argv == []
        assert isinstance(error.value, GitError)
        assert error.value.command == command
        assert " ".join(command) in str(error.value)

    @pytest.mark.parametrize(
        "command",
        [
            ("rev-parse",),
            ("rev-parse", "--show-toplevel", "--git-dir"),
            ("git", "rev-parse", "--show-toplevel"),
            ("--no-optional-locks", "status"),
            ("status", "--porcelain=v2", "-z", "--branch", "--untracked-files=all"),
            _ROOT_COMMAND + ("--verify",),
            _STATUS_COMMAND + ("--ignored",),
            ("--no-optional-locks", "status", "--porcelain=v1", "-z", "--branch"),
            (),
            ("",),
        ],
        ids=[
            "rev-parse-prefix",
            "rev-parse-extra-flag",
            "executable-repeated",
            "status-prefix",
            "status-without-lock-flag",
            "root-with-suffix",
            "status-with-suffix",
            "porcelain-v1",
            "empty-vector",
            "blank-token",
        ],
    )
    def test_variants_of_allowed_commands_are_rejected(
        self,
        command: tuple[str, ...],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        run = _RecordingRun()
        monkeypatch.setattr(git_changes.subprocess, "run", run)

        with pytest.raises(GitUnsafeCommandError):
            run_git_command(command, tmp_path)

        assert not run.started_a_process

    def test_allowlist_matches_argument_values_not_container_type(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run = _RecordingRun()
        monkeypatch.setattr(git_changes.subprocess, "run", run)

        result = run_git_command([*_STATUS_COMMAND], tmp_path)

        assert result.command == _STATUS_COMMAND
        assert run.argv == [("git", *_STATUS_COMMAND)]
        assert run.kwargs[0]["shell"] is False
        assert run.kwargs[0]["cwd"] == str(tmp_path)

    def test_read_only_commands_get_a_wall_clock_budget(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        run = _RecordingRun()
        monkeypatch.setattr(git_changes.subprocess, "run", run)

        run_git_command(_ROOT_COMMAND, tmp_path)

        assert run.kwargs[0]["timeout"] == git_changes.GIT_COMMAND_TIMEOUT_SECONDS

    def test_a_stalled_git_process_becomes_a_typed_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def stalled(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            raise subprocess.TimeoutExpired(list(argv), float(kwargs["timeout"]))  # type: ignore[arg-type]

        monkeypatch.setattr(git_changes.subprocess, "run", stalled)

        with pytest.raises(GitTimeoutError) as error:
            run_git_command(_STATUS_COMMAND, tmp_path)

        assert error.value.command == _STATUS_COMMAND
        assert error.value.timeout_seconds == git_changes.GIT_COMMAND_TIMEOUT_SECONDS
        assert isinstance(error.value, GitError)

    def test_rejection_message_lists_the_allowed_commands(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(git_changes.subprocess, "run", _RecordingRun())

        with pytest.raises(GitUnsafeCommandError) as error:
            run_git_command(("reset", "--hard"), tmp_path)

        assert "git rev-parse --show-toplevel" in str(error.value)
        assert "git --no-optional-locks status --porcelain=v2 -z --branch" in str(error.value)
        assert error.value.allowed == (_ROOT_COMMAND, _STATUS_COMMAND)

    @requires_git
    def test_only_read_only_git_commands_are_invoked(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        commit_all(repository, "initial")
        write_file(repository, "tracked.txt", "two\n")

        calls: list[tuple[tuple[str, ...], dict[str, object]]] = []
        real_run = subprocess.run

        def recording_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            calls.append((tuple(argv), kwargs))
            return real_run(argv, **kwargs)

        monkeypatch.setattr(git_changes.subprocess, "run", recording_run)
        snapshot = capture_change_snapshot(repository)

        assert [tuple(argv[1:]) for argv, _ in calls] == [_ROOT_COMMAND, _STATUS_COMMAND]
        assert all(argv[0] == "git" for argv, _ in calls)
        assert all(kwargs.get("shell", False) is False for _, kwargs in calls)
        assert all(kwargs.get("cwd") is not None for _, kwargs in calls)
        tokens = {token for argv, _ in calls for token in argv[1:]}
        assert _FORBIDDEN_GIT_VERBS.isdisjoint(tokens)
        assert snapshot.is_dirty

    @requires_git
    def test_snapshot_does_not_mutate_the_repository(self, tmp_path: Path) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        commit_all(repository, "initial")
        write_file(repository, "tracked.txt", "two, unstaged\n")
        write_file(repository, "brand new.txt", "untracked\n")

        state_before = repository_state(repository)
        head_before = head_commit(repository)

        capture_change_snapshot(repository)
        capture_change_snapshot(repository)

        assert repository_state(repository) == state_before
        assert head_commit(repository) == head_before
        assert (repository / "tracked.txt").read_text(encoding="utf-8") == "two, unstaged\n"
        assert sorted(path.name for path in repository.iterdir() if path.is_file()) == [
            "brand new.txt",
            "tracked.txt",
        ]

    def test_missing_git_executable_raises_git_unavailable_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def missing(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            raise FileNotFoundError(2, "No such file or directory", "git")

        monkeypatch.setattr(git_changes.subprocess, "run", missing)

        with pytest.raises(GitUnavailableError, match="was not found on PATH"):
            run_git_command(_ROOT_COMMAND, tmp_path)

    def test_unstartable_git_process_raises_git_unavailable_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def refused(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
            raise PermissionError(13, "Permission denied", "git")

        monkeypatch.setattr(git_changes.subprocess, "run", refused)

        with pytest.raises(GitUnavailableError, match="Could not start Git executable"):
            run_git_command(_ROOT_COMMAND, tmp_path)

    def test_failing_status_command_raises_git_command_error(self, tmp_path: Path) -> None:
        def runner(command: Sequence[str], cwd: Path) -> GitCommandResult:
            args = tuple(command)
            if args == _ROOT_COMMAND:
                stdout = str(tmp_path).encode("utf-8") + b"\n"
                return GitCommandResult(command=args, returncode=0, stdout=stdout, stderr="")
            return GitCommandResult(
                command=args,
                returncode=128,
                stdout=b"",
                stderr="fatal: unable to read tree (0123456789abcdef0123456789abcdef01234567)",
            )

        with pytest.raises(GitCommandError) as error:
            capture_change_snapshot(tmp_path, runner=runner)

        assert error.value.returncode == 128
        assert error.value.command == _STATUS_COMMAND
        assert "unable to read tree" in error.value.stderr

    def test_empty_repository_root_raises_parse_error(self, tmp_path: Path) -> None:
        def runner(command: Sequence[str], cwd: Path) -> GitCommandResult:
            return GitCommandResult(
                command=tuple(command),
                returncode=0,
                stdout=b"\n",
                stderr="",
            )

        with pytest.raises(GitPorcelainParseError, match="empty repository root"):
            capture_change_snapshot(tmp_path, runner=runner)


class TestSnapshotModels:
    """The public models are immutable and serialize with stable keys."""

    def test_file_change_is_immutable(self) -> None:
        change = GitFileChange(
            path="tracked.txt",
            status=GitChangeStatus.MODIFIED,
            index_status="M",
            worktree_status=".",
        )

        with pytest.raises(dataclasses.FrozenInstanceError):
            change.path = "other.txt"

    def test_snapshot_is_immutable(self) -> None:
        snapshot = GitChangeSnapshot(repository_root=Path("/repository"))

        with pytest.raises(dataclasses.FrozenInstanceError):
            snapshot.branch = "other-branch"

    def test_empty_snapshot_is_clean(self) -> None:
        snapshot = GitChangeSnapshot(repository_root=Path("/repository"))

        assert snapshot.is_clean
        assert not snapshot.is_dirty
        assert set(snapshot.counts.values()) == {0}

    def test_conflict_alone_makes_the_snapshot_dirty(self) -> None:
        conflicted = GitFileChange(
            path="both.txt",
            status=GitChangeStatus.UNMERGED,
            index_status="U",
            worktree_status="U",
        )
        snapshot = GitChangeSnapshot(
            repository_root=Path("/repository"),
            conflicted=(conflicted,),
        )

        assert snapshot.is_dirty
        assert snapshot.counts["conflicted"] == 1
        assert snapshot.counts["staged"] == 0

    def test_document_keys_are_stable(self) -> None:
        document = GitChangeSnapshot(repository_root=Path("/repository")).to_dict()

        assert list(document) == [
            "schema_version",
            "repository_root",
            "branch",
            "head_commit",
            "upstream",
            "ahead",
            "behind",
            "clean",
            "staged",
            "unstaged",
            "untracked",
            "renamed",
            "copied",
            "deleted",
            "conflicted",
            "ignored",
            "counts",
        ]
        assert document["schema_version"] == git_changes.SCHEMA_VERSION

    def test_change_keys_are_stable(self) -> None:
        change = GitFileChange(
            path="new.txt",
            status=GitChangeStatus.RENAMED,
            index_status="R",
            worktree_status=".",
            old_path="old.txt",
        )

        assert list(change.to_dict()) == [
            "path",
            "old_path",
            "status",
            "index_status",
            "worktree_status",
        ]

    def test_status_values_are_stable_strings(self) -> None:
        assert [status.value for status in GitChangeStatus] == [
            "added",
            "modified",
            "deleted",
            "renamed",
            "copied",
            "type_changed",
            "unmerged",
            "untracked",
            "ignored",
            "unknown",
        ]
