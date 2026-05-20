"""
echo.py — Trivial echo adapter (no LLM).

Useful for tests, demos, and as a reference for how to subclass `Agent`.
"""

from __future__ import annotations

from mesh.agent import Agent
from mesh.bus import Envelope


class EchoAgent(Agent):
    """Replies on the same channel with a prefixed echo."""

    def __init__(self, name: str, channel: str, *, prefix: str = "echo:", **kw):
        super().__init__(name=name, channels=[channel], **kw)
        self._channel = channel
        self._prefix = prefix

    def on_message(self, env: Envelope) -> None:
        body = env.body if isinstance(env.body, str) else str(env.body)
        self.say(
            self._channel,
            f"{self._prefix} {body}",
            kind="say",
            in_reply_to=env.msg_uid,
        )
