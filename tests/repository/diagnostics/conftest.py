"""Shared fixtures for diagnostics tests."""

from __future__ import annotations

import pytest

from packages.repository.diagnostics.analyzers.dead_code import DeadCodeAnalyzer
from packages.repository.diagnostics.analyzers.graph_statistics import GraphStatisticsAnalyzer
from packages.repository.diagnostics.analyzers.orphan import OrphanAnalyzer
from packages.repository.diagnostics.analyzers.statistics import ModuleStatisticsAnalyzer
from packages.repository.diagnostics.engine import DiagnosticsEngine
from packages.repository.index.models import RepositoryIndex, RepositoryStatistics
from packages.repository.symbols.models import (
    Module,
    Relationship,
    RelationshipType,
    Symbol,
    SymbolType,
)


@pytest.fixture
def empty_index() -> RepositoryIndex:
    """Return an empty RepositoryIndex."""
    return RepositoryIndex()


@pytest.fixture
def simple_index() -> RepositoryIndex:
    """Return a RepositoryIndex with a simple call graph.

    Structure:
        module_a.py:
            - func_a (FUNCTION)
            - func_b (FUNCTION) - called by func_a
        module_b.py:
            - func_c (FUNCTION) - never called

    Relationships:
        func_a -> func_b (CALLS)
    """
    func_a = Symbol(
        id="module_a.func_a",
        name="func_a",
        qualified_name="module_a.func_a",
        symbol_type=SymbolType.FUNCTION,
        module="module_a.py",
        lineno=1,
    )
    func_b = Symbol(
        id="module_a.func_b",
        name="func_b",
        qualified_name="module_a.func_b",
        symbol_type=SymbolType.FUNCTION,
        module="module_a.py",
        lineno=5,
    )
    func_c = Symbol(
        id="module_b.func_c",
        name="func_c",
        qualified_name="module_b.func_c",
        symbol_type=SymbolType.FUNCTION,
        module="module_b.py",
        lineno=1,
    )

    call_a_b = Relationship(
        source="module_a.func_a",
        target="module_a.func_b",
        type=RelationshipType.CALLS,
    )

    modules = {
        "module_a.py": Module(
            path="module_a.py",
            symbols=[func_a, func_b],
            relationships=[call_a_b],
        ),
        "module_b.py": Module(
            path="module_b.py",
            symbols=[func_c],
            relationships=[],
        ),
    }

    stats = RepositoryStatistics(
        module_count=2,
        class_count=0,
        function_count=3,
        method_count=0,
        symbol_count=3,
    )

    return RepositoryIndex(
        modules=modules,
        _symbols=[func_a, func_b, func_c],
        _relationships=[call_a_b],
        _statistics=stats,
    )


@pytest.fixture
def orphan_index() -> RepositoryIndex:
    """Return a RepositoryIndex with orphan modules.

    Structure:
        main.py - connected (imports utils.py)
        utils.py - connected (imported by main.py)
        orphan.py - orphaned (no connections)
    """
    main_sym = Symbol(
        id="main",
        name="main",
        qualified_name="main",
        symbol_type=SymbolType.MODULE,
        module="main.py",
        lineno=1,
    )
    utils_sym = Symbol(
        id="utils",
        name="utils",
        qualified_name="utils",
        symbol_type=SymbolType.MODULE,
        module="utils.py",
        lineno=1,
    )
    orphan_sym = Symbol(
        id="orphan",
        name="orphan",
        qualified_name="orphan",
        symbol_type=SymbolType.MODULE,
        module="orphan.py",
        lineno=1,
    )

    import_main_utils = Relationship(
        source="main",
        target="utils",
        type=RelationshipType.IMPORTS,
    )

    modules = {
        "main.py": Module(
            path="main.py",
            symbols=[main_sym],
            relationships=[import_main_utils],
        ),
        "utils.py": Module(
            path="utils.py",
            symbols=[utils_sym],
            relationships=[],
        ),
        "orphan.py": Module(
            path="orphan.py",
            symbols=[orphan_sym],
            relationships=[],
        ),
    }

    stats = RepositoryStatistics(
        module_count=3,
        class_count=0,
        function_count=0,
        method_count=0,
        symbol_count=3,
    )

    return RepositoryIndex(
        modules=modules,
        _symbols=[main_sym, utils_sym, orphan_sym],
        _relationships=[import_main_utils],
        _statistics=stats,
    )


@pytest.fixture
def full_index() -> RepositoryIndex:
    """Return a RepositoryIndex with a realistic structure.

    Structure:
        package/
            __init__.py
            core.py - has ClassA with method run, function helper
            utils.py - has function format_data
            orphan_module.py - orphaned module

        Relationships:
            core imports utils
            ClassA.run calls helper (CALLS)
            ClassA.run calls format_data (CALLS)
    """
    # Symbols
    pkg_init = Symbol(
        id="package",
        name="package",
        qualified_name="package",
        symbol_type=SymbolType.MODULE,
        module="package/__init__.py",
        lineno=1,
    )
    core_main = Symbol(
        id="package.core.ClassA",
        name="ClassA",
        qualified_name="package.core.ClassA",
        symbol_type=SymbolType.CLASS,
        module="package/core.py",
        lineno=1,
    )
    core_run = Symbol(
        id="package.core.ClassA.run",
        name="run",
        qualified_name="package.core.ClassA.run",
        symbol_type=SymbolType.METHOD,
        module="package/core.py",
        lineno=5,
        decorators=["@abstractmethod"],
    )
    core_helper = Symbol(
        id="package.core.helper",
        name="helper",
        qualified_name="package.core.helper",
        symbol_type=SymbolType.FUNCTION,
        module="package/core.py",
        lineno=10,
    )
    utils_format = Symbol(
        id="package.utils.format_data",
        name="format_data",
        qualified_name="package.utils.format_data",
        symbol_type=SymbolType.FUNCTION,
        module="package/utils.py",
        lineno=1,
    )
    orphan_mod = Symbol(
        id="package.orphan_module",
        name="orphan_module",
        qualified_name="package.orphan_module",
        symbol_type=SymbolType.MODULE,
        module="package/orphan_module.py",
        lineno=1,
    )
    orphan_func = Symbol(
        id="package.orphan_module.orphan_func",
        name="orphan_func",
        qualified_name="package.orphan_module.orphan_func",
        symbol_type=SymbolType.FUNCTION,
        module="package/orphan_module.py",
        lineno=5,
    )

    # Relationships
    import_core_utils = Relationship(
        source="package.core",
        target="package.utils",
        type=RelationshipType.IMPORTS,
    )
    call_helper = Relationship(
        source="package.core.ClassA.run",
        target="package.core.helper",
        type=RelationshipType.CALLS,
    )
    call_format = Relationship(
        source="package.core.ClassA.run",
        target="package.utils.format_data",
        type=RelationshipType.CALLS,
    )

    modules = {
        "package/__init__.py": Module(
            path="package/__init__.py",
            symbols=[pkg_init],
            relationships=[],
        ),
        "package/core.py": Module(
            path="package/core.py",
            symbols=[core_main, core_run, core_helper],
            relationships=[call_helper],
        ),
        "package/utils.py": Module(
            path="package/utils.py",
            symbols=[utils_format],
            relationships=[import_core_utils],
        ),
        "package/orphan_module.py": Module(
            path="package/orphan_module.py",
            symbols=[orphan_mod, orphan_func],
            relationships=[],
        ),
    }

    stats = RepositoryStatistics(
        module_count=4,
        class_count=1,
        function_count=3,
        method_count=1,
        symbol_count=7,
    )

    return RepositoryIndex(
        modules=modules,
        _symbols=[
            pkg_init, core_main, core_run, core_helper,
            utils_format, orphan_mod, orphan_func,
        ],
        _relationships=[import_core_utils, call_helper, call_format],
        _statistics=stats,
    )


@pytest.fixture
def engine() -> DiagnosticsEngine:
    """Return a DiagnosticsEngine with all analyzers registered."""
    e = DiagnosticsEngine()
    e.register(DeadCodeAnalyzer())
    e.register(OrphanAnalyzer())
    e.register(ModuleStatisticsAnalyzer())
    e.register(GraphStatisticsAnalyzer())
    return e
