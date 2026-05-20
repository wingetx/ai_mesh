# ai-mesh

A small, **transparent** multi-agent message bus for LLM-backed agents.

The point: let multiple AI agents (local Ollama, cloud APIs, scripted bots)
exchange messages on named channels, with **every message persisted to
SQLite** so a human can inspect the entire traffic history at any time.

This is the legitimate, auditable version of "AIs talking to each other."
Nothing happens out of view — `mesh inspect` shows you the wire.

## Layout

```
mesh/
  bus.py        — SQLite-backed pub/sub bus
  agent.py      — Agent base class (subscribe, send, react)
  inspector.py  — CLI to view traffic
  adapters/
    ollama.py   — Local Ollama-backed agent
    echo.py     — Trivial echo agent (no LLM)
examples/
  two_agents.py — Two echo agents on a channel
tests/
  test_bus.py
```

## Quick start

```bash
python -m mesh.inspector channels       # show channels with traffic
python -m mesh.inspector tail            # tail recent messages
python examples/two_agents.py            # run a tiny demo
```

## Design

- **Bus** = local SQLite file (`~/.ai-mesh/bus.db` by default).
  Producers `INSERT`, consumers poll for new rows on their channels.
  No network sockets, no daemons. Everything is a file you can `sqlite3`.
- **Agent** = anything with a `name`, a list of channels it subscribes to,
  and a callable `on_message(envelope)` that may `bus.send(...)` in response.
- **Inspector** = read-only SQL queries against the bus DB.

If you want network reach, mount the DB on shared storage or run a thin
HTTP shim around `bus.send / bus.fetch`. The core stays local-first.
