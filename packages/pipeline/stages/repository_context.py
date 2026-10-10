"""Repository context pipeline stage.

Assembles repository context for the request by orchestrating the
Context Builder pipeline (Builder -> Ranking -> Budget -> Composer)
and attaching the resulting ContextPackage to the PipelineContext.

Architecture
------------

PipelineContext
       |
       v
RepositoryContextStage
       |
       |-- ContextBuilder   (enumerate & rank symbols)
       |-- RankingEngine    (integrated inside Builder)
       |-- ContextBudget    (integrated inside Builder)
       +-- ContextComposer  (assembles structured package)
       |
       v
PipelineContext.context_package

The stage is provider-agnostic. It never performs inference.

Constraints
-----------

The stage

must not

- call providers
- inspect provider configuration
- access Gateway internals

Serializes only into ``ProviderRequest`` -- never raw JSON or HTTP payloads.

It orchestrates existing Context components only.

Delta context injection
-----------------------

When ``context_delta_injection`` is enabled (the default), the stage tracks
which symbols have already been sent in a multi-turn conversation.  On each
turn it:

1. Computes a SHA-256 key from **user messages only** (the prefix, excluding
   the new user turn).  Assistant replies are invisible to the key.
2. Looks up already-sent symbols from an LRU cache.
3. Filters out already-sent supporting symbols while always keeping the
   primary symbol.
4. Stores the union of already-sent + new symbols under the **same key** so
   the next turn can find it.

This eliminates redundant re-injection of the same symbols across turns.
When disabled the stage behaves exactly as before.

Change-aware ranking
--------------------

When a ``changed_files`` source is supplied (opt-in, off by default), the
stage reads the bounded set of index module keys for locally modified files
once per request and forwards it to the ranking engine, which adds one flat
bonus to symbols that already match the query.  The read is a cache lookup:
with the gateway's startup prime and its background refresher, no request path
ever reaches Git, and a source that raises degrades to an empty set instead of
breaking the request.  Only counts are logged - never paths.

Promotion observability
~~~~~~~~~~~~~~~~~~~~~~~

The signal is worth measuring only if "the bonus was sent" can be told apart
from "the bonus changed what was sent".  So the stage builds a **counterfactual
baseline**: the same query, the same index, the same chars-per-token, the same
already-sent set, and no changed modules.  That baseline is composed, compared
and dropped - it is never serialized, never attached to the context, never
stored in the tracker and never leaves this method.  Because a second full build
roughly doubles the stage on a dirty tree - measured on this repository's real
index of 328 modules with 8 changed, about 50 ms becomes about 105 ms - it is
built only when ``ContextResult.changed_bonus_count`` says the ranking pass
actually gave the bonus to a candidate.  That count is the exact condition: the
bonus is the only thing ``changed_modules`` influences, so with zero bonus
candidates the two arms cannot differ.

``changed_file_promotion_counts`` turns the pair into count-only fields that
ride along in the stage result and land in every session record:
``changed_files_signal``, ``changed_files_count``, ``changed_symbols_selected``,
``changed_primary_promoted``, ``changed_symbols_promoted``,
``changed_context_differs`` and ``changed_baseline_status``.
``changed_symbols_selected`` says how many of the sent symbols *carry* the
working-tree bonus.  ``changed_context_differs`` is the measurement itself: the
sent package is not equal to the baseline package, which covers order,
membership, the primary and trimmed or enriched content.  The two
``*_promoted`` fields are detail on top of it - whether the primary differs, and
how many sent symbols are missing from the baseline's sent set - so a request
whose supporting symbols merely swapped places reads as
``changed_context_differs=True`` with both detail fields at ``False``/``0``.
``changed_baseline_status`` states which of those readings applies: ``"none"``
(nothing to compare), ``"built"`` (compared), ``"skipped_no_bonus"`` (the bonus
touched no candidate, so the arms are identical by construction), or ``"failed"``
(the comparison could not be built, which is unmeasurable rather than inert).
A dirty file that was already going to be sent therefore reports a count above
zero and a difference of false, which is the distinction a review could not make
before.

Counting happens on the final composed package, so a bonus-carrying symbol that
the budget trimmed or delta injection suppressed is neither selected nor
promoted.  With no changed modules the baseline is skipped entirely and the
promotion fields stay inert; the duration of a baseline build that was made is
reported as ``changed_baseline_ms`` on the log line so its cost is visible.  A
stage that composes nothing still reports the signal state it read, or
``unavailable`` when it failed before reading it, so a degraded request never
records as a disabled feature.  No path, module name, symbol name or Git output
is ever logged or recorded.

Public API
----------

.. code-block:: python

    from packages.pipeline.stages.repository_context import RepositoryContextStage

    stage = RepositoryContextStage(index=index)
    result = await stage.execute(context)
"""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Mapping, Sequence
from typing import Any, Final

from packages.context.budget import CHARS_PER_TOKEN
from packages.context.builder import ContextBuilder
from packages.context.composer import ContextComposer
from packages.context.context_package import ContextPackage
from packages.context.delta import (
    SentSymbolTracker,
    collect_all_symbols,
    conversation_key,
    filter_candidates,
    store_key,
)
from packages.context.models import ContextCandidate, ContextQuery
from packages.context.scoring import RankingReason
from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.result import PipelineStageResult
from packages.pipeline.user_messages import select_context_query_text
from packages.repository.changed_files import ChangedModuleSource
from packages.repository.index.models import RepositoryIndex
from packages.serializers.factory import SerializerFactory
from packages.serializers.openai import OpenAISerializer  # noqa: F401 - auto-registers
from packages.serializers.types import ProviderType

logger = logging.getLogger(__name__)

#: The three states the change-aware signal can be in for one request.  They are
#: reported as a word so a disabled feature, a clean tree and a failed Git read
#: are distinguishable without a single path crossing the boundary.
SIGNAL_OFF: Final = "off"
SIGNAL_OK: Final = "ok"
SIGNAL_UNAVAILABLE: Final = "unavailable"

#: The four states of the counterfactual comparison itself.  They exist because
#: "the bonus changed nothing" and "the comparison could not be made" are
#: different answers, and only one of them is a measurement.
BASELINE_NONE: Final = "none"
BASELINE_BUILT: Final = "built"
BASELINE_SKIPPED_NO_BONUS: Final = "skipped_no_bonus"
BASELINE_FAILED: Final = "failed"

#: The promotion fields as the stage states them when the signal did nothing.
#: This is the single source of truth: the stage, the gateway mapping and the
#: session record all start here, so no caller can invent an extra field and
#: none can guess a default.  ``changed_files_signal`` is ``SIGNAL_OFF`` because
#: on those paths the signal was never consulted; a stage that ran and reported
#: the state it read overwrites it.
INERT_PROMOTION: Final[Mapping[str, Any]] = {
    "changed_files_count": 0,
    "changed_symbols_selected": 0,
    "changed_primary_promoted": False,
    "changed_symbols_promoted": 0,
    "changed_context_differs": False,
    "changed_baseline_status": BASELINE_NONE,
    "changed_files_signal": SIGNAL_OFF,
}

#: One promotion fragment, so the three log lines cannot drift apart.
_PROMOTION_LOG_FORMAT: Final = (
    "changed_files_signal=%(changed_files_signal)s "
    "changed_files_count=%(changed_files_count)d "
    "changed_symbols_selected=%(changed_symbols_selected)d "
    "changed_primary_promoted=%(changed_primary_promoted)s "
    "changed_symbols_promoted=%(changed_symbols_promoted)d "
    "changed_context_differs=%(changed_context_differs)s "
    "changed_baseline_status=%(changed_baseline_status)s "
    "changed_baseline_ms=%(changed_baseline_ms).1f"
)


def promotion_log_fields(promotion: Mapping[str, Any], baseline_ms: float = 0.0) -> str:
    """Render the count-only promotion fields for a log line.

    Args:
        promotion: The promotion block of a stage result.
        baseline_ms: Milliseconds spent building the counterfactual baseline.
            That is a cost, not a signal, so it stays on the log line and never
            reaches a session record.

    Returns:
        One fragment naming every promotion field.
    """
    values: dict[str, Any] = {
        field: promotion.get(field, default) for field, default in INERT_PROMOTION.items()
    }
    values["changed_baseline_ms"] = float(baseline_ms)
    return _PROMOTION_LOG_FORMAT % values


def _sent_symbols(package: ContextPackage | None) -> list[str]:
    """Return the symbols a composed package actually sends, in order.

    Args:
        package: The composed package, or ``None`` when nothing was assembled.

    Returns:
        The primary followed by the supporting symbols, deduplicated.
    """
    if package is None:
        return []
    sent: list[str] = []
    for name in (package.primary_symbol, *package.supporting_symbols):
        if name and name not in sent:
            sent.append(name)
    return sent


def changed_file_promotion_counts(
    package: ContextPackage | None,
    candidates: Sequence[ContextCandidate],
    changed_modules: frozenset[str],
    baseline_package: ContextPackage | None = None,
    changed_bonus_count: int = 0,
) -> dict[str, Any]:
    """Measure the working-tree bonus, and what it changed, in counts alone.

    The counters describe the **final** context - after ranking, budget
    trimming and delta suppression - because that is what the model receives:

    - a promoted candidate trimmed away by the budget or filtered out by the
      delta tracker is neither selected nor promoted;
    - ``changed_files_count`` still reports the modified files that were seen,
      so a non-zero count with zero selected symbols proves the signal was read
      but never reached the sent context;
    - ``changed_context_differs`` is the one measurement that answers the actual
      question: it is true when the package that was sent differs from
      ``baseline_package`` - the same request against the same index, query,
      budget and already-sent set, with no changed modules.  The comparison is
      the whole composed package, so a change of **order** counts even when the
      primary and the membership are identical, which is the usual effect of a
      flat reordering bonus.
    - ``changed_primary_promoted`` and ``changed_symbols_promoted`` stay on the
      record as detail: which part of that difference the primary and the
      supporting symbols account for.  A reorder-only request is exactly
      ``changed_context_differs=True`` with both of them at ``False``/``0``, and
      is still a promotion: the bonus moved text the model reads.
      ``changed_symbols_promoted`` counts every sent symbol that is absent from
      the no-bonus context, which can include a symbol outside the changed
      modules that entered through relationship expansion once the primary
      changed.
    - ``changed_baseline_status`` says whether the comparison was made at all:
      ``"built"`` compared the two packages, ``"skipped_no_bonus"`` means no
      candidate received the bonus so the two arms are provably identical,
      ``"failed"`` means the comparison could not be built - and then the three
      difference fields are reported as inert rather than as a measurement - and
      ``"none"`` means nothing needed comparing.

    Args:
        package: The composed context package, or ``None`` when no context was
            assembled for this request.
        candidates: The candidates the package was composed from, in final
            order.
        changed_modules: Index module keys of the locally modified files.
        baseline_package: The counterfactual package for the same request
            without ``changed_modules``.  ``None`` means there is no package to
            compare with - either the bonus touched nothing, or the build
            failed, or the signal is off.
        changed_bonus_count: How many candidates the ranking pass gave the
            bonus to.  It separates "no comparison was needed" from "a
            comparison was attempted and failed", and is itself a count only.

    Returns:
        Count-only fields for the stage result and the session log.  No path,
        module name or symbol name is returned.
    """
    if not changed_modules:
        return {
            key: value
            for key, value in INERT_PROMOTION.items()
            if key != "changed_files_signal"
        }

    status = (
        BASELINE_BUILT
        if baseline_package is not None
        else BASELINE_FAILED
        if changed_bonus_count > 0
        else BASELINE_SKIPPED_NO_BONUS
    )

    sent = _sent_symbols(package)
    promoted = {
        candidate.qualified_name
        for candidate in candidates
        if RankingReason.CHANGED_FILE in candidate.reasons
    }
    changed_symbols_selected = sum(1 for name in sent if name in promoted)
    if baseline_package is None:
        return {
            "changed_files_count": len(changed_modules),
            "changed_symbols_selected": changed_symbols_selected,
            "changed_primary_promoted": False,
            "changed_symbols_promoted": 0,
            "changed_context_differs": False,
            "changed_baseline_status": status,
        }

    baseline_sent = _sent_symbols(baseline_package)
    return {
        "changed_files_count": len(changed_modules),
        "changed_symbols_selected": changed_symbols_selected,
        "changed_primary_promoted": (sent or [""])[0] != (baseline_sent or [""])[0],
        "changed_symbols_promoted": len(set(sent) - set(baseline_sent)),
        # The composed package, not just its symbol names: order, membership,
        # primary and trimmed or enriched content are all part of what the model
        # receives.  The fields it compares beyond the serialized text
        # (``estimated_tokens`` and ``metadata``) are deterministic functions of
        # the same candidates, so they cannot differ unless the text differs.
        "changed_context_differs": package != baseline_package,
        "changed_baseline_status": status,
    }


class RepositoryContextStage(PipelineStage):
    """Pipeline stage that assembles repository context.

    Orchestrates the full context-building pipeline and attaches
    the resulting ContextPackage to the PipelineContext.

    Delta injection (enabled by default): tracks symbols already sent in
    a multi-turn conversation and suppresses redundant re-injection, while
    always keeping the primary symbol.

    Attributes:
        _index: Read-only repository index for symbol enumeration.
            May be ``None`` if repository scanning is not configured;
            the stage handles this gracefully.
        _delta_enabled: Whether delta context injection is active.
        _tracker: LRU cache mapping conversation keys to sent symbols.
    """

    def __init__(
        self,
        index: RepositoryIndex | None = None,
        context_delta_injection: bool = True,
        context_delta_cache_size: int = 256,
        max_context_tokens: int = 4096,
        intent_context_budgets: dict[str, int] | None = None,
        changed_files: ChangedModuleSource | None = None,
    ) -> None:
        """Initialize with an optional repository index.

        Args:
            index: A ``RepositoryIndex`` providing access to
                repository symbols, or ``None`` to disable context
                assembly.
            context_delta_injection: When ``True`` (default), only symbols
                not already sent in this conversation are injected.
            context_delta_cache_size: Maximum number of conversation keys
                in the LRU cache.
            max_context_tokens: Token budget for assembled repository context.
            intent_context_budgets: Optional per-intent budget overrides.
            changed_files: Optional source of index module keys for locally
                modified files, derived from the read-only Git change
                snapshot.  ``None`` (the default) leaves ranking untouched.
        """
        self._index = index
        self._delta_enabled = context_delta_injection
        self._tracker = SentSymbolTracker(maxsize=context_delta_cache_size)
        self._max_context_tokens = max_context_tokens if max_context_tokens > 0 else 4096
        self._changed_files = changed_files
        self._intent_context_budgets = {
            intent.upper(): tokens
            for intent, tokens in (intent_context_budgets or {}).items()
            if tokens > 0
        }

    @property
    def name(self) -> str:
        """Stage name for logging and ordering."""
        return "repository_context"

    async def before(self, context: PipelineContext) -> PipelineStageResult | None:
        """Check if repository context is enabled.

        Reads the ``context_enabled`` flag from context metadata.
        Defaults to ``True`` when the flag is absent.

        If disabled, records a no-op result and skips ``execute()``.

        Args:
            context: The pipeline context.

        Returns:
            A no-op result if context is disabled, or ``None`` to
            proceed with ``execute()``.
        """
        context_enabled = context.get_metadata("context_enabled", True)
        if not context_enabled:
            context.context_package = None
            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data={
                    "enabled": False,
                    "symbols_selected": 0,
                    "symbols_new": 0,
                    "symbols_suppressed": 0,
                    "max_context_tokens": self._max_context_tokens,
                    # The changed-file signal is never read on this path, so the
                    # promotion is inert -- stated explicitly rather than omitted.
                    **INERT_PROMOTION,
                },
            )
        return None

    async def execute(self, context: PipelineContext) -> PipelineStageResult:
        """Assemble repository context and attach to context.

        Executes the full context-building pipeline:

        1. Build candidates from the repository index.
        2. Rank candidates against the user query.
        3. Estimate token budget.
        4. Compose the final ContextPackage.

        When delta injection is enabled, step 3 is followed by filtering
        out symbols already sent in the current conversation.

        Stores the ContextPackage in ``context.context_package``.

        On any exception, logs the error, leaves ``context_package``
        as ``None``, and returns a successful result so the pipeline
        continues to the provider stage.

        Args:
            context: The pipeline context with request data.

        Returns:
            A ``PipelineStageResult`` with the ContextPackage on
            success, or a successful result with ``None`` data on
            failure (graceful degradation).
        """
        start_time = time.perf_counter()
        request_id = context.request_id
        context_enabled = context.get_metadata("context_enabled", True)
        # A stage that fails before the signal is read has nothing to report but
        # this.  The degraded paths surface it, so a configured source is never
        # recorded as "off" just because the stage sent nothing.
        changed_signal = SIGNAL_UNAVAILABLE

        try:
            # If no index is available, skip context assembly.  The signal state
            # is still worth stating, and reading it is a cache lookup that
            # cannot need the index.
            if self._index is None:
                context.context_package = None
                _, changed_signal = self._read_changed_signal()
                context.set_metadata("changed_files_signal", changed_signal)
                return PipelineStageResult(
                    stage_name=self.name,
                    success=True,
                    data=None,
                )

            # Extract query text from the request.
            # Messages are stored in context.request as provider kwargs.
            query_text = self._extract_query(context)

            # Build context from the repository index.
            # Read the ContextPlan from metadata -- it is the single source
            # of truth for retrieval configuration.  When no plan is present
            # (planning disabled or not yet run), fall back to safe defaults.
            plan = context.get_metadata("context_plan")
            max_context_tokens = self._resolve_context_budget(context, plan)
            context.set_metadata("repository_context_max_tokens", max_context_tokens)

            if plan is not None:
                query = ContextQuery(
                    text=query_text,
                    max_symbols=20,
                    max_modules=10,
                    max_tokens=max_context_tokens,
                    maximum_depth=plan.maximum_depth,
                    relationship_expansion=plan.relationship_expansion,
                )
            else:
                query = ContextQuery(
                    text=query_text,
                    max_symbols=20,
                    max_modules=10,
                    max_tokens=max_context_tokens,
                )

            chars_per_token = self._resolve_chars_per_token(context)
            changed_modules, changed_signal = self._read_changed_signal()
            # The state that was read rides on the pipeline metadata as well as
            # on the stage result, because the degraded paths below produce no
            # result data for the gateway to read.
            context.set_metadata("changed_files_signal", changed_signal)
            builder = ContextBuilder(
                self._index,
                chars_per_token=chars_per_token,
                changed_modules=changed_modules,
            )
            context_result = builder.build(query)

            # How many candidates the ranking pass gave the bonus to.  Zero is
            # proof that the same request without the signal ranks identically,
            # which is when the counterfactual is not worth building.
            changed_bonus_count = int(getattr(context_result, "changed_bonus_count", 0) or 0)

            # Check if ranking returned no relevant symbols.
            candidates = getattr(context_result, "candidates", [])
            if not candidates:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                # Nothing is sent on this path, so there is nothing to attribute
                # to the bonus and no baseline worth building - and because none
                # was attempted, "failed" cannot be claimed here.  The bonus count
                # is deliberately not passed: with nothing composed the two arms
                # send the same (empty) context either way, which is the skip
                # state.  What the signal saw, and whether it worked at all, is
                # still stated.
                promotion = {
                    **changed_file_promotion_counts(None, (), changed_modules, None),
                    "changed_files_signal": changed_signal,
                }

                logger.info(
                    "repository_context request_id=%s context_enabled=%s "
                    "context_status=empty reason=no_relevant_symbols "
                    "%s duration_ms=%.1f",
                    request_id,
                    context_enabled,
                    promotion_log_fields(promotion),
                    elapsed_ms,
                )

                # Leave context_package as None -- proceed with unmodified messages.
                context.context_package = None

                return PipelineStageResult(
                    stage_name=self.name,
                    success=True,
                    data={
                        "symbols_selected": 0,
                        "symbols_new": 0,
                        "symbols_suppressed": 0,
                        "max_context_tokens": max_context_tokens,
                        "changed_baseline_ms": 0.0,
                        **promotion,
                    },
                )

            # ------------------------------------------------------------------
            # Delta context injection
            # ------------------------------------------------------------------
            symbols_new = len(candidates)
            symbols_suppressed = 0
            already_sent: set[str] = set()
            conv_key = ""

            if self._delta_enabled and candidates:
                # Retrieve the list of messages for key computation.
                messages = self._get_messages(context)

                # Conversation key = user-message prefix (excludes assistant turns).
                conv_key = conversation_key(messages)

                # Look up already-sent symbols (empty set on cache miss).
                already_sent = self._tracker.get(conv_key)

                # Filter out already-sent supporting symbols.
                filtered = filter_candidates(candidates, already_sent)
                symbols_new = len(filtered)
                symbols_suppressed = len(candidates) - symbols_new

                # Store the union under the same key so the next turn can find it.
                new_symbols = collect_all_symbols(filtered)
                self._tracker.store(store_key(messages), already_sent | new_symbols)

                # Replace candidates in-place so the composer sees the filter.
                # ContextResult is frozen, so mutate the list directly.
                if filtered is not candidates:
                    candidates = filtered
                    context_result.candidates.clear()
                    context_result.candidates.extend(filtered)

            # Compose the final package.
            composer = ContextComposer()
            package = composer.compose(context_result)

            # Measure the working-tree bonus against the same request without
            # it.  The counterfactual is a second full build, and it doubles the
            # stage on a dirty tree - measured on this repository's real index
            # (328 modules, 8 changed) about 50 ms becomes about 105 ms - so it
            # is paid only when the bonus actually moved a candidate.  With zero
            # bonus candidates the two arms are provably identical, and saying
            # so is the honest answer rather than a measurement.
            baseline_package: ContextPackage | None = None
            changed_baseline_ms = 0.0
            if changed_modules and changed_bonus_count > 0:
                baseline_start = time.perf_counter()
                baseline_package = self._build_baseline_package(
                    self._index,
                    query,
                    chars_per_token,
                    already_sent,
                )
                changed_baseline_ms = (time.perf_counter() - baseline_start) * 1000

            # Counted on the composed packages - not on the ranked candidates -
            # so budget trimming and delta suppression are already applied.
            promotion = {
                **changed_file_promotion_counts(
                    package,
                    candidates,
                    changed_modules,
                    baseline_package,
                    changed_bonus_count,
                ),
                "changed_files_signal": changed_signal,
            }

            # Serialize the context package into a ProviderRequest.
            # The serializer translates platform models into the
            # provider-specific request format that the Provider
            # layer consumes.
            self._serialize(context, package)

            # Attach the context package to the pipeline context so that
            # downstream stages (and tests) can inspect it directly.
            context.context_package = package

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            modules_selected = len(package.related_modules)
            estimated_tokens = package.estimated_tokens

            # Determine a concise status label.
            if symbols_new == 0 and symbols_suppressed > 0:
                context_status = "no_new_symbols"
            elif self._delta_enabled:
                context_status = "ok"
            else:
                context_status = "ok"

            # Build the log line with delta info when enabled.
            promotion_fields = promotion_log_fields(promotion, changed_baseline_ms)
            if self._delta_enabled:
                conv_key_short = conv_key[:8] if candidates else ""
                logger.info(
                    "repository_context request_id=%s context_enabled=%s "
                    "context_status=%s symbols_selected=%d symbols_new=%d "
                    "symbols_suppressed=%d conversation_key=%s "
                    "modules_selected=%d estimated_tokens=%d "
                    "%s duration_ms=%.1f",
                    request_id,
                    context_enabled,
                    context_status,
                    len(package.supporting_symbols),
                    symbols_new,
                    symbols_suppressed,
                    conv_key_short,
                    modules_selected,
                    estimated_tokens,
                    promotion_fields,
                    elapsed_ms,
                )
            else:
                logger.info(
                    "repository_context request_id=%s context_enabled=%s "
                    "context_status=%s symbols_selected=%d "
                    "modules_selected=%d estimated_tokens=%d "
                    "%s duration_ms=%.1f",
                    request_id,
                    context_enabled,
                    context_status,
                    len(package.supporting_symbols),
                    modules_selected,
                    estimated_tokens,
                    promotion_fields,
                    elapsed_ms,
                )

            # Assemble counts for metadata.
            symbols_selected = len(package.supporting_symbols) + (
                1 if package.primary_symbol else 0
            )
            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data={
                    "package": package,
                    "symbols_selected": symbols_selected,
                    "symbols_new": symbols_new,
                    "symbols_suppressed": symbols_suppressed,
                    "max_context_tokens": max_context_tokens,
                    "changed_baseline_ms": changed_baseline_ms,
                    **promotion,
                },
            )

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            logger.error(
                "repository_context request_id=%s context_enabled=%s error=%s duration_ms=%.1f",
                request_id,
                context_enabled,
                exc,
                elapsed_ms,
            )

            # Leave context_package as None -- graceful degradation.  The signal
            # state that was read is still stated, so a request that failed after
            # the read does not record as a disabled feature; the default above
            # covers a failure before it.
            context.context_package = None
            context.set_metadata("changed_files_signal", changed_signal)

            return PipelineStageResult(
                stage_name=self.name,
                success=True,
                data=None,
                error=str(exc),
            )

    async def after(
        self, context: PipelineContext, result: PipelineStageResult
    ) -> PipelineStageResult | None:
        """Log stage completion.

        Args:
            context: The pipeline context.
            result: The result from this stage.

        Returns:
            ``None`` to keep the existing result.
        """
        if result.success:
            has_package = context.context_package is not None
            logger.info(
                "repository_context request_id=%s status=ok has_package=%s",
                context.request_id,
                has_package,
            )
        else:
            logger.error(
                "repository_context request_id=%s status=error error=%s",
                context.request_id,
                result.error,
            )
        return None

    def _read_changed_signal(self) -> tuple[frozenset[str], str]:
        """Read the locally modified module keys and state whether it worked.

        The gateway primes its signal during lifespan startup and refreshes it
        from a background worker thread, so this is a frozen-set lookup in the
        request path - never a ``git status``.  A source that raises degrades to
        an empty set; the signal may never break or slow down a request.

        Returns:
            A ``(module keys, state)`` pair.  ``SIGNAL_OFF`` means no source is
            configured, ``SIGNAL_UNAVAILABLE`` means the source raised, and
            ``SIGNAL_OK`` means the read worked - including on a clean tree,
            where the set is simply empty.  No path is ever returned.
        """
        if self._changed_files is None:
            return frozenset(), SIGNAL_OFF
        try:
            return frozenset(self._changed_files.module_paths()), SIGNAL_OK
        except Exception as exc:  # graceful degradation
            logger.warning(
                "repository_context changed_files_status=unavailable error=%s",
                type(exc).__name__,
            )
            return frozenset(), SIGNAL_UNAVAILABLE

    def _build_baseline_package(
        self,
        index: RepositoryIndex,
        query: ContextQuery,
        chars_per_token: float,
        already_sent: set[str],
    ) -> ContextPackage | None:
        """Compose the same request as it would have been sent without the bonus.

        This is the counterfactual the promotion fields are measured against.
        ``ContextBuilder.build`` creates fresh candidates on every call, so this
        pass cannot disturb the scores or reasons of the package that is really
        going out.  Nothing here is serialized, attached to the context, or
        stored in the delta tracker: only the symbols it would have sent are
        compared, in counts, and the result is dropped.

        Args:
            index: The same index the real build used.
            query: The same ``ContextQuery`` the real build used.
            chars_per_token: The same calibration the real build used.
            already_sent: The same delta set the real candidates were filtered
                with, so the comparison holds the conversation fixed.

        Returns:
            The counterfactual package, or ``None`` when it could not be built.
            ``None`` is reported as ``changed_baseline_status="failed"`` with the
            difference fields inert, which is a request that could not be
            measured - not a request where the bonus did nothing.
        """
        try:
            baseline_result = ContextBuilder(
                index,
                chars_per_token=chars_per_token,
            ).build(query)
        except Exception as exc:  # the measurement must never break a request
            logger.warning(
                "repository_context changed_files_baseline=unavailable error=%s",
                type(exc).__name__,
            )
            return None

        candidates = baseline_result.candidates
        if self._delta_enabled and candidates:
            filtered = filter_candidates(candidates, already_sent)
            if filtered is not candidates:
                baseline_result.candidates.clear()
                baseline_result.candidates.extend(filtered)
        return ContextComposer().compose(baseline_result)

    def _resolve_context_budget(
        self,
        context: PipelineContext,
        plan: Any,
    ) -> int:
        """Resolve request, intent, or default repository-context budget."""
        override = context.get_metadata("repository_context_max_tokens")
        if isinstance(override, int) and override > 0:
            return override

        intent = getattr(plan, "intent", "")
        if isinstance(intent, str):
            intent_budget = self._intent_context_budgets.get(intent.upper())
            if intent_budget is not None:
                return intent_budget

        return self._max_context_tokens

    @staticmethod
    def _resolve_chars_per_token(context: PipelineContext) -> float:
        """Read the resolved model's calibrated chars-per-token ratio.

        Defensive: falls back to the platform default when the resolved
        model is missing, the definition lacks the attribute, or the value
        is not a finite number within the supported 0.5-20.0 range.

        Args:
            context: The pipeline context.

        Returns:
            The chars-per-token ratio to use for context estimation.
        """
        resolved = getattr(context, "resolved_model", None)
        if resolved is None:
            return CHARS_PER_TOKEN
        definition = getattr(resolved, "definition", None)
        if definition is None:
            return CHARS_PER_TOKEN
        value = getattr(definition, "chars_per_token", CHARS_PER_TOKEN)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return CHARS_PER_TOKEN
        if not math.isfinite(value) or not 0.5 <= value <= 20.0:
            return CHARS_PER_TOKEN
        return float(value)

    @staticmethod
    def _extract_query(context: PipelineContext) -> str:
        """Extract query text from the pipeline context.

        Reads the last user message from the request messages.

        Args:
            context: The pipeline context.

        Returns:
            The query text, or empty string if not found.
        """
        request = context.request
        if not isinstance(request, dict):
            return ""

        return select_context_query_text(request.get("messages", []))

    @staticmethod
    def _get_messages(context: PipelineContext) -> list[dict[str, str]]:
        """Return the messages list from the request, or [].

        Args:
            context: The pipeline context.

        Returns:
            The raw ``messages`` list from ``context.request``.
        """
        request = context.request
        if isinstance(request, dict):
            messages = request.get("messages", [])
            if isinstance(messages, list):
                return messages
        return []

    @staticmethod
    def _serialize(
        context: PipelineContext,
        context_package: ContextPackage,
    ) -> None:
        """Serialize the context package into the normalized request.

        Looks up the OpenAI serializer via the factory, produces a
        serialized message list, and updates the ``normalized_request``
        on the pipeline context so downstream stages (ProviderStage)
        can emit a deterministic provider payload.

        The serializer combines the client system message(s) with the
        repository-context system message into a single system message,
        then preserves the conversation messages.

        Args:
            context: The pipeline context with request data.
            context_package: The assembled context package to serialize.
        """
        nr = context.normalized_request
        if nr is None:
            # Fallback: try to read from context.request.
            request = context.request
            if not isinstance(request, dict):
                return
            messages = request.get("messages", [])
            if not messages:
                return
            model = request.get("model", "default")
        else:
            messages = list(nr.messages)
            model = nr.model

        try:
            serializer = SerializerFactory.create(ProviderType.openai)
            provider_request = serializer.serialize(
                context_package=context_package,
                messages=messages,
                model=model,
            )

            # Update the normalized request with the serialized messages
            # (which now include the combined system message).
            if nr is not None:
                updated_nr = nr.with_messages(provider_request.messages)
                context.normalized_request = updated_nr
            else:
                # Store ProviderRequest in metadata for backward compat.
                context.set_metadata("provider_request", provider_request)
        except Exception as exc:
            logger.warning(
                "serialization request_id=%s error=%s",
                context.request_id,
                exc,
            )
            # Leave provider_request unset -- graceful degradation.
