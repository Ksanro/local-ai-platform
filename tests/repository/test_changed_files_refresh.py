"""Focused tests for the background change-signal refresher.

The refresher exists so that a TTL above zero cannot put Git into the request
path: refreshes must happen on a worker thread, at most one at a time, and a
failing refresh must never escape the task or stop the loop.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from packages.repository.changed_files_refresh import ChangedFilesRefresher


class _StubSignal:
    """Refreshable signal that records which thread called it."""

    def __init__(
        self,
        ttl_seconds: float = 0.05,
        *,
        error: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self._ttl = ttl_seconds
        self._error = error
        self._delay = delay
        self.threads: list[int] = []
        self.reads = 0

    @property
    def ttl_seconds(self) -> float:
        """The configured refresh window."""
        return self._ttl

    def refresh(self) -> bool:
        """Record the calling thread, then behave as scripted."""
        self.threads.append(threading.get_ident())
        if self._delay:
            # Blocks the worker thread only - the event loop must stay free.
            threading.Event().wait(self._delay)
        if self._error is not None:
            raise self._error
        return True

    def module_paths(self) -> frozenset[str]:
        """Return the cached keys and count the read."""
        self.reads += 1
        return frozenset({"packages/a/mod"})


def test_disabled_ttl_creates_no_task() -> None:
    """The default policy needs no background work at all."""
    refresher = ChangedFilesRefresher(_StubSignal(0.0))

    assert refresher.interval_seconds == 0.0
    assert refresher.start() is None
    assert refresher.running is False


def test_interval_defaults_to_the_signal_ttl() -> None:
    """One window, one attempt - the signal already owns the policy."""
    refresher = ChangedFilesRefresher(_StubSignal(45.0))

    assert refresher.interval_seconds == 45.0


@pytest.mark.asyncio
async def test_refresh_runs_off_the_event_loop() -> None:
    """A blocking Git call must never occupy the loop that serves requests."""
    signal = _StubSignal(0.01, delay=0.2)
    refresher = ChangedFilesRefresher(signal)
    refresher.start()

    ticks = 0
    for _ in range(40):
        await asyncio.sleep(0.01)
        ticks += 1

    await refresher.stop()

    assert signal.threads, "the refresh never ran"
    assert signal.threads[0] != threading.get_ident()
    assert ticks == 40  # the loop kept scheduling this coroutine throughout


@pytest.mark.asyncio
async def test_refresh_repeats_once_per_window_and_stops_on_demand() -> None:
    """The loop is periodic, and cancelling it is enough to end it."""
    signal = _StubSignal(0.02)
    refresher = ChangedFilesRefresher(signal)
    task = refresher.start()

    assert task is not None
    assert refresher.running is True
    await asyncio.sleep(0.12)
    await refresher.stop()

    assert refresher.refresh_count >= 3
    assert refresher.running is False
    assert task.cancelled() or task.done()
    after = refresher.refresh_count
    await asyncio.sleep(0.05)
    assert refresher.refresh_count == after


@pytest.mark.asyncio
async def test_failing_refresh_never_escapes_the_loop(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A surprise from the signal is counted, logged by type, and survived."""
    signal = _StubSignal(0.01, error=RuntimeError("boom at /very/secret/path"))
    refresher = ChangedFilesRefresher(signal)
    refresher.start()

    await asyncio.sleep(0.05)
    await refresher.stop()

    assert refresher.failure_count >= 1
    assert refresher.refresh_count == 0
    assert refresher.running is False
    assert "RuntimeError" in caplog.text
    assert "/very/secret/path" not in caplog.text
