"""Tests for the provider payload built from a normalized request."""

from __future__ import annotations

from packages.pipeline.normalized import NormalizedRequest


def test_streaming_payload_requests_usage_by_default() -> None:
    """A streaming request asks the backend for a final usage chunk."""
    payload = NormalizedRequest.from_client(
        {"messages": [], "model": "m", "stream": True}
    ).to_provider_payload()

    assert payload["stream_options"] == {"include_usage": True}


def test_client_stream_options_are_kept_and_usage_stays_requested() -> None:
    """A client's own ``stream_options`` survives without switching usage off.

    Undeclared fields are forwarded from the gateway now, so a client's
    ``stream_options`` would otherwise replace the gateway's and could stop
    the session log receiving usage.
    """
    payload = NormalizedRequest.from_client(
        {
            "messages": [],
            "model": "m",
            "stream": True,
            "stream_options": {"include_usage": False, "continuous_usage_stats": True},
        }
    ).to_provider_payload()

    assert payload["stream_options"] == {
        "include_usage": True,
        "continuous_usage_stats": True,
    }


def test_non_streaming_payload_passes_client_stream_options_through() -> None:
    """Without streaming the gateway adds nothing and forwards what it got."""
    payload = NormalizedRequest.from_client(
        {"messages": [], "model": "m", "stream_options": {"x": 1}}
    ).to_provider_payload()

    assert payload["stream"] is False
    assert payload["stream_options"] == {"x": 1}
