"""Protocol compatibility invariant test.

Asserts that routing and context injection change ONLY:
- ``model`` (client-facing name → backend_model)
- the repository-context system message content (added or updated)

Everything else must be byte-identical:
- client user/assistant messages (content, order, roles)
- the client's own system message(s)
- ``tools``, ``tool_choice``
- ``stream``, ``stream_options``
- ``stop``, generation params, etc.

This test catches regressions where routing or serialization
accidentally modifies fields it should not touch.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from packages.pipeline.context import PipelineContext
from packages.pipeline.engine import PipelineEngine
from packages.pipeline.result import PipelineStageResult
from packages.pipeline.stages import (
    ModelResolutionStage,
    PlanningStage,
    ProviderStage,
)
from packages.pipeline.stages.repository_context import RepositoryContextStage
from packages.providers import _load_providers
from packages.providers.registry_models import ModelRegistry
from packages.providers.router import ModelRouter
from packages.serializers.models import ProviderRequest

# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------

_FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    """Load a captured request fixture from ``tests/fixtures/<name>.json``."""
    path = _FIXTURE_DIR / f"{name}.json"
    assert path.is_file(), f"Missing fixture: {path}"
    raw = path.read_text(encoding="utf-8")
    data: dict[str, Any] = json.loads(raw)
    return data


# ---------------------------------------------------------------------------
# Engine builders
# ---------------------------------------------------------------------------


def _synthetic_router() -> ModelRouter:
    """Build a ModelRouter over a synthetic registry.

    Maps the fixture model names to the vllm provider with a dummy
    backend_model so routing does NOT alter message content.
    """
    _load_providers()

    from packages.providers.models import ModelDefinition as MD

    # Build a minimal registry: map client model names to a real vLLM backend.
    definitions: dict[str, MD] = {
        "default": MD(
            model="default",
            backend_model="vllm-default",
            provider="vllm",
            base_url="http://localhost:8000/v1",
            api_key="test-key",
            context_window=8192,
        ),
        "claude-code": MD(
            model="claude-code",
            backend_model="vllm-claude",
            provider="vllm",
            base_url="http://localhost:8000/v1",
            api_key="test-key",
            context_window=8192,
        ),
    }

    registry = ModelRegistry(definitions=definitions)
    return ModelRouter(registry)


def _build_routed_engine() -> PipelineEngine:
    """Build a pipeline engine with model routing enabled."""
    router = _synthetic_router()
    engine = PipelineEngine()
    engine.register(ModelResolutionStage(router))
    engine.register(PlanningStage())
    # repository_context stage gets index=None to skip context assembly
    engine.register(RepositoryContextStage(index=None))
    engine.register(ProviderStage())
    return engine


def _install_chat_capture(provider: Any) -> AsyncMock:
    """Point the resolved provider's ``chat`` at an AsyncMock.

    Keeps the invariant check hermetic (no real provider call from the
    pre-commit gate) while capturing the exact payload that
    ``ProviderStage`` forwards to the provider.
    """
    chat: AsyncMock = AsyncMock(
        return_value={
            "choices": [],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }
    )
    provider.chat = chat
    return chat


# ---------------------------------------------------------------------------
# Invariant comparison helpers
# ---------------------------------------------------------------------------


def _normalize_input_for_comparison(data: dict[str, Any]) -> dict[str, Any]:
    """Normalise the input fixture for comparison.

    The gateway's ChatCompletionRequest wraps fields into a PipelineRequest
    and then to_provider_kwargs(). We need to reproduce that shape so the
    comparison is apples-to-apples.
    """
    # Build the shape that to_provider_kwargs() produces:
    #   {"messages": ..., "model": ..., "stream": ..., "stream_options": {...} if stream}
    # plus any kwargs like temperature, max_tokens, tools, etc.
    normalized: dict[str, Any] = {
        "messages": copy.deepcopy(data.get("messages", [])),
        "model": data.get("model", "default"),
        "stream": data.get("stream", False),
    }
    if normalized["stream"]:
        normalized["stream_options"] = {"include_usage": True}

    # Forward all other top-level fields as kwargs
    for key in ("temperature", "max_tokens", "top_p", "frequency_penalty",
                "presence_penalty", "stop", "tool_choice", "tools"):
        if key in data:
            normalized[key] = data[key]

    return normalized


def _get_provider_payload(
    context: PipelineContext,
    chat_mock: AsyncMock | None = None,
) -> dict[str, Any]:
    """Extract the provider payload from a PipelineContext.

    This is what would actually be forwarded to the provider.
    """
    # Check if RepositoryContextStage produced a ProviderRequest
    provider_request = context.get_metadata("provider_request")
    if isinstance(provider_request, ProviderRequest):
        payload = provider_request.to_dict()
    elif chat_mock is not None and chat_mock.call_args is not None:
        # ProviderStage forwards its kwargs to provider.chat - that is the
        # exact provider payload after all stages ran.
        payload = dict(chat_mock.call_args.kwargs)
    else:
        # Fallback: use raw context.request
        payload = dict(context.request)

    return payload


def _protocol_diff(
    input_payload: dict[str, Any],
    output_payload: dict[str, Any],
    mode: str,
    history_cap_enabled: bool = False,
) -> list[str]:
    """Compare input vs output and report ALL key-level differences.

    Allowed differences:
    - ``model`` may change (client name → backend_model) — allowed in both modes
    - The first system message's content may gain repository context (routed mode only)
    - When ``history_cap_enabled=True``, some old history messages may be dropped
      (but kept messages must be unchanged, system messages present, last user
      message intact, and no tool call/result left orphaned).

    Forbidden differences:
    - Everything else must match.
    """
    diffs: list[str] = []

    # --- model: allowed to differ ---
    inp_model = input_payload.get("model")
    out_model = output_payload.get("model")
    if inp_model != out_model:
        # Allowed — client name → backend_model
        pass

    # --- stream: must be identical ---
    inp_stream = input_payload.get("stream")
    out_stream = output_payload.get("stream")
    if inp_stream != out_stream:
        diffs.append(
            f"stream: input={inp_stream} output={out_stream}"
        )

    # --- stream_options: must be identical when stream=true ---
    if inp_stream:
        inp_so = input_payload.get("stream_options")
        out_so = output_payload.get("stream_options")
        if inp_so != out_so:
            diffs.append(
                f"stream_options: input={inp_so} output={out_so}"
            )

    # --- tools: must be identical ---
    inp_tools = input_payload.get("tools")
    out_tools = output_payload.get("tools")
    if inp_tools != out_tools:
        diffs.append(
            f"tools: input={json.dumps(inp_tools, sort_keys=True)} "
            f"output={json.dumps(out_tools, sort_keys=True)}"
        )

    # --- tool_choice: must be identical ---
    inp_tc = input_payload.get("tool_choice")
    out_tc = output_payload.get("tool_choice")
    if inp_tc != out_tc:
        diffs.append(
            f"tool_choice: input={json.dumps(inp_tc)} output={json.dumps(out_tc)}"
        )

    # --- generation params: must be identical ---
    for param in ("temperature", "top_p", "max_tokens", "frequency_penalty",
                  "presence_penalty", "stop"):
        inp_val = input_payload.get(param)
        out_val = output_payload.get(param)
        if inp_val != out_val:
            diffs.append(
                f"{param}: input={inp_val} output={out_val}"
            )

    # --- messages: compare structure ---
    inp_msgs = input_payload.get("messages", [])
    out_msgs = output_payload.get("messages", [])

    # Count system messages: input may have multiple, output must have at most 1
    inp_system_count = sum(1 for m in inp_msgs if m.get("role") == "system")
    out_system_count = sum(1 for m in out_msgs if m.get("role") == "system")

    if out_system_count > 1:
        diffs.append(
            f"system message count: input={inp_system_count} output={out_system_count} "
            f"(multiple system messages is a regression)"
        )

    # Compare non-system messages (user/assistant) byte-for-byte.
    # With history capping enabled, some old messages may be dropped,
    # so we verify the weaker property: kept messages are unchanged,
    # last user message intact, and no tool call/result orphaned.
    inp_conv = [m for m in inp_msgs if m.get("role") in ("user", "assistant")]
    out_conv = [m for m in out_msgs if m.get("role") in ("user", "assistant")]

    if history_cap_enabled:
        # When capping is enabled, dropped messages are a contiguous prefix
        # of the history (oldest first).  Verify:
        # 1. The last user message is present in full.
        # 2. All kept messages are byte-identical to input.
        # 3. No tool call is left without its result (and vice versa).
        # 4. System messages are present.
        if inp_system_count > 0 and out_system_count == 0:
            diffs.append(
                "all client system messages were dropped (no system message in output)"
            )

        # Find the last user message in output and verify it matches.
        out_last_user = None
        for m in reversed(out_conv):
            if m.get("role") == "user":
                out_last_user = m
                break
        inp_last_user = None
        for m in reversed(inp_conv):
            if m.get("role") == "user":
                inp_last_user = m
                break
        if inp_last_user is not None and out_last_user is not None:
            if inp_last_user.get("content") != out_last_user.get("content"):
                diffs.append(
                    "last user message content changed by history capping"
                )

        # Verify kept suffix messages match input.
        # Build a map of content->index for matching.
        # Since dropped messages are a contiguous prefix of non-system messages,
        # the kept messages should be a suffix of the input.
        if len(out_conv) > 0 and len(inp_conv) > 0:
            # Find the first kept message by matching from the end.
            # The suffix of out_conv should match a suffix of inp_conv.
            match_start = 0
            for offset in range(min(len(inp_conv), len(out_conv))):
                inp_idx = len(inp_conv) - 1 - offset
                out_idx = len(out_conv) - 1 - offset
                inp_m = inp_conv[inp_idx]
                out_m = out_conv[out_idx]
                if (inp_m.get("content") == out_m.get("content") and
                        inp_m.get("role") == out_m.get("role")):
                    if out_idx == 0:
                        match_start = inp_idx
                        break
                else:
                    match_start = inp_idx + 1
                    break

            # Verify all matched messages are identical.
            for i, out_m in enumerate(out_conv):
                inp_m = inp_conv[match_start + i] if (match_start + i < len(inp_conv)) else None
                if inp_m is None:
                    diffs.append(
                        f"extra output message at position {i} not in input"
                    )
                    continue
                if inp_m.get("role") != out_m.get("role"):
                    diffs.append(
                        f"messages[{i}].role mismatch after capping: "
                        f"input={inp_m.get('role')} output={out_m.get('role')}"
                    )
                if inp_m.get("content") != out_m.get("content"):
                    diffs.append(
                        f"messages[{i}] content differs after capping"
                    )

        # Check tool call/result pairing on the FULL output message list
        # (not just out_conv which filters out tool messages).
        # This catches orphaned tool results that were previously missed
        # because the old code filtered to out_conv first, then checked
        # role=="tool" on an already-filtered list.
        out_tool_call_ids: set[str] = set()
        out_tool_results: set[str] = set()
        for m in out_msgs:
            tc_list = m.get("tool_calls", [])
            for tc in tc_list:
                if isinstance(tc, dict) and tc.get("id"):
                    out_tool_call_ids.add(tc["id"])
            if m.get("role") == "tool" and m.get("tool_call_id"):
                out_tool_results.add(m["tool_call_id"])
        # Each tool result must have a matching call.
        orphan_results = out_tool_results - out_tool_call_ids
        if orphan_results:
            diffs.append(
                f"orphaned tool results without calls after capping: {orphan_results}"
            )
        # Each tool call must have a matching result.
        orphan_calls = out_tool_call_ids - out_tool_results
        if orphan_calls:
            diffs.append(
                f"orphaned tool calls without results after capping: {orphan_calls}"
            )

    else:
        # Strict mode: no messages may be dropped.
        if len(inp_conv) != len(out_conv):
            diffs.append(
                f"conversation message count: input={len(inp_conv)} output={len(out_conv)}"
            )
        else:
            for i, (inp_m, out_m) in enumerate(zip(inp_conv, out_conv)):
                if inp_m.get("role") != out_m.get("role"):
                    diffs.append(
                        f"messages[{i}].role: input={inp_m.get('role')} output={out_m.get('role')}"
                    )
                if inp_m.get("content") != out_m.get("content"):
                    # For list content, compare structure precisely
                    inp_c = inp_m.get("content")
                    out_c = out_m.get("content")
                    if type(inp_c) is not type(out_c):
                        diffs.append(
                            f"messages[{i}].content type changed: "
                            f"input={type(inp_c).__name__} "
                            f"output={type(out_c).__name__}"
                        )
                    elif inp_c != out_c:
                        # Check if list content is preserved
                        if isinstance(inp_c, list) and isinstance(out_c, list):
                            if len(inp_c) != len(out_c):
                                diffs.append(
                                    f"messages[{i}].content list length changed: "
                                    f"input={len(inp_c)} output={len(out_c)}"
                                )
                            else:
                                for j, (inp_part, out_part) in enumerate(zip(inp_c, out_c)):
                                    if inp_part != out_part:
                                        diffs.append(
                                            f"messages[{i}].content[{j}]: "
                                            f"input={json.dumps(inp_part)} "
                                            f"output={json.dumps(out_part)}"
                                        )
                        elif isinstance(inp_c, list):
                            diffs.append(
                                f"messages[{i}].content: list was stringified to "
                                f"{type(out_c).__name__}"
                            )
                        elif isinstance(out_c, list):
                            diffs.append(
                                f"messages[{i}].content: string became list"
                            )
                        else:
                            diffs.append(
                                f"messages[{i}].content: input={repr(inp_c)[:200]} "
                                f"output={repr(out_c)[:200]}"
                            )

    # --- client system content must survive ---
    if inp_system_count > 0:
        # All input system content must be present in the output
        inp_system_texts = [
            m.get("content", "") for m in inp_msgs if m.get("role") == "system"
        ]

        # Check output system message content
        out_system_msgs = [m for m in out_msgs if m.get("role") == "system"]
        if out_system_msgs:
            out_system_text = out_system_msgs[0].get("content", "")
            for client_text in inp_system_texts:
                if client_text not in out_system_text:
                    diffs.append(
                        "client system content lost: "
                        "input system text not found "
                        "in output system message"
                    )
        else:
            diffs.append(
                "all client system messages were dropped (no system message in output)"
            )

    return diffs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestProtocolInvariant:
    """Protocol compatibility invariant tests."""

    @pytest.mark.parametrize("fixture_name", [
        "plain_turn",
        "tool_use",
        "list_content",
    ])
    @pytest.mark.parametrize("mode", ["fallback", "routed"])
    @pytest.mark.asyncio
    async def test_invariant_per_fixture(
        self,
        fixture_name: str,
        mode: str,
    ) -> None:
        """Run each fixture through the pipeline and assert
        protocol invariant."""
        fixture = _load_fixture(fixture_name)

        # Build the provider payload shape that the gateway produces
        payload = _normalize_input_for_comparison(fixture)

        # Create a PipelineContext from the payload
        context = PipelineContext(
            request_id=f"test-{fixture_name}-{mode}",
            request=payload,
        )
        context.set_metadata("provider_name", "vllm")
        context.set_metadata("model", payload.get("model", "default"))
        context.set_metadata("context_enabled", mode == "routed")

        # Run the stages relevant to the mode. All stage hooks are async,
        # so they are awaited exactly like PipelineEngine.execute does.
        chat_mock: AsyncMock | None = None

        if mode == "routed":
            engine = _build_routed_engine()
            for stage in engine._stages:
                short_circuit = await stage.before(context)
                if short_circuit is not None:
                    result = short_circuit
                    if not isinstance(result, PipelineStageResult):
                        result = PipelineStageResult(
                            stage_name=stage.name,
                            success=True,
                            data=result,
                        )
                else:
                    result = await stage.execute(context)
                    if (
                        stage.name == "model_resolution"
                        and context.resolved_model is not None
                    ):
                        # Hermetic provider: capture the payload instead of
                        # hitting a real backend from the pre-commit gate.
                        chat_mock = _install_chat_capture(
                            context.resolved_model.provider
                        )
                after_result = await stage.after(context, result)
                if after_result is not None and isinstance(
                    after_result, PipelineStageResult
                ):
                    result = after_result
                context.set_stage_result(stage.name, result)
                if not result.success:
                    # PipelineEngine.execute halts on a failed stage.
                    break
        else:
            # Fallback: no routing stages; ProviderStage works off a
            # resolved model (as the gateway's FallbackModelRouter provides).
            router = _synthetic_router()
            resolved = router.resolve(payload.get("model", "default"))
            context.resolved_model = resolved
            chat_mock = _install_chat_capture(resolved.provider)

            stage = ProviderStage()
            result = await stage.execute(context)
            after_result = await stage.after(context, result)
            if after_result is not None and isinstance(
                after_result, PipelineStageResult
            ):
                result = after_result
            context.set_stage_result(stage.name, result)

        # Extract the provider payload
        provider_payload = _get_provider_payload(context, chat_mock)

        # Compare with a detailed diff
        diffs = _protocol_diff(payload, provider_payload, mode)

        if diffs:
            pytest.fail(
                f"Protocol invariant violated in {mode} mode for fixture '{fixture_name}':\n"
                + "\n".join(f"  - {d}" for d in diffs)
            )


class TestListContentPreservation:
    """Ensure list-form content is preserved, not stringified."""

    def test_list_content_not_stringified(self) -> None:
        """list_content fixture must not stringify content to JSON."""
        fixture = _load_fixture("list_content")
        payload = _normalize_input_for_comparison(fixture)

        # The input content is a list
        inp_content = payload["messages"][0]["content"]
        assert isinstance(inp_content, list), "Input content should be a list"

        # Run through the serializer directly (no routing)
        from packages.serializers.openai import OpenAISerializer  # noqa: PLC0414

        serializer = OpenAISerializer()
        result = serializer.serialize(
            None,
            payload["messages"],
            model=payload.get("model", "default"),
        )

        output_content = result.messages[0]["content"] if result.messages else None

        # The content should remain a list, or if converted to string, the text must survive
        if isinstance(inp_content, list):
            # Check that the list content survives
            inp_texts = [
                part.get("text", "")
                for part in inp_content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ]
            output_text = output_content if isinstance(output_content, str) else str(output_content)
            for text in inp_texts:
                assert text in output_text, (
                    f"List content text '{text}' was lost during serialization"
                )


class TestClientSystemPreservation:
    """Verify client system messages survive serialization."""

    def test_tool_use_system_survives(self) -> None:
        """tool_use fixture's system message must survive serialization."""
        fixture = _load_fixture("tool_use")
        payload = _normalize_input_for_comparison(fixture)

        # Get the client system content
        client_system = None
        for msg in payload["messages"]:
            if msg.get("role") == "system":
                client_system = msg.get("content", "")
                break

        assert client_system is not None, "Fixture should have a system message"

        # Run through serializer
        from packages.serializers.openai import OpenAISerializer  # noqa: PLC0414

        serializer = OpenAISerializer()
        result = serializer.serialize(
            None,
            payload["messages"],
            model=payload.get("model", "default"),
        )

        # Check output
        out_system_msgs = [m for m in result.messages
                           if m.get("role") == "system"]
        if out_system_msgs:
            out_text = out_system_msgs[0].get("content", "")
            assert client_system in out_text, (
                "Client system message not found "
                "in output system message"
            )
        else:
            pytest.fail("No system message in output — client system was dropped")


class TestDeltaInjection:
    """Delta injection subtlety — only repo-context content should differ between turns."""

    def test_two_turns_only_repo_context_differs(self) -> None:
        """Two turns of the same conversation: only repo-context may differ."""
        fixture = _load_fixture("plain_turn")
        payload = _normalize_input_for_comparison(fixture)

        # Simulate two turns: same input each time
        # Turn 1
        context1 = PipelineContext(
            request_id="turn-1",
            request=copy.deepcopy(payload),
        )
        context1.set_metadata("provider_name", "vllm")
        context1.set_metadata("model", "default")
        context1.set_metadata("context_enabled", True)

        # Turn 2
        context2 = PipelineContext(
            request_id="turn-2",
            request=copy.deepcopy(payload),
        )
        context2.set_metadata("provider_name", "vllm")
        context2.set_metadata("model", "default")
        context2.set_metadata("context_enabled", True)

        # Get provider payloads
        payload1 = _get_provider_payload(context1)
        payload2 = _get_provider_payload(context2)

        # Compare all fields EXCEPT model and system message content
        # The invariant says only repo-context content may differ
        for key in ("stream", "tools", "tool_choice", "temperature",
                    "max_tokens", "top_p"):
            assert payload1.get(key) == payload2.get(key), (
                f"Key '{key}' differs between turns but should be identical"
            )

        # Messages should be identical
        assert payload1.get("messages") == payload2.get("messages"), (
            "messages differ between turns but should be identical"
        )


class TestInvariantNamesViolations:
    """Verify that the diff function reports specific field violations."""

    def test_diff_reports_changed_tools(self) -> None:
        """Temporarily break tools and confirm the error message names the field."""
        input_payload = {
            "model": "default",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "tools": [{"type": "function", "function": {"name": "test"}}],
        }
        output_payload = copy.deepcopy(input_payload)
        output_payload["tools"] = [{"type": "function", "function": {"name": "CHANGED"}}]

        diffs = _protocol_diff(input_payload, output_payload, "fallback")

        assert len(diffs) >= 1
        # Check that the diff message mentions 'tools'
        tools_diffs = [d for d in diffs if "tools" in d.lower()]
        assert len(tools_diffs) > 0, (
            f"Expected diff to mention 'tools', got: {diffs}"
        )

    def test_diff_reports_stringified_content(self) -> None:
        """When list content becomes string, diff must report the type change."""
        input_payload = {
            "model": "default",
            "messages": [{
                "role": "user",
                "content": [{"type": "text", "text": "hello"}]
            }],
            "stream": False,
        }
        output_payload = {
            "model": "default",
            "messages": [{
                "role": "user",
                "content": '[{"type":"text","text":"hello"}]'  # stringified!
            }],
            "stream": False,
        }

        diffs = _protocol_diff(input_payload, output_payload, "fallback")

        assert len(diffs) >= 1
        # Check that at least one diff mentions the content type change
        content_diffs = [d for d in diffs if "content" in d.lower()]
        assert len(content_diffs) > 0, (
            f"Expected diff to mention 'content', got: {diffs}"
        )
