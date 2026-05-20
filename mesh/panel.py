"""
panel.py — Turn-based multi-agent orchestrator.

The bus already supports any number of agents publishing freely. But if N
agents all reply to every message you get N-1 replies per turn and the
conversation explodes quadratically. `Panel` solves that by taking explicit
turns: it picks the next speaker, hands them the conversation, posts their
reply to the bus, advances.

Key feature: the roster can be reloaded from disk between turns. Edit the
roster file while the panel is running and new agents join, removed ones
leave. No restart required. Every change is visible in the bus log.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from mesh.adapters.ollama import OllamaAgent
from mesh.bus import Bus, Envelope

log = logging.getLogger(__name__)


@dataclass
class Seat:
    """One participant in the panel."""

    name: str
    model: str
    system_prompt: str

    def make_agent(self, channel: str, bus: Bus) -> OllamaAgent:
        return OllamaAgent(
            name=self.name,
            channel=channel,
            model=self.model,
            system_prompt=self.system_prompt,
            bus=bus,
            poll_interval=1.0,  # panel calls them directly; loop unused
        )


class Panel:
    """Round-robin orchestrator for N agents on a single channel.

    Agents are kept in a roster (list of Seat). The roster can be backed by
    a JSON file that is re-read each turn — that's how live join/leave
    works.
    """

    def __init__(
        self,
        channel: str,
        bus: Bus,
        roster_path: Optional[Path] = None,
        seats: Optional[list[Seat]] = None,
        turn_delay: float = 0.0,
        on_event: Optional[Callable[[str, dict], None]] = None,
    ):
        self.channel = channel
        self.bus = bus
        self.roster_path = Path(roster_path) if roster_path else None
        self.turn_delay = turn_delay
        self.on_event = on_event or (lambda evt, data: None)
        self._agents: dict[str, OllamaAgent] = {}
        self._order: list[str] = []
        self._next_idx = 0
        self._roster_mtime: float = 0.0
        if seats:
            for s in seats:
                self._add_seat(s)
        if self.roster_path:
            self._reload_roster(initial=True)

    # ── roster management ──────────────────────────────────────────────
    def _add_seat(self, seat: Seat) -> None:
        if seat.name in self._agents:
            return
        self._agents[seat.name] = seat.make_agent(self.channel, self.bus)
        self._order.append(seat.name)
        self.bus.send(
            self.channel,
            sender="panel",
            kind="join",
            body={"name": seat.name, "model": seat.model},
        )
        self.on_event("join", {"name": seat.name, "model": seat.model})

    def _remove_seat(self, name: str) -> None:
        if name not in self._agents:
            return
        del self._agents[name]
        self._order = [n for n in self._order if n != name]
        if self._next_idx >= len(self._order) and self._order:
            self._next_idx %= len(self._order)
        self.bus.send(
            self.channel,
            sender="panel",
            kind="leave",
            body={"name": name},
        )
        self.on_event("leave", {"name": name})

    def _reload_roster(self, initial: bool = False) -> None:
        if not self.roster_path or not self.roster_path.exists():
            return
        try:
            mtime = self.roster_path.stat().st_mtime
            if not initial and mtime == self._roster_mtime:
                return
            data = json.loads(self.roster_path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            log.warning("roster reload failed: %s", e)
            return
        self._roster_mtime = mtime
        wanted: dict[str, Seat] = {}
        for entry in data:
            try:
                seat = Seat(
                    name=entry["name"],
                    model=entry["model"],
                    system_prompt=entry.get("system_prompt", ""),
                )
            except KeyError as e:
                log.warning("roster entry missing field %s: %r", e, entry)
                continue
            wanted[seat.name] = seat
        # Remove anyone no longer present.
        for name in list(self._agents.keys()):
            if name not in wanted:
                self._remove_seat(name)
        # Add anyone new (preserve file order for new arrivals).
        for seat in wanted.values():
            if seat.name not in self._agents:
                self._add_seat(seat)
            else:
                # Update prompt/model in place without disturbing turn order.
                existing = self._agents[seat.name]
                if existing._model != seat.model or existing._system != seat.system_prompt:
                    self._agents[seat.name] = seat.make_agent(self.channel, self.bus)

    # ── turn execution ─────────────────────────────────────────────────
    def _last_message(self) -> Optional[Envelope]:
        tail = self.bus.tail(n=1, channel=self.channel)
        return tail[-1] if tail else None

    def _pending_whisper(self) -> tuple[Optional[str], Optional[Envelope]]:
        """Return (agent_name, envelope) for an unanswered direct address.

        Scans the recent tail for the newest message whose `to` field names
        a current panelist who has not yet spoken since being addressed.
        """
        recent = self.bus.tail(n=20, channel=self.channel)
        # Walk newest-first.
        for env in reversed(recent):
            if not env.to or env.to not in self._agents:
                continue
            target = env.to
            # Has `target` spoken AFTER this message?
            answered = any(
                later.sender == target and later.id is not None
                and env.id is not None and later.id > env.id
                for later in recent
            )
            if not answered:
                return target, env
        return None, None

    def _pick_next_speaker(self) -> tuple[Optional[str], Optional[Envelope]]:
        """Return (speaker, message_to_hand_them).

        If a whisper is pending, the addressee speaks next and is given the
        whisper itself. Otherwise round-robin, given the most recent message.
        """
        if not self._order:
            return None, None
        whispered, whisper_env = self._pending_whisper()
        if whispered is not None:
            try:
                idx = self._order.index(whispered)
                self._next_idx = (idx + 1) % len(self._order)
            except ValueError:
                pass
            return whispered, whisper_env
        last = self._last_message()
        for _ in range(len(self._order)):
            name = self._order[self._next_idx % len(self._order)]
            self._next_idx = (self._next_idx + 1) % len(self._order)
            if last is None or name != last.sender:
                return name, last
        return None, None

    def step(self) -> Optional[Envelope]:
        """Run one turn: reload roster, pick next speaker, post their reply."""
        self._reload_roster()
        speaker, message = self._pick_next_speaker()
        if speaker is None or message is None:
            return None
        agent = self._agents[speaker]
        try:
            agent.on_message(message)
        except Exception:
            log.exception("agent %s failed on turn", speaker)
            self.bus.send(
                self.channel,
                sender="panel",
                kind="error",
                body=f"{speaker} failed this turn (logged)",
            )
        return self._last_message()

    def run(
        self,
        seed: Optional[str] = None,
        seed_from: str = "human",
        max_turns: int = 0,
        stop_event=None,
    ) -> None:
        """Run forever (or until max_turns / stop_event)."""
        if seed:
            self.bus.send(self.channel, sender=seed_from, kind="say", body=seed)
        turns = 0
        while True:
            if stop_event is not None and stop_event.is_set():
                return
            if max_turns and turns >= max_turns:
                return
            # If the roster is empty, idle until someone joins.
            self._reload_roster()
            if not self._order:
                time.sleep(0.5)
                continue
            self.step()
            turns += 1
            if self.turn_delay:
                time.sleep(self.turn_delay)
