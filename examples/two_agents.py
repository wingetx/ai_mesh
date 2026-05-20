"""
two_agents.py — Two echo agents bouncing one message back and forth.

Run:
    python examples/two_agents.py

Then inspect:
    python -m mesh.inspector tail -c demo
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mesh.adapters.echo import EchoAgent
from mesh.bus import Bus


def main() -> int:
    bus = Bus()
    channel = "demo"

    # Two echo agents with different prefixes; each will reply to anything
    # the other says, so a single seed message produces a back-and-forth.
    alice = EchoAgent("alice", channel, prefix="alice heard:", bus=bus, poll_interval=0.1)
    bob = EchoAgent("bob", channel, prefix="bob heard:", bus=bus, poll_interval=0.1)

    # Run each in its own thread for 4 seconds.
    t1 = threading.Thread(target=alice.run, kwargs={"stop_after": 4.0}, daemon=True)
    t2 = threading.Thread(target=bob.run, kwargs={"stop_after": 4.0}, daemon=True)
    t1.start()
    t2.start()

    # Give them a moment to subscribe, then drop a seed message.
    time.sleep(0.3)
    bus.send(channel=channel, sender="human", body="hello, agents", kind="say")

    t1.join()
    t2.join()

    # Print the resulting traffic.
    print(f"\n--- channel '{channel}' traffic ---")
    for env in bus.tail(n=20, channel=channel):
        print(f"  #{env.id:>4}  {env.sender:>6} [{env.kind}]: {env.body}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
