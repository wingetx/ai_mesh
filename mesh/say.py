"""
say.py — Inject a message into a live channel from the outside.

Usage:
    python -m mesh.say --channel panel "Pause and summarize so far."
    python -m mesh.say --channel panel --to skeptic "Steelman the opposite view."
    python -m mesh.say --channel panel --kind note --as moderator "Wrap up in 2 turns."

Every injection lands on the same SQLite bus and is logged like any other
message. There is no separate channel.
"""

from __future__ import annotations

import argparse
import sys

from mesh.bus import Bus


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mesh.say")
    p.add_argument("--channel", required=True)
    p.add_argument("--to", default=None, help="address one specific agent")
    p.add_argument("--kind", default="say", help="say | note | ask | ...")
    p.add_argument("--as", dest="sender", default="human", help="sender name")
    p.add_argument("body", nargs="+", help="message body (joined with spaces)")
    args = p.parse_args(argv)

    bus = Bus()
    text = " ".join(args.body)
    env = bus.send(
        channel=args.channel,
        sender=args.sender,
        body=text,
        kind=args.kind,
        to=args.to,
    )
    target = f" → {env.to}" if env.to else ""
    print(f"posted #{env.id} on {env.channel} [{env.kind}] from {env.sender}{target}: {text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
