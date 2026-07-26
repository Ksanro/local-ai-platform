"""Pipeline engine.

Orchestrates registered stages in order, executing each stage's
``before``, ``execute``, and ``after`` hooks.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from packages.pipeline.base import PipelineStage
from packages.pipeline.context import PipelineContext
from packages.pipeline.exceptions import PipelineExecutionError
from packages.pipeline.history import cap_history
from packages.pipeline.normalized import NormalizedRequest
from packages.pipeline.request import PipelineRequest
from packages.pipeline.response import PipelineResponse
from packages.pipeline.result import PipelineStageResult

logger = logging.getLogger(__name__)


class PipelineEngine:
    """Pipeline execution engine.

    Manages a registry of stages and executes them in order for each
    incoming request. Stages are registered via ``register()`` and
    executed via ``execute()``.

    Execution model:

    1. Create a fresh ``PipelineContext`` for the request.
    2. For each registered stage (in order):
       a. Call ``before(context)`` — may short-circuit.
       b. Call ``execute(context)`` — performs the work.
       c. Call ``after(context, result)`` — post-process.
    3. Build and return a ``PipelineResponse``.

    Attributes:
        _stages: Ordered list of registered pipeline stages.
    """

    def __init__(self) -> None:
        """Initialize the pipeline engine with an empty stage list."""
        self._stages: list[PipelineStage] = []

    def register(self, stage: PipelineStage) -> None:
        """Register a pipeline stage.

        Stages are executed in registration order. To change order,
        unregister and re-register, or rebuild the engine.

        Args:
            stage: The stage instance to register.
        """
        self._stages.append(stage)

    async def execute(self, request: PipelineRequest) -> PipelineResponse:
        """Execute all registered stages for the given request.

        Creates a fresh context, runs each stage in order, and returns
        the final response.

        Args:
            request: The pipeline request to process.

        Returns:
            A ``PipelineResponse`` with results from all stages.

        Raises:
            PipelineExecutionError: If no stages are registered.
        """
        if not self._stages:
            raise PipelineExecutionError("No stages registered in pipeline")

        context = PipelineContext(
            request_id=request.metadata.get("request_id", ""),
            request=request.to_provider_kwargs(),
        )

        # Store provider_name and model in context metadata for logging
        context.set_metadata("provider_name", request.provider_name)
        context.set_metadata("model", request.model)
        context.set_metadata("context_enabled", request.metadata.get("context_enabled", True))

        # Create NormalizedRequest early so downstream stages can use it.
        # This is the single source of truth for protocol fields.
        context.normalized_request = NormalizedRequest.from_client(context.request)

        # Determine history cap settings from context metadata.
        # These are set by the gateway endpoint from settings.
        history_cap_enabled = context.get_metadata("history_cap_enabled", False)
        history_cap_tokens = context.get_metadata("history_cap_tokens", 0)
        # Read from the typed field set by ModelResolutionStage, not metadata.
        resolved_model = context.resolved_model
        max_tokens_override = context.get_metadata("max_tokens_override")
        context.set_metadata("history_cap_enabled", history_cap_enabled)
        context.set_metadata("history_cap_tokens", history_cap_tokens)

        all_results: dict[str, PipelineStageResult] = {}

        for stage in self._stages:
            stage_start = time.perf_counter()
            stage_name = stage.name

            logger.info(
                "pipeline stage=%s request_id=%s",
                stage_name,
                context.request_id,
            )

            try:
                # Before hook
                short_circuit = await stage.before(context)
                if short_circuit is not None:
                    result = short_circuit
                    if not isinstance(result, PipelineStageResult):
                        result = PipelineStageResult(
                            stage_name=stage_name,
                            success=True,
                            data=result,
                        )
                else:
                    # Execute
                    result = await stage.execute(context)

                # After hook
                after_result = await stage.after(context, result)
                if after_result is not None and isinstance(after_result, PipelineStageResult):
                    result = after_result

                # Record result with duration
                result.duration = time.perf_counter() - stage_start
                context.set_stage_result(stage_name, result)
                all_results[stage_name] = result

                if not result.success:
                    logger.error(
                        "pipeline stage=%s request_id=%s error=%s",
                        stage_name,
                        context.request_id,
                        result.error,
                    )
                    # Halt the pipeline on failure — do not run later stages.
                    break

                # Propagate data for next stages
                if result.data is not None:
                    pass

                # Apply history capping after RepositoryContextStage completes
                # (where the repo-context system message is injected) and
                # before ProviderStage calls to_provider_payload.
                if stage_name == "repository_context" and history_cap_enabled:
                    _apply_history_cap(context, resolved_model, max_tokens_override)

            except Exception as exc:
                elapsed = time.perf_counter() - stage_start
                error_result = PipelineStageResult(
                    stage_name=stage_name,
                    success=False,
                    error=str(exc),
                    exception=exc,
                    duration=elapsed,
                )
                context.set_stage_result(stage_name, error_result)
                all_results[stage_name] = error_result

                logger.error(
                    "pipeline stage=%s request_id=%s error=%s duration=%.3fs",
                    stage_name,
                    context.request_id,
                    exc,
                    elapsed,
                )
                # Catch any exception, record it as a failed result,
                # and fall through to build a normal PipelineResponse.
                # This ensures the status-code mapping in chat.py
                # receives the original exception via response.exception.
                break

        # Build final response from context (success/error/data are
        # aggregated across all stages by from_context).
        response = PipelineResponse.from_context(context)

        # Log summary
        logger.info(
            "pipeline request_id=%s provider=%s model=%s duration=%.3fs status=%s",
            context.request_id,
            request.provider_name,
            request.model,
            context.elapsed,
            "ok" if response.success else "error",
        )

        return response


def _apply_history_cap(
    context: PipelineContext,
    resolved_model: Any,
    max_tokens_override: int | None,
) -> None:
    """Apply history capping after RepositoryContextStage.

    Creates a capped NormalizedRequest and stores history_dropped_count
    and history_tokens_after on context.metadata for the session logger.

    Args:
        context: The pipeline context.
        resolved_model: The resolved model (with context_window).
        max_tokens_override: Max tokens for generation (if set).
    """
    from packages.context.budget import CHARS_PER_TOKEN

    nr = context.normalized_request
    if nr is None:
        return

    # Derive the history token budget.
    if history_cap_tokens_override := context.get_metadata("history_cap_tokens", 0):
        max_history_tokens = history_cap_tokens_override
    elif resolved_model is not None:
        # Derive from context_window minus reserve for generation and repo context.
        ctx_window = getattr(resolved_model, "context_window", 8192)
        if ctx_window is None:
            # Handle ResolvedModel definition attribute.
            defn = getattr(resolved_model, "definition", None)
            if defn is not None:
                ctx_window = getattr(defn, "context_window", 8192)
        if ctx_window is None:
            ctx_window = 8192
        gen_max = max_tokens_override or 2048
        repo_context_reserve = 1024  # estimate for repo-context system message
        safety_margin = 512
        max_history_tokens = ctx_window - gen_max - repo_context_reserve - safety_margin
        if max_history_tokens <= 0:
            return
    else:
        return

    # Apply capping.
    messages = nr.messages
    capped_messages, dropped_count = cap_history(
        messages,
        max_history_tokens,
        estimate=lambda text: int(len(text) / CHARS_PER_TOKEN) if text else 0,
    )

    if dropped_count > 0:
        # Create a new NormalizedRequest with capped messages.
        capped_nr = nr.with_messages(capped_messages)
        context.normalized_request = capped_nr

        # Estimate tokens after capping for logging.
        total_after = sum(
            int(len(_content_to_text(m.get("content", ""))) / CHARS_PER_TOKEN)
            for m in capped_messages
        )

        # Store on context.metadata for the session logger to surface
        # via response.metadata (set by _surface_history_metadata).
        context.set_metadata("history_dropped_count", dropped_count)
        context.set_metadata("history_tokens_after", total_after)

        # Also set on response metadata so it survives PipelineResponse.from_context.
        if not hasattr(context, "_response_metadata"):
            context._response_metadata: dict[str, Any] = {}
        context._response_metadata["history_dropped_count"] = dropped_count
        context._response_metadata["history_tokens_after"] = total_after

        logger.info(
            "history_cap request_id=%s dropped=%d tokens_after=%d budget=%d",
            context.request_id,
            dropped_count,
            total_after,
            max_history_tokens,
        )


def _content_to_text(content: object) -> str:
    """Normalise an OpenAI message ``content`` field to plain text.

    Content may be a string, or a list of parts such as
    ``[{"type": "text", "text": "..."}]`` (the format Cline and other
    clients send). Non-text parts are ignored.

    Args:
        content: The raw ``content`` value from a message.

    Returns:
        The concatenated text, or an empty string.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""
