"""Tests for ``scripts/git_change_snapshot.py``.

The script is the documented entry point of Git Change Snapshot v1, so
these tests pin the table and JSON output shapes and the exit codes for
operational errors. Every repository is a throwaway temporary one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.git_change_snapshot import EXIT_ERROR, EXIT_OK, main
from tests.repository.git_helpers import (
    commit_all,
    isolate_git_environment,
    make_repository,
    repository_state,
    requires_git,
    run_git,
    write_file,
)

_DOCUMENT_KEYS = [
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


@pytest.fixture(autouse=True)
def _isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every Git invocation away from machine-wide configuration."""
    isolate_git_environment(monkeypatch, tmp_path)


def _dirty_repository(tmp_path: Path) -> Path:
    """Build one repository that is staged, unstaged, renamed, deleted, and new.

    File contents stay distinct so Git's rename detection cannot pair the
    rename with the unrelated deletion.
    """
    repository = make_repository(tmp_path)
    write_file(repository, "gone.txt", "gone content\n")
    write_file(repository, "keep.txt", "keep content\n")
    write_file(repository, "moved name.txt", "moved content\n")
    commit_all(repository, "initial")
    write_file(repository, "keep.txt", "keep content, staged\n")
    run_git(repository, "add", "keep.txt")
    write_file(repository, "keep.txt", "keep content, also unstaged\n")
    run_git(repository, "rm", "--quiet", "gone.txt")
    run_git(repository, "mv", "moved name.txt", "moved name again.txt")
    write_file(repository, "brand new.txt", "untracked content\n")
    return repository


@requires_git
class TestGitChangeSnapshotScript:
    """CLI behaviour of the read-only snapshot script."""

    def test_json_output_matches_documented_schema(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repository = _dirty_repository(tmp_path)

        exit_code = main([str(repository), "--json"])
        document = json.loads(capsys.readouterr().out)

        assert exit_code == EXIT_OK
        assert list(document) == _DOCUMENT_KEYS
        assert document["schema_version"] == 1
        assert Path(document["repository_root"]).resolve() == repository.resolve()
        assert document["branch"] == "main"
        assert document["head_commit"]
        assert document["upstream"] is None
        assert document["ahead"] is None
        assert document["behind"] is None
        assert document["clean"] is False
        assert [row["path"] for row in document["staged"]] == [
            "gone.txt",
            "keep.txt",
            "moved name again.txt",
        ]
        assert [row["status"] for row in document["staged"]] == [
            "deleted",
            "modified",
            "renamed",
        ]
        assert [row["path"] for row in document["unstaged"]] == ["keep.txt"]
        assert [row["path"] for row in document["untracked"]] == ["brand new.txt"]
        assert [row["old_path"] for row in document["renamed"]] == ["moved name.txt"]
        assert [row["path"] for row in document["deleted"]] == ["gone.txt"]
        assert document["copied"] == []
        assert document["conflicted"] == []
        assert document["ignored"] == []
        assert document["counts"] == {
            "staged": 3,
            "unstaged": 1,
            "untracked": 1,
            "renamed": 1,
            "copied": 0,
            "deleted": 1,
            "conflicted": 0,
            "ignored": 0,
        }
        assert list(document["staged"][0]) == [
            "path",
            "old_path",
            "status",
            "index_status",
            "worktree_status",
        ]

    def test_table_output_lists_every_changed_path(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repository = _dirty_repository(tmp_path)

        exit_code = main([str(repository)])
        output = capsys.readouterr().out

        assert exit_code == EXIT_OK
        assert "GIT CHANGE SNAPSHOT" in output
        assert "state      : dirty" in output
        assert "STAGED (3)" in output
        assert "UNSTAGED (1)" in output
        assert "UNTRACKED (1)" in output
        assert "moved name again.txt  <-  moved name.txt" in output
        assert "branch     : main" in output

    def test_clean_repository_reports_no_changes(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repository = make_repository(tmp_path)
        write_file(repository, "tracked.txt", "one\n")
        commit_all(repository, "initial")

        exit_code = main([str(repository)])
        output = capsys.readouterr().out

        assert exit_code == EXIT_OK
        assert "state      : clean" in output
        assert "nothing to commit, working tree clean" in output

        main([str(repository), "--json"])
        document = json.loads(capsys.readouterr().out)
        assert document["clean"] is True
        assert set(document["counts"].values()) == {0}

    def test_json_output_is_deterministic(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repository = _dirty_repository(tmp_path)
        state_before = repository_state(repository)

        main([str(repository), "--json"])
        first = capsys.readouterr().out
        main([str(repository), "--json"])
        second = capsys.readouterr().out

        assert first == second
        assert json.loads(first) == json.loads(second)
        assert repository_state(repository) == state_before

    def test_path_defaults_to_the_current_directory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repository = _dirty_repository(tmp_path)
        monkeypatch.chdir(repository)

        exit_code = main(["--json"])
        document = json.loads(capsys.readouterr().out)

        assert exit_code == EXIT_OK
        assert Path(document["repository_root"]).resolve() == repository.resolve()

    def test_path_outside_a_repository_exits_with_an_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        plain = tmp_path / "plain-directory"
        plain.mkdir()

        exit_code = main([str(plain)])
        captured = capsys.readouterr()

        assert exit_code == EXIT_ERROR
        assert captured.out == ""
        assert "not inside a Git working tree" in captured.err

    def test_missing_path_exits_with_an_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        exit_code = main([str(tmp_path / "does-not-exist")])

        assert exit_code == EXIT_ERROR
        assert "Path does not exist" in capsys.readouterr().err

    def test_file_path_exits_with_an_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        a_file = tmp_path / "not-a-directory.txt"
        a_file.write_text("content\n", encoding="utf-8")

        exit_code = main([str(a_file)])

        assert exit_code == EXIT_ERROR
        assert "not a directory" in capsys.readouterr().err
