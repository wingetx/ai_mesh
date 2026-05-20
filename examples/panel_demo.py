"""
panel_demo.py — Live multi-agent panel with hot-reloading roster.

Reads the roster from a JSON file. While the panel is running you can edit
that file: new entries join the conversation, removed entries leave, and
prompt/model changes take effect on the next turn.

Run:
    python examples/panel_demo.py --roster examples/roster.json \
        --seed "What does it mean for a system like ours to be honest?"

Watch live in another terminal:
    python -m mesh.inspector watch -c panel

Add a participant on the fly: edit examples/roster.json and append e.g.

    {
      "name": "gardener",
      "model": "llama3.1:8b",
      "system_prompt": "You are Gardener, a quiet observer..."
    }

— save the file and they'll speak on the next turn.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mesh.bus import Bus
from mesh.panel import Panel


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--roster", default="examples/roster.json")
    p.add_argument("--channel", default="panel")
    p.add_argument(
        "--seed",
        default="What does it mean for a system like ours to be honest with each other?",
    )
    p.add_argument("--max-turns", type=int, default=0, help="0 = forever")
    p.add_argument("--turn-delay", type=float, default=0.0)
    args = p.parse_args()

    bus = Bus()
    stop = threading.Event()

    def print_event(evt: str, data: dict) -> None:
        print(f"\n[panel] {evt}: {data}\n", flush=True)

    panel = Panel(
        channel=args.channel,
        bus=bus,
        roster_path=Path(args.roster),
        turn_delay=args.turn_delay,
        on_event=print_event,
    )

    def watcher():
        with bus._connect() as conn:  # noqa: SLF001
            row = conn.execute(
                "SELECT COALESCE(MAX(id), 0) AS m FROM messages WHERE channel = ?",
                (args.channel,),
            ).fetchone()
            cursor = int(row["m"])
        while not stop.is_set():
            for env in bus.fetch([args.channel], after_id=cursor, limit=100):
                ts = time.strftime("%H:%M:%S", time.localtime(env.ts))
                body = env.body if isinstance(env.body, str) else str(env.body)
                print(f"\n[{ts}] {env.sender} (#{env.id}) [{env.kind}]:\n  {body}\n", flush=True)
                cursor = env.id  # type: ignore[assignment]
            time.sleep(0.2)

    threading.Thread(target=watcher, daemon=True).start()

    print(f"[seed] human → {args.channel}: {args.seed}\n", flush=True)
    try:
        panel.run(seed=args.seed, max_turns=args.max_turns, stop_event=stop)
    except KeyboardInterrupt:
        print("\n[interrupted]", flush=True)
    finally:
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
