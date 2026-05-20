"""Bus unit tests — no LLM, no network."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from mesh.adapters.echo import EchoAgent
from mesh.bus import Bus


@pytest.fixture()
def bus(tmp_path: Path) -> Bus:
    return Bus(db_path=tmp_path / "bus.db")


def test_send_and_fetch(bus: Bus):
    e1 = bus.send("c1", "alice", "hi")
    e2 = bus.send("c1", "alice", "again")
    bus.send("c2", "bob", "elsewhere")

    rows = bus.fetch(["c1"])
    assert [r.id for r in rows] == [e1.id, e2.id]
    assert rows[0].body == "hi"
    assert rows[1].body == "again"
    assert all(r.channel == "c1" for r in rows)


def test_fetch_after_id(bus: Bus):
    e1 = bus.send("c", "a", "1")
    e2 = bus.send("c", "a", "2")
    rows = bus.fetch(["c"], after_id=e1.id)
    assert [r.id for r in rows] == [e2.id]


def test_body_can_be_structured(bus: Bus):
    payload = {"x": 1, "ys": [1, 2, 3], "nested": {"k": "v"}}
    sent = bus.send("c", "a", payload, kind="data")
    [back] = bus.fetch(["c"])
    assert back.body == payload
    assert back.kind == "data"
    assert back.msg_uid == sent.msg_uid


def test_channels_summary(bus: Bus):
    bus.send("c1", "a", "x")
    bus.send("c1", "a", "y")
    bus.send("c2", "b", "z")
    chans = dict(bus.channels())
    assert chans == {"c1": 2, "c2": 1}


def test_echo_agents_converse(tmp_path: Path):
    """Two EchoAgents on the same channel: a seed message produces several
    back-and-forth replies, all logged to the bus."""
    bus = Bus(db_path=tmp_path / "bus.db")
    channel = "demo"

    a = EchoAgent("alice", channel, prefix="A:", bus=bus, poll_interval=0.05)
    b = EchoAgent("bob", channel, prefix="B:", bus=bus, poll_interval=0.05)

    t1 = threading.Thread(target=a.run, kwargs={"stop_after": 1.5}, daemon=True)
    t2 = threading.Thread(target=b.run, kwargs={"stop_after": 1.5}, daemon=True)
    t1.start()
    t2.start()
    time.sleep(0.2)
    bus.send(channel, "human", "ping")
    t1.join()
    t2.join()

    msgs = bus.fetch([channel], after_id=0, limit=500)
    senders = [m.sender for m in msgs]
    assert "alice" in senders
    assert "bob" in senders
    # Each non-human message should reference an earlier one.
    for m in msgs:
        if m.sender != "human":
            assert m.in_reply_to is not None
