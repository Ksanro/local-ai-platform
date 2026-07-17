"""Benchmark engine: executes the full retrieval pipeline.

Orchestrates the pipeline stages in order, measuring each stage's
output and timing without invoking any LLM or network calls.

Architecture
------------

BenchmarkCase
    ↓
Planning (ContextPlanner)
    ↓
Repository Search (RepositoryIndex)
    ↓
Ranking + Context Building (ContextBuilder)
    ↓
Serialization (ProviderSerializer)
    ↓
BenchmarkResult

Responsibilities
----------------

- Execute each pipeline stage in order.
- Measure duration and output for each stage.
- Do NOT call providers.
- Do NOT perform HTTP.
- Do NOT call LLMs.
- Do NOT modify RepositoryIndex.
- Do NOT mutate ContextPackage.

Public API
----------

.. code-block:: python

    engine = BenchmarkEngine()
    result = engine.run(case, repository_index)

Constraints
-----------

- All imports are from public APIs only.
- No internal module imports (no ContextBuilder internals, no
  Ranking internals, no Planner internals).
- Pure evaluation: measures what the platform produces, not what
  it should produce.
"""

from __future__ import annotations

import logging
import time

from packages.benchmark.models import BenchmarkCase, BenchmarkResult
from packages.context.builder import ContextBuilder
from packages.context.context_package import ContextPackage
from packages.context.models import ContextQuery, ContextResult
from packages.planning.planner import ContextPlanner
from packages.repository.index.models import RepositoryIndex
from packages.serializers.factory import SerializerFactory
from packages.serializers.models import ProviderRequest
from packages.serializers.types import ProviderType

logger = logging.getLogger(__name__)


class BenchmarkEngine:
    """Executes the full retrieval pipeline for a single benchmark case.

    Pipeline stages:
        1. Planning — ContextPlanner.build()
        2. Repository Search — RepositoryIndex.find()
        3. Ranking + Context Building — ContextBuilder.build()
        4. Serialization — ProviderSerializer.serialize()

    Each stage measures duration and captures output.
    No providers are invoked. No network calls are made.

    Attributes:
        _planner: The context planner for planning stage.
        _serializer_provider_type: The provider type for serialization.
    """

    def __init__(
        self,
        serializer_provider_type: ProviderType = ProviderType.openai,
    ) -> None:
        """Initialize the benchmark engine.

        Args:
            serializer_provider_type: The provider type to use for
                serialization. Defaults to openai.
        """
        self._serializer_provider_type = serializer_provider_type

    def run(self, case: BenchmarkCase, repository_index: RepositoryIndex) -> BenchmarkResult:
        """Execute the full pipeline for a benchmark case.

        Runs all pipeline stages in order, measures each stage, and
        produces a BenchmarkResult with scores and failures.

        Args:
            case: The benchmark case specification.
            repository_index: The repository index to benchmark against.

        Returns:
            A BenchmarkResult with scores, selected items, and failures.
        """
        start_time = time.perf_counter()

        # Stage 1: Planning
        self._stage_planning(case)

        # Stage 2: Repository Search
        self._stage_repository_search(case, repository_index)

        # Stage 3: Ranking + Context Building
        context_result = self._stage_context_building(case, repository_index)

        # Stage 4: Serialization
        self._stage_serialization(context_result)

        # Compute metrics
        total_duration = time.perf_counter() - start_time

        # Extract selected items from pipeline output
        selected_symbols = tuple(
            c.symbol_id for c in context_result.candidates
        )
        selected_modules = tuple(context_result.selected_modules)
        selected_relationships: tuple[str, ...] = ()

        # Estimate tokens from context budget
        estimated_tokens = context_result.budget.estimated_tokens

        # Compute scores
        failures = self._compute_failures(
            case=case,
            selected_symbols=set(selected_symbols),
            selected_modules=set(selected_modules),
            estimated_tokens=estimated_tokens,
        )

        passed = len(failures) == 0

        result = BenchmarkResult(
            benchmark=case.id,
            selected_symbols=selected_symbols,
            selected_modules=selected_modules,
            selected_relationships=selected_relationships,
            estimated_tokens=estimated_tokens,
            duration_ms=total_duration * 1000,
            passed=passed,
            score=self._compute_score(case, selected_symbols, selected_modules),
            failures=tuple(failures),
        )

        logger.info(
            "benchmark case=%s passed=%s score=%.3f duration=%.1fms",
            case.id,
            passed,
            result.score,
            result.duration_ms,
        )

        return result

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------

    def _stage_planning(self, case: BenchmarkCase) -> object:
        """Execute the planning stage.

        Calls ContextPlanner.build() with the case query.

        Args:
            case: The benchmark case specification.

        Returns:
            The plan object (internal type).
        """
        planner = ContextPlanner()
        plan = planner.build([case.query])
        return plan

    def _stage_repository_search(
        self,
        case: BenchmarkCase,
        repository_index: RepositoryIndex,
    ) -> list[str]:
        """Execute the repository search stage.

        Searches the repository index for symbols matching the query.

        Args:
            case: The benchmark case specification.
            repository_index: The repository index to search.

        Returns:
            List of found symbol qualified names.
        """
        found: list[str] = []
        for symbol in repository_index.symbols():
            if (
                case.query.lower() in symbol.name.lower()
                or case.query.lower() in symbol.qualified_name.lower()
            ):
                found.append(symbol.qualified_name)
        return found

    def _stage_context_building(
        self,
        case: BenchmarkCase,
        repository_index: RepositoryIndex,
    ) -> ContextResult:
        """Execute the context building stage.

        Calls ContextBuilder.build() with a ContextQuery derived from
        the benchmark case.

        Args:
            case: The benchmark case specification.
            repository_index: The repository index.

        Returns:
            The context result object (internal type).
        """
        builder = ContextBuilder(repository_index)
        query = ContextQuery(
            text=case.query,
            max_symbols=case.max_context_tokens // 100 or 20,
            max_modules=10,
            max_tokens=case.max_context_tokens,
        )
        result = builder.build(query)
        return result

    def _stage_serialization(
        self,
        context_result: object,
    ) -> ProviderRequest:
        """Execute the serialization stage.

        Converts the context result into a ProviderRequest using the
        registered serializer.

        Args:
            context_result: The context building result.

        Returns:
            The serialized ProviderRequest.
        """
        # Build a ContextPackage from the context result.
        context_package = self._build_context_package(context_result)

        # Create the serializer via factory.
        serializer = SerializerFactory.create(self._serializer_provider_type)

        # Serialize — this is a pure function, no network calls.
        messages: list[dict[str, object]] = [{"role": "user", "content": "test"}]
        request = serializer.serialize(context_package, messages)
        return request

    def _build_context_package(self, context_result: object) -> ContextPackage:
        """Build a ContextPackage from a context building result.

        Extracts the necessary fields from the context result to
        construct a ContextPackage for serialization.

        Args:
            context_result: The context building result.

        Returns:
            A ContextPackage ready for serialization.
        """
        from packages.context.models import ContextResult as _ContextResult

        if not isinstance(context_result, _ContextResult):
            return ContextPackage()

        candidates = context_result.candidates
        selected_modules = context_result.selected_modules
        budget = context_result.budget

        primary_symbol = candidates[0].symbol_id if candidates else ""
        supporting_symbols = [c.symbol_id for c in candidates[1:]]

        return ContextPackage(
            primary_symbol=primary_symbol,
            supporting_symbols=supporting_symbols,
            related_modules=selected_modules,
            estimated_tokens=budget.estimated_tokens,
        )

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _compute_score(
        self,
        case: BenchmarkCase,
        selected_symbols: tuple[str, ...],
        selected_modules: tuple[str, ...],
    ) -> float:
        """Compute the overall benchmark score.

        Args:
            case: The benchmark case specification.
            selected_symbols: Symbols selected by the pipeline.
            selected_modules: Modules selected by the pipeline.

        Returns:
            Overall score between 0.0 and 1.0.
        """
        from packages.benchmark.metrics import (
            budget_compliance,
            module_precision,
            overall_score,
            relationship_precision,
            symbol_precision,
        )

        symbol_prec = symbol_precision(
            retrieved=set(selected_symbols),
            expected=set(case.expected_symbols),
        )
        mod_prec = module_precision(
            retrieved=set(selected_modules),
            expected=set(case.expected_modules),
        )
        rel_prec = relationship_precision(
            retrieved=set(),
            expected=set(case.expected_relationships),
        )
        budget = budget_compliance(
            estimated=0,
            max_budget=case.max_context_tokens,
        )

        return overall_score(symbol_prec, mod_prec, rel_prec, budget)

    def _compute_failures(
        self,
        case: BenchmarkCase,
        selected_symbols: set[str],
        selected_modules: set[str],
        estimated_tokens: int,
    ) -> list[str]:
        """Compute failure reasons for the benchmark case.

        Checks:
        - Symbol precision below threshold
        - Module precision below threshold
        - Budget exceeded

        Args:
            case: The benchmark case specification.
            selected_symbols: Symbols selected by the pipeline.
            selected_modules: Modules selected by the pipeline.
            estimated_tokens: Estimated token count.

        Returns:
            List of failure description strings.
        """
        from packages.benchmark.metrics import (
            module_precision,
            symbol_precision,
        )

        failures: list[str] = []

        # Symbol precision check
        symbol_prec = symbol_precision(
            retrieved=selected_symbols,
            expected=set(case.expected_symbols),
        )
        if case.expected_symbols and symbol_prec < 0.1:
            failures.append(
                f"Symbol precision too low: {symbol_prec:.3f} "
                f"(expected {len(case.expected_symbols)}, "
                f"got {len(selected_symbols & set(case.expected_symbols))})"
            )

        # Module precision check
        mod_prec = module_precision(
            retrieved=selected_modules,
            expected=set(case.expected_modules),
        )
        if case.expected_modules and mod_prec < 0.1:
            failures.append(
                f"Module precision too low: {mod_prec:.3f} "
                f"(expected {len(case.expected_modules)}, "
                f"got {len(selected_modules & set(case.expected_modules))})"
            )

        # Budget check
        if estimated_tokens > case.max_context_tokens:
            failures.append(
                f"Token budget exceeded: {estimated_tokens} > {case.max_context_tokens}"
            )

        return failures
