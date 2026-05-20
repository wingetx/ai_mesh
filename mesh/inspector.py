"""
inspector.py — CLI to view bus traffic.

Usage:
    python -m mesh.inspector channels
    python -m mesh.inspector tail [-n 20] [-c CHANNEL]
    python -m mesh.inspector watch [-c CHANNEL]
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime

from mesh.bus import Bus


def _fmt(env) -> str:
    ts = datetime.fromtimestamp(env.ts).strftime("%H:%M:%S")
    body = env.body
    if isinstance(body, str):
        body_text = body
    else:
        import json

        body_text = json.dumps(body, ensure_ascii=False, default=str)
    if len(body_text) > 200:
        body_text = body_text[:197] + "..."
    reply = f" ↪ {env.in_reply_to}" if env.in_reply_to else ""
    return f"#{env.id:>5}  {ts}  {env.channel:>14}  {env.sender:>10}  [{env.kind}]{reply}  {body_text}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mesh.inspector")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("channels", help="List channels with traffic counts")

    pt = sub.add_parser("tail", help="Show the most recent messages")
    pt.add_argument("-n", type=int, default=20)
    pt.add_argument("-c", "--channel", default=None)

    pw = sub.add_parser("watch", help="Follow the bus live")
    pw.add_argument("-c", "--channel", default=None)
    pw.add_argument("--interval", type=float, default=0.5)

    args = p.parse_args(argv)
    bus = Bus()

    if args.cmd == "channels":
        rows = bus.channels()
        if not rows:
            print("(no traffic yet)")
            return 0
        for ch, n in rows:
            print(f"  {n:>6}  {ch}")
        return 0

    if args.cmd == "tail":
        for env in bus.tail(n=args.n, channel=args.channel):
            print(_fmt(env))
        return 0

    if args.cmd == "watch":
        channels = [args.channel] if args.channel else [c for c, _ in bus.channels()]
        if not channels:
            print("(no channels yet — waiting…)", file=sys.stderr)
        cursor = 0
        try:
            while True:
                # Refresh channel list each tick so new channels show up.
                channels = [args.channel] if args.channel else [c for c, _ in bus.channels()] or []
                if channels:
                    for env in bus.fetch(channels, after_id=cursor, limit=500):
                        print(_fmt(env))
                        cursor = env.id  # type: ignore[assignment]
                time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
