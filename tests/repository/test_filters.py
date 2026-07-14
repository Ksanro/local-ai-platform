"""Tests for the repository filter logic.

Verifies that both hardcoded ignored directories and gitignore patterns
are correctly applied when determining which paths to exclude.
"""

from __future__ import annotations

from pathlib import Path

from packages.repository.filters import (
    _DEFAULT_IGNORED_DIRS,
    parse_gitignore,
    should_ignore_path,
)

_project_root = Path(__file__).resolve().parent.parent.parent


class TestDefaultIgnoredDirs:
    """Tests for hardcoded ignored directory basenames."""

    def test_venv_is_ignored(self) -> None:
        """venv/ should be in the default ignored set."""
        assert "venv" in _DEFAULT_IGNORED_DIRS

    def test_node_modules_is_ignored(self) -> None:
        """node_modules should be in the default ignored set."""
        assert "node_modules" in _DEFAULT_IGNORED_DIRS

    def test_pycache_is_ignored(self) -> None:
        """__pycache__ should be in the default ignored set."""
        assert "__pycache__" in _DEFAULT_IGNORED_DIRS

    def test_git_is_ignored(self) -> None:
        """.git should be in the default ignored set."""
        assert ".git" in _DEFAULT_IGNORED_DIRS

    def test_build_is_ignored(self) -> None:
        """build should be in the default ignored set."""
        assert "build" in _DEFAULT_IGNORED_DIRS

    def test_dist_is_ignored(self) -> None:
        """dist should be in the default ignored set."""
        assert "dist" in _DEFAULT_IGNORED_DIRS


class TestShouldIgnorePath:
    """Tests for path ignore decision logic."""

    def test_hardcoded_dir_is_ignored(self) -> None:
        """A directory matching a hardcoded basename should be ignored."""
        path = Path("node_modules")
        assert should_ignore_path(path, True, []) is True

    def test_hardcoded_file_not_ignored(self) -> None:
        """A file matching a directory basename should not be ignored."""
        path = Path("node_modules")
        assert should_ignore_path(path, False, []) is False

    def test_non_ignored_dir_passes(self) -> None:
        """A directory not in the ignored set should pass."""
        path = Path("src")
        assert should_ignore_path(path, True, []) is False

    def test_file_always_passes(self) -> None:
        """Files should not be ignored by the hardcoded set."""
        path = Path("node_modules")
        assert should_ignore_path(path, False, []) is False


class TestGitignoreParsing:
    """Tests for .gitignore file parsing."""

    def test_parse_gitignore_returns_patterns(self) -> None:
        """parse_gitignore should return patterns from the project .gitignore."""
        patterns = parse_gitignore(_project_root)
        assert len(patterns) > 0

    def test_parse_gitignore_skips_comments(self) -> None:
        """parse_gitignore should skip lines starting with #."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            gitignore = Path(tmpdir) / ".gitignore"
            gitignore.write_text("# This is a comment\n*.pyc\n\n# Another comment\n")
            patterns = parse_gitignore(Path(tmpdir))
            assert "*.pyc" in patterns
            assert len(patterns) == 1

    def test_parse_gitignore_missing_file(self) -> None:
        """parse_gitignore should return empty list for missing file."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            patterns = parse_gitignore(Path(tmpdir))
            assert patterns == []


class TestGitignorePatterns:
    """Tests for gitignore pattern matching."""

    def test_glob_pattern_matches(self) -> None:
        """Glob patterns like *.pyc should match files with that suffix."""
        path = Path("foo.pyc")
        assert should_ignore_path(path, False, ["*.pyc"]) is True

    def test_glob_pattern_no_match(self) -> None:
        """Glob patterns should not match unrelated extensions."""
        path = Path("foo.py")
        assert should_ignore_path(path, False, ["*.pyc"]) is False

    def test_directory_pattern(self) -> None:
        """Directory-only patterns should only match directories."""
        path = Path("dist")
        assert should_ignore_path(path, True, ["dist/"]) is True
        assert should_ignore_path(path, False, ["dist/"]) is False

    def test_prefix_pattern(self) -> None:
        """Prefix patterns like 'dir/' should match contents."""
        path = Path("dist/assets/style.css")
        assert should_ignore_path(path, False, ["dist/"]) is True

    def test_basename_pattern_any_depth(self) -> None:
        """Basenames should match at any depth."""
        path = Path("src/vendor/foo.pyc")
        assert should_ignore_path(path, False, ["*.pyc"]) is True
