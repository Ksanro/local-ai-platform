"""Docs-level test that /debug/runtime-context snippets stay aligned.

This is a tiny docs-consistency test, not a live probe. It reads the static
docs and asserts the documented `curl` command and the inspect-field list in
`docs/live-gateway-runbook.md` match the real endpoint, and that `README.md`
points operators at the same command. Keeping these snippets in a test catches
silent drift when the endpoint path or response keys change.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "live-gateway-runbook.md"
README = REPO_ROOT / "README.md"

# These must match the real endpoint in apps/gateway/api/runtime_context.py
# and the response keys asserted in test_runtime_context.py.
CURL_SNIPPET = "curl http://127.0.0.1:8001/debug/runtime-context"
INSPECT_FIELDS = (
    "default_model",
    "routing_mode",
    "models[].base_url",
    "models[].backend_model",
    "repository_context_intent_budget_map",
    "quality_baseline.available",
    "quality_baseline.latest_score",
    "gateway_session_summary.available",
    "gateway_session_summary.success_rate",
    "gateway_session_summary.recent_errors",
)


def _read(path: Path) -> str:
    assert path.exists(), f"expected docs file is missing: {path}"
    return path.read_text(encoding="utf-8")


def test_runbook_documents_runtime_context_command_and_fields() -> None:
    text = _read(RUNBOOK)

    assert "## Runtime Context Introspection" in text
    assert CURL_SNIPPET in text
    for field in INSPECT_FIELDS:
        assert f"`{field}`" in text, f"runbook is missing inspect field `{field}`"


def test_readme_points_to_runtime_context_command() -> None:
    text = _read(README)

    assert "curl http://localhost:8001/debug/runtime-context" in text
    assert "docs/live-gateway-runbook.md" in text
