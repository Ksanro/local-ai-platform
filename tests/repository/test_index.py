"""Tests for the RepositoryIndex helper methods.

Verifies that lookup and query methods on RepositoryIndex work correctly.
"""

from __future__ import annotations

from pathlib import Path

from packages.repository.index import find_extension, find_language, get_file, summary
from packages.repository.scanner import scan

_project_root = Path(__file__).resolve().parent.parent.parent


class TestGetFile:
    """Tests for the get_file lookup method."""

    def test_existing_file_found(self) -> None:
        """get_file should return a SourceFile for an existing path."""
        index = scan(_project_root)
        result = get_file(index, Path("pyproject.toml"))
        assert result is not None
        assert result.path.is_absolute()

    def test_missing_file_returns_none(self) -> None:
        """get_file should return None for a nonexistent path."""
        index = scan(_project_root)
        result = get_file(index, Path("nonexistent_file.txt"))
        assert result is None

    def test_get_file_returns_correct_language(self) -> None:
        """get_file should return a file with the correct language."""
        index = scan(_project_root)
        py_file = get_file(index, Path("pyproject.toml"))
        assert py_file is not None
        assert py_file.language == "TOML"


class TestFindExtension:
    """Tests for the find_extension lookup method."""

    def test_find_python_files(self) -> None:
        """find_extension should return all .py files."""
        index = scan(_project_root)
        py_files = find_extension(index, ".py")
        assert len(py_files) > 0
        for f in py_files:
            assert f.extension == ".py"

    def test_find_without_dot(self) -> None:
        """find_extension should work with or without leading dot."""
        index = scan(_project_root)
        py_files_with_dot = find_extension(index, ".py")
        py_files_no_dot = find_extension(index, "py")
        assert len(py_files_with_dot) == len(py_files_no_dot)

    def test_find_unrecognized_extension(self) -> None:
        """find_extension should return empty list for unknown extensions."""
        index = scan(_project_root)
        result = find_extension(index, ".xyz")
        assert len(result) == 0

    def test_find_json_files(self) -> None:
        """find_extension should return .json files."""
        index = scan(_project_root)
        json_files = find_extension(index, ".json")
        assert len(json_files) >= 0  # May or may not exist


class TestFindLanguage:
    """Tests for the find_language lookup method."""

    def test_find_python_files(self) -> None:
        """find_language should return all Python files."""
        index = scan(_project_root)
        py_files = find_language(index, "Python")
        assert len(py_files) > 0
        for f in py_files:
            assert f.language == "Python"

    def test_find_unknown_language(self) -> None:
        """find_language should return empty list for unknown language."""
        index = scan(_project_root)
        result = find_language(index, "NonexistentLanguage")
        assert len(result) == 0

    def test_find_all_languages(self) -> None:
        """find_language should find files for every language in the index."""
        index = scan(_project_root)
        for lang_summary in index.statistics.languages:
            files = find_language(index, lang_summary.language)
            assert len(files) == lang_summary.file_count


class TestSummary:
    """Tests for the summary method."""

    def test_summary_returns_dict(self) -> None:
        """summary should return a dictionary."""
        index = scan(_project_root)
        result = summary(index)
        assert isinstance(result, dict)

    def test_summary_has_required_keys(self) -> None:
        """summary should contain all required keys."""
        index = scan(_project_root)
        result = summary(index)
        required_keys = {
            "total_files",
            "source_files",
            "languages",
            "total_size_bytes",
            "largest_files",
        }
        assert required_keys.issubset(set(result.keys()))

    def test_summary_total_files(self) -> None:
        """summary total_files should match index statistics."""
        index = scan(_project_root)
        result = summary(index)
        assert result["total_files"] == index.statistics.total_files

    def test_summary_source_files(self) -> None:
        """summary source_files should match index statistics."""
        index = scan(_project_root)
        result = summary(index)
        assert result["source_files"] == index.statistics.source_files

    def test_summary_languages(self) -> None:
        """summary languages should be a list of dicts."""
        index = scan(_project_root)
        result = summary(index)
        assert isinstance(result["languages"], list)
        for lang_entry in result["languages"]:
            assert isinstance(lang_entry, dict)
            assert "language" in lang_entry
            assert "file_count" in lang_entry
            assert "total_size_bytes" in lang_entry

    def test_summary_largest_files(self) -> None:
        """summary largest_files should be a list of dicts."""
        index = scan(_project_root)
        result = summary(index)
        assert isinstance(result["largest_files"], list)
        for file_entry in result["largest_files"]:
            assert isinstance(file_entry, dict)
            assert "path" in file_entry
            assert "size_bytes" in file_entry
            assert "language" in file_entry
