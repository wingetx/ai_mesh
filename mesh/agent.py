"""
agent.py — Base class for agents that live on the bus.

An Agent has:
  - a name (its sender id on the bus)
  - one or more subscribed channels
  - an `on_message(envelope)` callable that handles each new message

`Agent.run()` polls the bus for new messages on its channels and dispatches
them. Agents are intentionally simple: a name, a handler, a loop. Anything
more (LLM calls, tools, memory) is the handler's responsibility.
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Callable, Iterable, Optional

from mesh.bus import Bus, Envelope

log = logging.getLogger(__name__)


class Agent:
    """A bus-resident agent. Subclass and override `on_message`,
    or pass a handler at construction.
    """

    def __init__(
        self,
        name: str,
        channels: Iterable[str],
        bus: Optional[Bus] = None,
        handler: Optional[Callable[["Agent", Envelope], None]] = None,
        poll_interval: float = 0.25,
    ):
        self.name = name
        self.channels: list[str] = list(channels)
        if not self.channels:
            raise ValueError("Agent must subscribe to at least one channel")
        self.bus = bus or Bus()
        self.handler = handler
        self.poll_interval = poll_interval
        self._cursor: int = self._latest_id()
        self._running = False

    # ── overrides ───────────────────────────────────────────────────────
    def on_message(self, env: Envelope) -> None:
        """Default: invoke the handler if one was provided; else log only."""
        if self.handler is not None:
            self.handler(self, env)
        else:
            log.debug("[%s] received #%s on %s: %r", self.name, env.id, env.channel, env.body)

    # ── publishing ──────────────────────────────────────────────────────
    def say(
        self,
        channel: str,
        body,
        *,
        kind: str = "say",
        in_reply_to: Optional[str] = None,
    ) -> Envelope:
        return self.bus.send(
            channel=channel,
            sender=self.name,
            body=body,
            kind=kind,
            in_reply_to=in_reply_to,
        )

    # ── loop ────────────────────────────────────────────────────────────
    def _latest_id(self) -> int:
        # Start past any existing traffic so agents don't replay history
        # on startup.
        with self.bus._connect() as conn:  # noqa: SLF001 — intentional internal use
            row = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM messages").fetchone()
        return int(row["m"])

    def step(self) -> int:
        """Process any new messages and return the number handled."""
        envs = self.bus.fetch(self.channels, after_id=self._cursor)
        count = 0
        for env in envs:
            # Don't react to your own messages.
            if env.sender == self.name:
                self._cursor = env.id  # type: ignore[assignment]
                continue
            try:
                self.on_message(env)
            except Exception:
                log.exception("[%s] handler error on msg #%s", self.name, env.id)
            self._cursor = env.id  # type: ignore[assignment]
            count += 1
        return count

    def run(self, stop_after: Optional[float] = None) -> None:
        """Poll forever (or until SIGINT / `stop_after` seconds)."""
        self._running = True
        deadline = (time.time() + stop_after) if stop_after else None

        def _stop(_sig, _frm):
            self._running = False

        installed_handler = False
        prev = None
        if threading.current_thread() is threading.main_thread():
            try:
                prev = signal.signal(signal.SIGINT, _stop)
                installed_handler = True
            except (ValueError, OSError):
                pass  # signals unavailable in this environment
        try:
            while self._running:
                self.step()
                if deadline is not None and time.time() >= deadline:
                    break
                time.sleep(self.poll_interval)
        finally:
            if installed_handler:
                signal.signal(signal.SIGINT, prev)
