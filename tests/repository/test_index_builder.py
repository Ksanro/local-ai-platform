"""Tests for Repository Index Builder.

Tests covering:
- exclude_tests=True: test files not indexed
- exclude_tests=False: test files indexed
- excluded_test_count tracking
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from packages.repository.index.builder import RepositoryIndexBuilder
from packages.repository.symbols.python_ast import PythonAstExtractor


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _write_py_file(directory: Path, name: str, content: str) -> Path:
    """Write a Python file to a temporary directory."""
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


class TestExcludeTestsTrue:
    """Test that test files are excluded when exclude_tests=True."""

    def test_test_file_not_indexed(self):
        """A test_*.py file should not appear in index when exclude_tests=True."""
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            _write_py_file(
                p,
                "test_foo.py",
                '''"""Test module."""

def test_something():
    """A test function."""
    pass
''',
            )
            _write_py_file(
                p,
                "main.py",
                '''"""Main module."""

def main():
    """Main function."""
    pass
''',
            )

            builder = RepositoryIndexBuilder(exclude_tests=True)
            index = builder.build(p)

            # main (without .py) should be indexed
            modules = list(index.modules.keys())
            assert any("main" in m for m in modules)
            # test_foo (without .py) should NOT be indexed
            assert not any("test_foo" in m for m in modules)

    def test_conftest_not_indexed(self):
        """A conftest.py file should not appear in index when exclude_tests=True."""
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            _write_py_file(
                p,
                "conftest.py",
                '''"""Test fixtures."""

def pytest_configure():
    """Configure pytest."""
    pass
''',
            )
            _write_py_file(
                p,
                "app.py",
                '''"""App module."""

class App:
    """An app class."""
    pass
''',
            )

            builder = RepositoryIndexBuilder(exclude_tests=True)
            index = builder.build(p)

            modules = list(index.modules.keys())
            assert any("app" in m for m in modules)
            assert not any("conftest" in m for m in modules)

    def test_excluded_test_count_is_nonzero(self):
        """excluded_test_count should be non-zero when test files are skipped."""
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            _write_py_file(
                p,
                "test_foo.py",
                "def test_one(): pass\n",
            )
            _write_py_file(
                p,
                "test_bar.py",
                "def test_two(): pass\n",
            )
            _write_py_file(
                p,
                "main.py",
                "def main(): pass\n",
            )

            builder = RepositoryIndexBuilder(exclude_tests=True)
            builder.build(p)

            assert builder.excluded_test_count == 2

    def test_excluded_test_count_is_zero_when_none(self):
        """excluded_test_count should be 0 when no test files exist."""
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            _write_py_file(
                p,
                "main.py",
                "def main(): pass\n",
            )

            builder = RepositoryIndexBuilder(exclude_tests=True)
            builder.build(p)

            assert builder.excluded_test_count == 0


class TestExcludeTestsFalse:
    """Test that test files are included when exclude_tests=False."""

    def test_test_file_indexed(self):
        """A test_*.py file should appear in index when exclude_tests=False."""
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            _write_py_file(
                p,
                "test_foo.py",
                '''"""Test module."""

def test_something():
    """A test function."""
    pass
''',
            )

            builder = RepositoryIndexBuilder(exclude_tests=False)
            index = builder.build(p)

            modules = list(index.modules.keys())
            assert any("test_foo" in m for m in modules)

    def test_excluded_test_count_is_zero_when_disabled(self):
        """excluded_test_count should be 0 when exclude_tests=False."""
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            _write_py_file(
                p,
                "test_foo.py",
                "def test_one(): pass\n",
            )

            builder = RepositoryIndexBuilder(exclude_tests=False)
            builder.build(p)

            assert builder.excluded_test_count == 0


class TestPythonAstExtractorExcludedCount:
    """Test PythonAstExtractor.excluded_test_count."""

    def test_extractor_counts_excluded(self):
        """Extractor should track excluded test files."""
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            _write_py_file(
                p,
                "test_foo.py",
                "def test_one(): pass\n",
            )

            extractor = PythonAstExtractor()
            extractor.extract(p, exclude_tests=True)

            assert extractor.excluded_test_count == 1