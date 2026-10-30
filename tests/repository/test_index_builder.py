"""Tests for Repository Index Builder.

Tests covering:
- exclude_tests=True: test files not indexed
- exclude_tests=False: test files indexed
- excluded_test_count tracking
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

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


class TestModulePaths:
    """Test module path handling during directory indexing."""

    def test_duplicate_filenames_in_different_directories_are_distinct(self):
        """Directory indexing should not collapse files with the same basename."""
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            _write_py_file(
                p,
                "packages/pipeline/repository_context.py",
                "class RepositoryContextStage:\n    pass\n",
            )
            _write_py_file(
                p,
                "packages/pipeline/stages/repository_context.py",
                "class RepositoryContextStage:\n    pass\n",
            )

            builder = RepositoryIndexBuilder(exclude_tests=False)
            index = builder.build(p)

            assert "packages/pipeline/repository_context" in index.modules
            assert "packages/pipeline/stages/repository_context" in index.modules
            assert len(index.find("RepositoryContextStage")) == 2


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


class TestGeneratedCacheIsNotIndexed:
    """A tool cache under the workspace contributes no module to the index."""

    def test_uv_cache_module_not_indexed(self):
        """A ``.uv-cache`` holding real ``.py`` files still yields nothing.

        The live AST index was already blind to it - a path component beginning with
        a dot is skipped before any file is read - and the scanner's ignored-directory
        set now says so out loud.  This test pins the indexer half of that, so a
        change to either rule is noticed here rather than in a session record.
        """
        with TemporaryDirectory() as tmp:
            p = Path(tmp)
            _write_py_file(p, "main.py", '"""Main module."""\n\n\ndef main():\n    pass\n')
            _write_py_file(
                p,
                ".uv-cache/archive-v0/0HzNOif3v/ast_serialize/__init__.py",
                "def serialize(node):\n    pass\n",
            )
            _write_py_file(
                p,
                ".uv-cache/wheels/dependency/module.py",
                "VALUE = 2\n",
            )

            index = RepositoryIndexBuilder(exclude_tests=False).build(p)

            assert any("main" in module for module in index.modules)
            assert not any(".uv-cache" in module for module in index.modules)
            assert not any("ast_serialize" in module for module in index.modules)
