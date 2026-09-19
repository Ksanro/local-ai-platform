"""Shared helpers for tests that need a real, throwaway Git repository.

Every helper runs Git inside a temporary directory whose configuration is
created locally (``user.name``/``user.email``), with global and system
configuration neutralised and upward repository discovery capped. Tests
therefore never depend on a developer's Git setup, never touch a real
repository, and never reach the network.

The mutating Git commands live here, in test setup only. The code under
test (:mod:`packages.repository.git_changes`) stays read-only.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest

GIT_EXECUTABLE: str | None = shutil.which("git")
GIT_AVAILABLE: bool = GIT_EXECUTABLE is not None

#: Skip an entire module when Git is genuinely not installed.
requires_git = pytest.mark.skipif(
    not GIT_AVAILABLE,
    reason="git executable is not available on PATH",
)


def run_git(cwd: Path, *args: str) -> str:
    """Run a Git command in ``cwd`` and return its trimmed stdout.

    Args:
        cwd: Directory to run Git in.
        *args: Git arguments after the executable.

    Returns:
        Standard output with surrounding whitespace removed.

    Raises:
        RuntimeError: If the command exits nonzero.
    """
    completed = subprocess.run(
        [GIT_EXECUTABLE or "git", *args],
        cwd=str(cwd),
        capture_output=True,
        shell=False,
        check=False,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"git {' '.join(args)} failed in {cwd} "
            f"(exit {completed.returncode}): {stderr.strip()}"
        )
    return stdout.strip()


def isolate_git_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate Git from machine configuration and from parent repositories.

    Args:
        monkeypatch: pytest monkeypatch used to rewrite the environment.
        tmp_path: Temporary directory that becomes the search ceiling.
    """
    empty_config = tmp_path / "gitconfig-isolated"
    empty_config.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_config))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty_config))
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY"):
        monkeypatch.delenv(name, raising=False)


def make_repository(tmp_path: Path, name: str = "repo") -> Path:
    """Create a temporary repository with local-only identity settings.

    Args:
        tmp_path: Base temporary directory.
        name: Directory name of the new repository.

    Returns:
        The repository root path.
    """
    repository = tmp_path / name
    repository.mkdir(parents=True, exist_ok=True)
    run_git(repository, "init", "-b", "main", "--quiet")
    configure_identity(repository)
    return repository


def configure_identity(repository: Path) -> None:
    """Set local-only Git settings so tests never need global configuration.

    Args:
        repository: Repository root to configure.
    """
    settings = {
        "user.name": "Repository Test",
        "user.email": "repository-test@example.invalid",
        "core.autocrlf": "false",
        "core.eol": "lf",
        "commit.gpgsign": "false",
        "gc.auto": "0",
        "maintenance.auto": "false",
    }
    for key, value in settings.items():
        run_git(repository, "config", "--local", key, value)


def make_bare_repository(tmp_path: Path, name: str = "remote.git") -> Path:
    """Create a local bare repository usable as an ``origin`` remote."""
    repository = tmp_path / name
    repository.mkdir(parents=True, exist_ok=True)
    run_git(repository, "init", "--bare", "--quiet", "-b", "main", ".")
    return repository


def write_file(repository: Path, relative_path: str, text: str = "content\n") -> Path:
    """Write ``relative_path`` inside ``repository``, creating parents."""
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def commit_all(repository: Path, message: str = "test commit") -> str:
    """Stage everything inside ``repository`` and commit it.

    Returns:
        The new HEAD commit.
    """
    run_git(repository, "add", "--all")
    run_git(repository, "commit", "--quiet", "-m", message)
    return run_git(repository, "rev-parse", "HEAD")


def head_commit(repository: Path) -> str:
    """Return the current HEAD commit of ``repository``."""
    return run_git(repository, "rev-parse", "HEAD")


def repository_state(repository: Path) -> dict[str, str]:
    """Fingerprint everything Git stores under ``.git``.

    Used to prove that taking a snapshot leaves the repository untouched:
    the returned mapping changes if Git writes, adds, or removes any file
    in the administration directory.

    Args:
        repository: Repository root.

    Returns:
        Mapping of forward-slash ``.git`` paths to ``size:sha256``.
    """
    git_dir = repository / ".git"
    state: dict[str, str] = {}
    for path in sorted(git_dir.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            state[path.relative_to(git_dir).as_posix()] = f"{path.stat().st_size}:{digest}"
    return state
