"""Tests for the repository scanner.

Uses the current project directory as test data to verify that the
scanner correctly walks directories, detects languages, and computes
statistics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.repository.models import (
    LanguageSummary,
    RepositoryIndex,
    SourceFile,
)
from packages.repository.scanner import scan

_project_root = Path(__file__).resolve().parent.parent.parent

# Use the project root as the test data directory.
_TEST_ROOT = _project_root


class TestScanBasic:
    """Tests for basic scan functionality."""

    def test_scan_returns_repository_index(self) -> None:
        """Scan should return a RepositoryIndex instance."""
        index = scan(_TEST_ROOT)
        assert isinstance(index, RepositoryIndex)

    def test_scan_root_is_resolved(self) -> None:
        """Scan should resolve the root path to an absolute path."""
        index = scan(_TEST_ROOT)
        assert index.root.is_absolute()

    def test_scan_finds_files(self) -> None:
        """Scan should discover files in the repository."""
        index = scan(_TEST_ROOT)
        assert len(index.files) > 0

    def test_scan_finds_directories(self) -> None:
        """Scan should discover directories in the repository."""
        index = scan(_TEST_ROOT)
        assert len(index.directories) > 0

    def test_scan_nonexistent_path_raises(self) -> None:
        """Scan should raise FileNotFoundError for nonexistent paths."""
        with pytest.raises(FileNotFoundError):
            scan(Path("/nonexistent/path/that/does/not/exist"))

    def test_scan_file_raises(self) -> None:
        """Scan should raise NotADirectoryError when given a file."""
        with pytest.raises(NotADirectoryError):
            scan(_TEST_ROOT / "pyproject.toml")


class TestScanIgnoredDirectories:
    """Tests that ignored directories are skipped."""

    def test_node_modules_skipped(self) -> None:
        """node_modules/ should not appear in scan results."""
        # Create a temporary node_modules directory to test.
        test_dir = _TEST_ROOT / "node_modules"
        test_dir.mkdir(exist_ok=True)
        try:
            index = scan(_TEST_ROOT)
            for d in index.directories:
                assert d.relative_path.name != "node_modules"
        finally:
            import shutil
            if test_dir.exists():
                shutil.rmtree(test_dir)

    def test_venv_skipped(self) -> None:
        """venv/ should not appear in scan results."""
        test_dir = _TEST_ROOT / "venv"
        test_dir.mkdir(exist_ok=True)
        try:
            index = scan(_TEST_ROOT)
            for d in index.directories:
                assert d.relative_path.name != "venv"
        finally:
            import shutil
            if test_dir.exists():
                shutil.rmtree(test_dir)

    def test_pycache_skipped(self) -> None:
        """__pycache__/ should not appear in scan results."""
        test_dir = _TEST_ROOT / "__pycache__"
        test_dir.mkdir(exist_ok=True)
        try:
            index = scan(_TEST_ROOT)
            for d in index.directories:
                assert d.relative_path.name != "__pycache__"
        finally:
            import shutil
            if test_dir.exists():
                shutil.rmtree(test_dir)

    def test_git_directory_skipped(self) -> None:
        """.git/ should not appear in scan results."""
        index = scan(_TEST_ROOT)
        for d in index.directories:
            assert d.relative_path.name != ".git"


class TestScanLanguageDetection:
    """Tests for language detection during scanning."""

    def test_python_files_detected(self) -> None:
        """Python files should be detected as 'Python'."""
        index = scan(_TEST_ROOT)
        python_files = [f for f in index.files if f.language == "Python"]
        assert len(python_files) > 0
        for f in python_files:
            assert f.extension == ".py"

    def test_all_files_have_language(self) -> None:
        """Every file should have a language assigned."""
        index = scan(_TEST_ROOT)
        for f in index.files:
            assert f.language is not None
            assert isinstance(f.language, str)
            assert len(f.language) > 0

    def test_unknown_language_for_unrecognized(self) -> None:
        """Files with unrecognized extensions should be 'Unknown'."""
        test_dir = _TEST_ROOT / "test_unknown_ext_tmp"
        test_dir.mkdir(exist_ok=True)
        try:
            test_file = test_dir / "data.xyz"
            test_file.write_text("test content")
            index = scan(_TEST_ROOT)
            rel = test_file.relative_to(_TEST_ROOT)
            unknown = [f for f in index.files if f.relative_path == rel]
            assert len(unknown) == 1
            assert unknown[0].language == "Unknown"
        finally:
            import shutil
            if test_dir.exists():
                shutil.rmtree(test_dir)


class TestScanStatistics:
    """Tests for computed statistics."""

    def test_statistics_total_files(self) -> None:
        """Statistics should include total file count."""
        index = scan(_TEST_ROOT)
        assert index.statistics.total_files == len(index.files)

    def test_statistics_source_files(self) -> None:
        """Statistics should count files with known languages."""
        index = scan(_TEST_ROOT)
        assert index.statistics.source_files <= index.statistics.total_files

    def test_statistics_languages(self) -> None:
        """Statistics should include a languages breakdown."""
        index = scan(_TEST_ROOT)
        assert len(index.statistics.languages) > 0
        for lang in index.statistics.languages:
            assert isinstance(lang, LanguageSummary)
            assert lang.file_count > 0
            assert lang.total_size_bytes > 0

    def test_statistics_largest_files(self) -> None:
        """Statistics should include top 10 largest files."""
        index = scan(_TEST_ROOT)
        assert len(index.statistics.largest_files) <= 10
        for f in index.statistics.largest_files:
            assert isinstance(f, SourceFile)

    def test_statistics_total_size(self) -> None:
        """Statistics total_size_bytes should match sum of all file sizes."""
        index = scan(_TEST_ROOT)
        expected = sum(f.size_bytes for f in index.files)
        assert index.statistics.total_size_bytes == expected

    def test_statistics_languages_sum(self) -> None:
        """Sum of language file counts should equal source_files."""
        index = scan(_TEST_ROOT)
        total_source = sum(ls.file_count for ls in index.statistics.languages)
        assert total_source == index.statistics.source_files


class TestScanPerformance:
    """Tests for scan performance."""

    def test_scan_completes_under_one_second(self) -> None:
        """Scan should complete in under 1 second for a normal project."""
        import time

        start = time.perf_counter()
        scan(_TEST_ROOT)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Scan took {elapsed:.2f}s, expected < 1s"
