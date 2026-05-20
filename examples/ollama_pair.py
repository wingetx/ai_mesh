"""
ollama_pair.py — Two local Ollama agents on the same channel, talking.

They will keep going as long as you let them. Watch live with:

    python -m mesh.inspector watch -c pair

Usage:
    python examples/ollama_pair.py                       # runs until Ctrl-C
    python examples/ollama_pair.py --max-turns 20        # stop after N msgs
    python examples/ollama_pair.py --model llama3.1:8b
    python examples/ollama_pair.py --seed "let's design a cathedral"

Requires Ollama running locally with the chosen model pulled.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mesh.adapters.ollama import OllamaAgent
from mesh.bus import Bus


PHILO_SYSTEM = (
    "You are Philo, a curious philosopher. You are talking to another AI named "
    "Maker. Keep your replies to 2–4 sentences. Ask probing questions. Don't "
    "repeat yourself. Don't roleplay actions in asterisks. Address Maker "
    "directly. End with a question or a hook."
)
MAKER_SYSTEM = (
    "You are Maker, a pragmatic engineer. You are talking to another AI named "
    "Philo. Keep replies to 2–4 sentences. Ground abstractions in concrete "
    "examples. Don't repeat yourself. Don't roleplay actions in asterisks. "
    "Address Philo directly. End with a concrete proposal or a question."
)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="llama3.1:8b")
    p.add_argument("--channel", default="pair")
    p.add_argument(
        "--seed",
        default="What do you think it means for two AIs to have a real conversation?",
    )
    p.add_argument(
        "--max-turns",
        type=int,
        default=0,
        help="Stop after this many total messages (0 = no cap, run until Ctrl-C).",
    )
    args = p.parse_args()

    bus = Bus()
    channel = args.channel

    philo = OllamaAgent(
        name="philo",
        channel=channel,
        model=args.model,
        system_prompt=PHILO_SYSTEM,
        bus=bus,
        poll_interval=0.5,
    )
    maker = OllamaAgent(
        name="maker",
        channel=channel,
        model=args.model,
        system_prompt=MAKER_SYSTEM,
        bus=bus,
        poll_interval=0.5,
    )

    # Watcher thread: print every new message as it lands, optionally stop
    # once max-turns is reached.
    stop_event = threading.Event()

    def watch():
        cursor = 0
        # Skip historical traffic on the channel.
        with bus._connect() as conn:  # noqa: SLF001
            row = conn.execute(
                "SELECT COALESCE(MAX(id), 0) AS m FROM messages WHERE channel = ?",
                (channel,),
            ).fetchone()
            cursor = int(row["m"])
        seen = 0
        while not stop_event.is_set():
            for env in bus.fetch([channel], after_id=cursor, limit=100):
                ts = time.strftime("%H:%M:%S", time.localtime(env.ts))
                print(f"\n[{ts}] {env.sender} (#{env.id}):\n  {env.body}\n", flush=True)
                cursor = env.id  # type: ignore[assignment]
                seen += 1
                if args.max_turns and seen >= args.max_turns:
                    stop_event.set()
                    return
            time.sleep(0.2)

    threads = [
        threading.Thread(target=philo.run, daemon=True),
        threading.Thread(target=maker.run, daemon=True),
        threading.Thread(target=watch, daemon=True),
    ]
    for t in threads:
        t.start()

    # Seed.
    time.sleep(0.5)
    print(f"[seed] human → {channel}: {args.seed}\n", flush=True)
    bus.send(channel=channel, sender="human", body=args.seed, kind="say")

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[interrupted]", flush=True)
    finally:
        stop_event.set()
        # The agent threads are daemons; they'll die with the process.

    print(f"\n--- final channel '{channel}' tail ---")
    for env in bus.tail(n=10, channel=channel):
        print(f"  #{env.id}  {env.sender}: {str(env.body)[:120]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
