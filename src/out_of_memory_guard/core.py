"""Core memory guard implementation.

This module provides a small, dependency-free guard that detects when the
process is approaching memory exhaustion and temporarily disables
non-essential handlers before allocation failures crash the process.

The design deliberately avoids reading /proc/self/status or calling
os.sysconf directly in the hot path. Instead the caller injects a
``memory_reader`` callable that returns the current available memory in
bytes. That keeps the library testable without relying on the host's
actual memory state, and lets callers plug in cgroup-aware readers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List


@dataclass
class GuardState:
    """Mutable bookkeeping for a :class:`MemoryGuard`.

    Attributes:
        disabled: Names of handlers that the guard has temporarily disabled.
        threshold_bytes: The available-memory threshold below which handlers
            are disabled.
        resume_bytes: The available-memory threshold at or above which
            handlers are re-enabled. Using a distinct resume threshold avoids
            flapping when memory hovers around the disable threshold.
    """

    disabled: List[str] = field(default_factory=list)
    threshold_bytes: int = 0
    resume_bytes: int = 0


class MemoryGuard:
    """Disable non-essential handlers when memory runs low.

    The guard is intentionally synchronous and side-effect free apart from
    toggling the handler callables it is given. It does not spawn threads or
    install signal handlers; callers decide when to call :meth:`check`.

    Args:
        memory_reader: Callable returning available memory in bytes. Must be
            monotonic in the sense that it reflects the current state; a
            decreasing value indicates memory pressure.
        threshold_bytes: Available memory at or below which handlers are
            disabled.
        resume_bytes: Available memory at or above which handlers are
            re-enabled. Must be greater than or equal to ``threshold_bytes``.

    Raises:
        ValueError: If ``resume_bytes`` is less than ``threshold_bytes``.
    """

    def __init__(
        self,
        memory_reader: Callable[[], int],
        threshold_bytes: int,
        resume_bytes: int,
    ) -> None:
        if resume_bytes < threshold_bytes:
            raise ValueError("resume_bytes must be >= threshold_bytes")
        self._memory_reader = memory_reader
        self._handlers: dict[str, Callable[[], None]] = {}
        self._state = GuardState(
            threshold_bytes=threshold_bytes,
            resume_bytes=resume_bytes,
        )

    @property
    def state(self) -> GuardState:
        """Return the current guard state.

        The returned object is the live state, not a copy. Callers that only
        need to inspect it should not mutate it.
        """
        return self._state

    def register(self, name: str, handler: Callable[[], None]) -> None:
        """Register a non-essential handler under ``name``.

        Registering the same name twice replaces the previous handler. The
        replacement inherits whatever enabled/disabled status the name
        currently has.
        """
        self._handlers[name] = handler

    def unregister(self, name: str) -> None:
        """Remove a handler by name. No-op if the name is unknown."""
        self._handlers.pop(name, None)
        if name in self._state.disabled:
            self._state.disabled.remove(name)

    def is_disabled(self, name: str) -> bool:
        """Return True if the named handler is currently disabled."""
        return name in self._state.disabled

    def check(self) -> bool:
        """Evaluate memory and toggle handlers.

        Returns True if handlers are currently disabled, False otherwise.
        Handlers are disabled when available memory is at or below
        ``threshold_bytes`` and re-enabled when it is at or above
        ``resume_bytes``. Between the two thresholds the previous state is
        kept, which prevents rapid toggling.
        """
        available = self._memory_reader()
        if available <= self._state.threshold_bytes:
            self._disable_all()
        elif available >= self._state.resume_bytes:
            self._enable_all()
        return bool(self._state.disabled)

    def _disable_all(self) -> None:
        for name in self._handlers:
            if name not in self._state.disabled:
                self._state.disabled.append(name)

    def _enable_all(self) -> None:
        self._state.disabled.clear()

    def run_essential(self, func: Callable[[], None]) -> None:
        """Run ``func`` regardless of guard state.

        Essential work should not be gated by this guard. This helper exists
        so callers do not have to remember which path bypasses the guard.
        """
        func()

    def run_handlers(self) -> List[str]:
        """Run all enabled handlers and return their names.

        Disabled handlers are skipped. Handlers run in registration order.
        """
        ran: List[str] = []
        for name, handler in self._handlers.items():
            if name in self._state.disabled:
                continue
            handler()
            ran.append(name)
        return ran
