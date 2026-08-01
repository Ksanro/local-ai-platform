"""Chat completions endpoint.

Routes chat requests through the pipeline (which delegates to the
configured provider) and handles both streaming and non-streaming
responses.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse

from apps.gateway.core.config import get_settings
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.exceptions import PipelineError
from packages.pipeline.request import PipelineRequest
from packages.providers.exceptions import (
    ProviderAuthenticationError,
    ProviderConnectionError,
    ProviderResponseError,
    UnknownModelError,
    UnknownProviderError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class ChatCompletionRequest(BaseModel):
    """Request body for chat completion endpoint.

    Mirrors the OpenAI Chat Completion API shape for compatibility.
    """

    model_config = ConfigDict(extra="allow")

    messages: list[dict[str, Any]] = Field(
        ...,
        description="List of message objects with role and content.",
    )
    model: str = Field(
        default="default",
        description="Model identifier to use for completion.",
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the response.",
    )
    temperature: float | None = Field(
        default=None,
        description="Sampling temperature (0-2).",
    )
    max_tokens: int | None = Field(
        default=None,
        description="Maximum number of tokens to generate.",
    )
    context_intent: str | None = Field(
        default=None,
        description="Optional explicit repository-context intent override.",
    )


def _status_for_exception(exc: Exception | None) -> int:
    """Map a pipeline exception to an HTTP status code.

    Args:
        exc: The exception to map, or ``None`` for the default.

    Returns:
        An HTTP status code integer.
    """
    if exc is None:
        return 502
    if isinstance(exc, UnknownProviderError):
        return 501
    if isinstance(exc, UnknownModelError):
        return 404
    if isinstance(exc, PipelineError):
        return 501
    if isinstance(exc, ProviderAuthenticationError):
        return 502
    if isinstance(exc, ProviderConnectionError):
        return 503
    if isinstance(exc, ProviderResponseError) and exc.status_code is not None:
        status = exc.status_code
        # 4xx errors are client-side — pass through unchanged.
        # 5xx errors are upstream failures — report as bad gateway.
        if 400 <= status < 500:
            return status
        return 502
    return 502


def _surface_session_metadata(
    request: Request,
    engine: PipelineEngine,
    response: Any,
) -> None:
    """Surface pipeline context metadata on request.scope for session logging.

    Reads stage results and pipeline context metadata, then writes
    the relevant fields onto ``request.scope`` so the session logger
    middleware can capture them without touching PipelineContext directly.

    Architecture
    ------------

    The pipeline engine already measures ``PipelineStageResult.duration``
    for every stage (in ``PipelineEngine.execute``, line 118).  This
    function extracts those durations and writes them onto the scope
    so the session logger can surface them in the timing breakdown.

    Args:
        request: The FastAPI request.
        engine: The pipeline engine that was used.
        response: The pipeline response from engine.execute().
    """
    scope = request.scope

    # --- Intent from PlanningStage ---
    # We need access to the PipelineContext to read context_plan.
    # The engine stores the last context in app state during execute,
    # but we can also read from response.stage_results.
    stage_results = response.stage_results if hasattr(response, "stage_results") else {}

    planning_result = stage_results.get("planning")
    if planning_result is not None and planning_result.data is not None:
        plan = planning_result.data
        if hasattr(plan, "intent"):
            scope["session_intent"] = plan.intent
        else:
            scope["session_intent"] = "DEFAULT"
    else:
        scope["session_intent"] = "DEFAULT"

    resp_meta = getattr(response, "metadata", {}) or {}
    scope["session_planning_user_message_count"] = resp_meta.get(
        "planning_user_message_count",
        0,
    )
    scope["session_planning_last_user_message"] = resp_meta.get(
        "planning_last_user_message",
        "",
    )
    scope["session_planning_matched_keyword"] = resp_meta.get(
        "planning_matched_keyword",
        "",
    )
    scope["session_planning_context_intent_override"] = resp_meta.get(
        "planning_context_intent_override",
        "",
    )
    scope["session_planning_context_intent_ignored"] = resp_meta.get(
        "planning_context_intent_ignored",
        "",
    )

    # --- Repository context metadata ---
    repo_result = stage_results.get("repository_context")
    if repo_result is not None and repo_result.success:
        pkg = repo_result.data

        # All paths now return a metadata dict from the repository_context stage.
        # For the assembled path the dict contains "package" + counts.
        # For no_new_symbols/empty paths the dict contains only counts.
        # For disabled path the dict contains "enabled": False + zero counts.
        if isinstance(pkg, dict):
            if "enabled" in pkg and pkg.get("enabled") is False:
                # Disabled path.
                scope["session_context_status"] = "disabled"
                scope["session_symbols_selected"] = 0
                scope["session_symbols_new"] = 0
                scope["session_symbols_suppressed"] = 0
                scope["session_estimated_tokens"] = 0
                scope["session_context_max_tokens"] = pkg.get("max_context_tokens", 0)
                scope["session_primary_symbol"] = ""
            elif "package" in pkg:
                # Assembled path with counts.
                scope["session_context_status"] = "assembled"
                package = pkg["package"]
                scope["session_symbols_selected"] = pkg.get("symbols_selected", 0)
                scope["session_symbols_new"] = pkg.get("symbols_new", 0)
                scope["session_symbols_suppressed"] = pkg.get("symbols_suppressed", 0)
                est = getattr(package, "estimated_tokens", 0) if package else 0
                scope["session_estimated_tokens"] = est
                scope["session_context_max_tokens"] = pkg.get("max_context_tokens", 0)
                prim = getattr(package, "primary_symbol", "") if package else ""
                scope["session_primary_symbol"] = prim
            else:
                # Empty or no_new_symbols path.
                symbols_new = pkg.get("symbols_new", 0)
                symbols_suppressed = pkg.get("symbols_suppressed", 0)
                scope["session_context_status"] = (
                    "no_new_symbols" if (symbols_new == 0 and symbols_suppressed > 0) else "empty"
                )
                scope["session_symbols_selected"] = pkg.get("symbols_selected", 0)
                scope["session_symbols_new"] = symbols_new
                scope["session_symbols_suppressed"] = symbols_suppressed
                scope["session_estimated_tokens"] = 0
                scope["session_context_max_tokens"] = pkg.get("max_context_tokens", 0)
                scope["session_primary_symbol"] = ""
        else:
            scope["session_context_status"] = "disabled"
            scope["session_symbols_selected"] = 0
            scope["session_symbols_new"] = 0
            scope["session_symbols_suppressed"] = 0
            scope["session_estimated_tokens"] = 0
            scope["session_context_max_tokens"] = 0
    elif repo_result is not None:
        scope["session_context_status"] = "degraded"
        scope["session_symbols_selected"] = 0
        scope["session_symbols_new"] = 0
        scope["session_symbols_suppressed"] = 0
        scope["session_estimated_tokens"] = 0
        scope["session_context_max_tokens"] = 0
    else:
        scope["session_context_status"] = "disabled"
        scope["session_symbols_selected"] = 0
        scope["session_symbols_new"] = 0
        scope["session_symbols_suppressed"] = 0
        scope["session_estimated_tokens"] = 0
        scope["session_context_max_tokens"] = 0

    # --- Backend model from provider stage ---
    provider_result = stage_results.get("provider")
    if provider_result is not None and provider_result.data is not None:
        data = provider_result.data
        backend_model = data.get("backend_model") if isinstance(data, dict) else None
        if backend_model:
            scope["session_backend_model"] = backend_model

    # --- Stage durations for timing breakdown ---
    # Extract duration from each PipelineStageResult and write onto scope.
    # The pipeline engine already measures result.duration for each stage.
    # Append _ms suffix so the keys match what session_log.py and the
    # analyzer expect (e.g. "repository_context_ms").
    stage_durations_ms: dict[str, float] = {}
    for stage_name, result in stage_results.items():
        dur = result.duration if hasattr(result, "duration") else 0.0
        stage_durations_ms[f"{stage_name}_ms"] = round(dur * 1000, 1)  # seconds → ms

    scope["session_stage_durations_ms"] = stage_durations_ms

    # Compute pipeline_ms (sum of non-provider stages) and provider_wait_ms.
    # Keys now have _ms suffix (e.g. "provider_ms").
    provider_ms = stage_durations_ms.get("provider_ms", 0.0)
    # Subtract provider_ms from the total to get non-provider stages.
    pipeline_ms = sum(d for k, d in stage_durations_ms.items() if k != "provider_ms")
    scope["session_pipeline_ms"] = round(pipeline_ms, 1)
    scope["session_provider_wait_ms"] = round(provider_ms, 1)

    # --- History capping metadata ---
    # Read from response.metadata (copied from context.metadata in PipelineResponse.from_context).
    scope["session_history_cap_enabled"] = resp_meta.get("history_cap_enabled", False)
    scope["session_history_cap_applied"] = resp_meta.get("history_cap_applied", False)
    scope["session_history_cap_budget"] = resp_meta.get("history_cap_budget", 0)
    scope["session_history_dropped_count"] = resp_meta.get("history_dropped_count", 0)
    scope["session_history_tokens_after"] = resp_meta.get("history_tokens_after", 0)


@router.post("/v1/chat/completions", response_model=None)
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
) -> StreamingResponse | dict[str, Any]:
    """Chat completions endpoint.

    Forwards the request through the pipeline and returns
    either a JSON response or an SSE streaming response depending
    on the ``stream`` flag.

    Args:
        request: The incoming FastAPI request (for request ID).
        body: The parsed chat completion request body.

    Returns:
        A StreamingResponse for SSE or a dict for JSON responses.

    Raises:
        HTTPException: If the pipeline fails or no provider is configured.
    """
    request_id = request.scope.get("request_id") or str(uuid.uuid4())
    model: str = body.model
    request.scope["request_data"] = body.model_dump()
    start_time: float = time.perf_counter()

    # Look up the configured provider via the factory.
    settings = get_settings()
    provider_name = settings.default_provider

    # Build the pipeline request.
    # Only optional passthrough params go in kwargs; messages/model/stream
    # are the sole source of truth via the dedicated PipelineRequest fields.
    kwargs: dict[str, Any] = {}
    if body.temperature is not None:
        kwargs["temperature"] = body.temperature
    if body.max_tokens is not None:
        kwargs["max_tokens"] = body.max_tokens

    # History cap settings are passed through to the engine in metadata.
    metadata: dict[str, Any] = {
        "request_id": request_id,
        "context_enabled": settings.repository_context_enabled,
        "history_cap_enabled": settings.history_cap_enabled,
        "history_cap_tokens": settings.history_cap_tokens,
        "max_tokens_override": body.max_tokens,
    }
    context_intent = body.context_intent or request.headers.get("X-Context-Intent")
    if context_intent is not None:
        metadata["context_intent"] = context_intent

    pipeline_request = PipelineRequest(
        provider_name=provider_name,
        model=body.model,
        messages=body.messages,
        stream=body.stream,
        kwargs=kwargs,
        metadata=metadata,
    )

    try:
        # Execute through the pipeline.
        engine = request.app.state.pipeline
        response = await engine.execute(pipeline_request)
        elapsed = time.perf_counter() - start_time

        if not response.success:
            if isinstance(response.exception, UnknownModelError):
                # Re-raise so the app-level handler emits the OpenAI-shaped body.
                raise response.exception

            status_code = _status_for_exception(response.exception)
            raise HTTPException(status_code=status_code, detail=response.error)

        # Surface session metadata on request.scope for the session logger.
        _surface_session_metadata(request, engine, response)

        result = response.data

        # Non-streaming: log duration immediately.
        if not body.stream:
            logger.info(
                "provider=%s model=%s duration=%.3fs status=ok request_id=%s",
                provider_name,
                model,
                elapsed,
                request_id,
            )
            return cast(dict[str, Any], result)

        # Streaming: log duration and TTFT on exhaustion via a wrapper generator.
        generator_fn = result.get("generator")
        media_type = result.get("media_type", "text/event-stream")
        if generator_fn is None:
            # Unexpected shape -- fall through to JSON.
            logger.warning(
                "provider=%s model=%s request_id=%s stream=true but no generator in result",
                provider_name,
                model,
                request_id,
            )
            return cast(dict[str, Any], result)

        return StreamingResponse(
            content=_wrap_stream_duration(
                generator_fn(), provider_name, model, start_time, request_id, request
            ),
            media_type=media_type,
        )

    except HTTPException:
        raise
    except PipelineError as exc:
        elapsed = time.perf_counter() - start_time
        logger.error(
            "provider=%s model=%s duration=%.3fs status=error request_id=%s error=%s",
            provider_name,
            model,
            elapsed,
            request_id,
            exc,
        )
        raise HTTPException(status_code=501, detail=str(exc)) from exc


def _wrap_stream_duration(
    generator: Any,
    provider_name: str,
    model: str,
    start_time: float,
    request_id: str,
    request: Request | None = None,
) -> Any:
    """Wrap a streaming generator to log total duration and TTFT on exhaustion.

    Yields every event from the underlying generator so the caller
    sees the same stream, but logs the full wall-clock time and
    time-to-first-token once iteration is complete.

    Also writes ``session_provider_wait_ms`` and ``session_ttft_ms``
    onto ``request.scope`` so the session logger can capture the true
    streaming drain time (which otherwise reads ~0 because the provider
    stage returns a lazy generator immediately).

    Args:
        generator: The async generator returned by the provider.
        provider_name: Name of the provider for logging.
        model: Model identifier for logging.
        start_time: perf_counter timestamp before the provider call.
        request_id: Request ID for logging.
        request: Optional FastAPI request (for writing timing to scope).

    Returns:
        An async generator that yields the same events and logs
        duration after the last event.
    """

    async def _wrapped() -> Any:
        status = "stream_ok"
        ttft: float | None = None
        gen_start: float = time.perf_counter()
        try:
            first = True
            async for event in generator:
                if first:
                    ttft = time.perf_counter() - gen_start
                    first = False
                yield event
        except GeneratorExit:
            status = "stream_client_disconnect"
            raise
        except Exception:
            status = "stream_error"
            raise
        finally:
            elapsed = time.perf_counter() - start_time
            drain_ms = (time.perf_counter() - gen_start) * 1000
            ttft_ms_val: float | None = round(ttft * 1000, 1) if ttft is not None else None

            # Write true streaming timing onto scope for the session logger.
            if request is not None:
                scope = request.scope
                scope["session_provider_wait_ms"] = round(drain_ms, 1)
                scope["session_ttft_ms"] = ttft_ms_val

            ttft_str = f" ttft={ttft:.3f}" if ttft is not None else ""
            logger.info(
                "provider=%s model=%s duration=%.3f%s status=%s request_id=%s",
                provider_name,
                model,
                elapsed,
                ttft_str,
                status,
                request_id,
            )

    return _wrapped()
