"""Shared probes for capability context-package tests.

Two things are easy to get wrong when a capability assembles a
``ContextPackage`` from ranked candidates, and both are checked here for every
directly executable capability:

*   Inventing relationships. ``ContextResult`` publishes ranked candidates.
    Their order and their modules are facts about retrieval, not facts about
    which symbol calls which, so ``related_callers`` and ``related_callees``
    must stay empty and the counts must agree with them.
*   Serializer availability. ``SerializerFactory.create(ProviderType.openai)``
    only works if the built-in serializer is registered. Registration has to
    come from the capability's own documented import path, not from a test
    fixture that imported a serializer module first, so the check below runs in
    a separate interpreter.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from packages.context.context_package import ContextPackage
from packages.context.models import (
    ContextBudgetResult,
    ContextCandidate,
    ContextResult,
)
from packages.repository.index.models import RepositoryIndex

if TYPE_CHECKING:
    from collections.abc import Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Prefix of the single JSON line the fresh-interpreter script prints.
RESULT_PREFIX = "RESULT "


def candidate(
    qualified_name: str,
    module: str,
    score: float = 100.0,
) -> ContextCandidate:
    """Build one ranked candidate for an assembly probe."""
    return ContextCandidate(
        symbol_id=qualified_name,
        qualified_name=qualified_name,
        module=module,
        score=score,
    )


def context_result(candidates: Sequence[ContextCandidate]) -> ContextResult:
    """Wrap candidates in a ``ContextResult`` with a proportional budget."""
    modules = sorted({item.module for item in candidates})
    return ContextResult(
        candidates=list(candidates),
        selected_modules=modules,
        budget=ContextBudgetResult(
            estimated_tokens=128 * len(candidates),
            estimated_symbols=len(candidates),
            estimated_modules=len(modules),
            within_budget=True,
            truncated=False,
        ),
    )


def assert_relationship_honesty(
    capability: Any,
    candidates: Sequence[ContextCandidate],
) -> ContextPackage:
    """Assemble a package and prove the capability invented nothing.

    The primary symbol is the first candidate, the rest stay supporting symbols
    in rank order without duplicates, both relationship lists stay empty,
    ``related_modules`` is the sorted set of candidate modules, and every count
    in the relationship summary matches the list it describes.
    """
    package = capability._stage_assemble_package(
        context_result(candidates),
        RepositoryIndex(),
    )

    expected_supporting: list[str] = []
    seen: set[str] = set()
    for position, item in enumerate(candidates):
        if position == 0:
            seen.add(item.qualified_name)
            continue
        if item.qualified_name not in seen:
            seen.add(item.qualified_name)
            expected_supporting.append(item.qualified_name)

    assert package.primary_symbol == (
        candidates[0].qualified_name if candidates else ""
    )
    assert package.supporting_symbols == expected_supporting
    assert package.related_callers == []
    assert package.related_callees == []
    assert package.related_modules == sorted(
        {item.module for item in candidates}
    )

    summary = package.relationship_summary
    assert summary.caller_count == len(package.related_callers)
    assert summary.callee_count == len(package.related_callees)
    assert summary.module_count == len(package.related_modules)
    assert summary.symbol_count == len(seen)
    return package


#: Script run by ``run_in_fresh_interpreter``. The placeholders name the
#: capability module and class, imported exactly the way the docs show them.
FRESH_INTERPRETER_SCRIPT = r"""
import json
import sys

sys.path.insert(0, sys.argv[1])

serializer_module_before = "packages.serializers.openai" in sys.modules

from packages.capabilities.__MODULE__ import __CLASS__

# Measured straight after the documented capability import, before any
# serializers module is touched, so the flag below can only come from here.
serializer_module_after_import = "packages.serializers.openai" in sys.modules

from packages.repository.index.models import RepositoryIndex, RepositoryStatistics
from packages.repository.symbols.models import Module, Symbol, SymbolType
from packages.serializers.registry import has_serializer
from packages.serializers.types import ProviderType

registered = has_serializer(ProviderType.openai)

SOURCE = "def should_retry(attempt, policy):\n    return attempt\n"
PATHS = ["gateway/retry.py", "gateway/alt_retry.py", "gateway/more_retry.py"]

symbols = [
    Symbol(
        id=path[:-3].replace("/", ".") + ".should_retry",
        name="should_retry",
        qualified_name=path[:-3].replace("/", ".") + ".should_retry",
        symbol_type=SymbolType.FUNCTION,
        module=path,
        lineno=1,
    )
    for path in PATHS
]
modules = {
    path: Module(path=path, symbols=[symbol], source=SOURCE)
    for path, symbol in zip(PATHS, symbols)
}
index = RepositoryIndex(
    modules=modules,
    _symbols=symbols,
    _relationships=[],
    _statistics=RepositoryStatistics(
        module_count=len(modules),
        function_count=len(symbols),
        symbol_count=len(symbols),
    ),
)

result = __CLASS__().execute(query="retry policy", repository_index=index)
package = result.context_package
request = result.provider_request
print(
    "RESULT "
    + json.dumps(
        {
            "serializer_module_before": serializer_module_before,
            "serializer_module_after_import": serializer_module_after_import,
            "registered": registered,
            "primary": package.primary_symbol,
            "supporting": package.supporting_symbols,
            "callers": package.related_callers,
            "callees": package.related_callees,
            "modules": package.related_modules,
            "caller_count": package.relationship_summary.caller_count,
            "callee_count": package.relationship_summary.callee_count,
            "provider": request.provider_type.value,
            "roles": [message["role"] for message in request.messages],
            "context": request.messages[0]["content"],
        }
    )
)
"""


def run_in_fresh_interpreter(module_name: str, class_name: str) -> dict[str, Any]:
    """Execute one capability in its own interpreter and return its payload.

    The subprocess imports nothing but the documented capability path, so a
    serializer registration that only works because some test module imported
    it first fails here instead of passing.
    """
    script = FRESH_INTERPRETER_SCRIPT.replace(
        "__MODULE__", module_name
    ).replace("__CLASS__", class_name)
    completed = subprocess.run(
        [sys.executable, "-c", script, str(REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        check=False,
    )

    assert completed.returncode == 0, completed.stderr

    for line in completed.stdout.splitlines():
        if line.startswith(RESULT_PREFIX):
            return json.loads(line.removeprefix(RESULT_PREFIX))
    raise AssertionError(f"no RESULT line in:\n{completed.stdout}")


def assert_fresh_execution_is_honest(payload: dict[str, Any]) -> None:
    """Prove one fresh-interpreter run serialized and invented nothing."""
    # The documented import path, not the test, made the serializer available.
    assert payload["serializer_module_before"] is False
    assert payload["serializer_module_after_import"] is True
    assert payload["registered"] is True
    assert payload["provider"] == "openai"
    assert payload["roles"] == ["system", "user"]
    # Three modules sharing one symbol name: retrieval, never a call graph.
    assert payload["primary"] == "gateway.retry.should_retry"
    assert payload["supporting"] == [
        "gateway.alt_retry.should_retry",
        "gateway.more_retry.should_retry",
    ]
    assert payload["modules"] == [
        "gateway/alt_retry.py",
        "gateway/more_retry.py",
        "gateway/retry.py",
    ]
    assert payload["callers"] == []
    assert payload["callees"] == []
    assert payload["caller_count"] == 0
    assert payload["callee_count"] == 0
    assert "0 callers, 0 callees" in payload["context"]
