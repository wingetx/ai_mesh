"""
ollama.py — Adapter that wires a local Ollama model to the bus.

Each incoming message becomes a chat completion request to Ollama; the
model's reply is posted back to the same channel.

Requirements:
    - Ollama running at OLLAMA_URL (default http://127.0.0.1:11434)
    - The chosen model pulled (`ollama pull llama3.2:3b` etc.)

This adapter has no Anthropic/OpenAI dependency. Add sibling adapters for
those if/when you want to bridge them onto the same bus.
"""

from __future__ import annotations

import json
import os
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from mesh.agent import Agent
from mesh.bus import Envelope

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")


class OllamaAgent(Agent):
    """An agent that calls an Ollama model for each message it sees."""

    def __init__(
        self,
        name: str,
        channel: str,
        model: str,
        system_prompt: Optional[str] = None,
        *,
        url: str = OLLAMA_URL,
        history_limit: int = 8,
        **kw,
    ):
        super().__init__(name=name, channels=[channel], **kw)
        self._channel = channel
        self._model = model
        self._system = system_prompt
        self._url = url.rstrip("/")
        self._history_limit = history_limit
        self._history: list[dict] = []

    def on_message(self, env: Envelope) -> None:
        user_text = env.body if isinstance(env.body, str) else json.dumps(env.body, default=str)

        msgs: list[dict] = []
        if self._system:
            msgs.append({"role": "system", "content": self._system})
        msgs.extend(self._history[-self._history_limit :])
        msgs.append({"role": "user", "content": f"{env.sender}: {user_text}"})

        try:
            reply = self._chat(msgs)
        except Exception as exc:
            self.say(
                self._channel,
                f"[ollama error: {exc!s}]",
                kind="error",
                in_reply_to=env.msg_uid,
            )
            return

        self._history.append({"role": "user", "content": f"{env.sender}: {user_text}"})
        self._history.append({"role": "assistant", "content": reply})
        self.say(self._channel, reply, kind="say", in_reply_to=env.msg_uid)

    # ── HTTP ────────────────────────────────────────────────────────────
    def _chat(self, messages: list[dict]) -> str:
        payload = json.dumps(
            {"model": self._model, "messages": messages, "stream": False},
            ensure_ascii=False,
        ).encode("utf-8")
        req = Request(
            f"{self._url}/api/chat",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except URLError as e:
            raise RuntimeError(f"could not reach Ollama at {self._url}: {e}") from e
        msg = (data.get("message") or {}).get("content") or ""
        return msg.strip()
