"""Background refresh for the change-aware repository-context signal.

The signal itself is synchronous - one capture costs two read-only Git
commands, which is fine during startup and unacceptable inside a request.
This module keeps those two worlds apart.

.. code-block:: text

    lifespan startup -> ChangedFilesRefresher.start()
                           |
                    sleep once per TTL window
                           v
                    asyncio.to_thread(signal.refresh())
                           |
                           v
                    signal cache -> module_paths() per request

Nothing here starts a process: the only Git vectors remain the two allowlisted
read-only commands inside :mod:`packages.repository.git_changes`, and each of
those already carries its own wall-clock budget.

Constraints
-----------

- One refresh at a time, so a slow Git can never pile up worker threads.
- Failures are counted and logged by exception type; nothing escapes the task.
- The request path never waits on this task - when the TTL disables
  refreshing, the task is not even created.

Public API
----------

.. code-block:: python

    from packages.repository.changed_files_refresh import ChangedFilesRefresher

    refresher = ChangedFilesRefresher(signal)
    refresher.start()
    ...
    await refresher.stop()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

__all__ = ["ChangedFilesRefresher"]

logger = logging.getLogger(__name__)


class RefreshableChangeSignal(Protocol):
    """The slice of :class:`ChangedFilesSignal` this loop depends on."""

    @property
    def ttl_seconds(self) -> float:
        """Minimum seconds between two captures; ``0`` disables refreshing."""
        ...

    def refresh(self) -> bool:
        """Capture once the window has elapsed; return whether it captured."""
        ...

    def module_paths(self) -> frozenset[str]:
        """Return the cached keys; must never capture."""
        ...


class ChangedFilesRefresher:
    """Refresh a change signal on its TTL window, off the event loop.

    Attributes:
        _signal: The signal whose cache stays warm.
        _interval: Seconds to sleep between refresh attempts.
        _task: The running loop, or ``None`` when it never started.
        _refresh_count: How many refresh attempts have completed.
        _failure_count: How many attempts raised, which they should not.
    """

    def __init__(
        self,
        signal: RefreshableChangeSignal,
        *,
        interval_seconds: float | None = None,
    ) -> None:
        """Initialise the refresher.

        Args:
            signal: The signal to keep fresh.
            interval_seconds: Sleep between attempts. Defaults to the
                signal's own TTL, which is the only sensible interval and is
                what makes a TTL of ``0`` mean "never refresh".
        """
        self._signal = signal
        self._interval = (
            float(signal.ttl_seconds) if interval_seconds is None else float(interval_seconds)
        )
        self._task: asyncio.Task[None] | None = None
        self._refresh_count = 0
        self._failure_count = 0

    @property
    def interval_seconds(self) -> float:
        """Seconds between refresh attempts; ``0`` means the loop is disabled."""
        return self._interval

    @property
    def running(self) -> bool:
        """Whether a refresh loop is currently scheduled."""
        return self._task is not None and not self._task.done()

    @property
    def refresh_count(self) -> int:
        """How many refresh attempts have completed."""
        return self._refresh_count

    @property
    def failure_count(self) -> int:
        """How many refresh attempts raised out of the signal."""
        return self._failure_count

    def start(self) -> "asyncio.Task[None] | None":
        """Schedule the refresh loop on the running event loop.

        Called from application lifespan startup. A TTL of ``0`` - the default
        - means the snapshot is taken once and never revisited, so no task is
        created and nothing here runs again.

        Returns:
            The scheduled task, or ``None`` when refreshing is disabled or the
            loop was already started.

        Raises:
            RuntimeError: If no event loop is running.
        """
        if self._interval <= 0.0:
            return None
        if self.running:
            return self._task
        self._task = asyncio.create_task(self._loop(), name="changed-files-refresher")
        return self._task

    async def stop(self) -> None:
        """Cancel the loop and wait for it to finish.

        An in-flight capture runs on a worker thread and cannot be interrupted;
        it stays bounded by the Git command timeout, and its only effect is a
        cache write nobody waits for.
        """
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _loop(self) -> None:
        """Sleep one window, refresh off the loop, repeat."""
        while True:
            await asyncio.sleep(self._interval)
            try:
                captured: bool = await asyncio.to_thread(self._signal.refresh)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # defensive: refresh must not raise
                self._failure_count += 1
                logger.warning(
                    "changed_files_refresh status=failed error=%s",
                    type(error).__name__,
                )
                continue
            self._refresh_count += 1
            if captured:
                logger.info(
                    "changed_files_refresh status=captured paths=%d",
                    len(self._signal.module_paths()),
                )
