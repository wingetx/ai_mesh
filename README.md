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

## Install

```bash
git clone https://github.com/wingetx/ai_mesh.git
cd ai_mesh

# Optional but recommended: isolated env.
python -m venv .venv
source .venv/bin/activate

# No third-party deps required for the core (stdlib only). Tests use pytest.
pip install pytest
```

To use the local Ollama adapter, also have Ollama running:

```bash
# install once (Arch: pacman -S ollama; or curl -fsSL https://ollama.com/install.sh | sh)
ollama serve &
ollama pull llama3.1:8b
```

## Quick start

```bash
cd ~/ai_mesh
source .venv/bin/activate     # if you made one

# Smoke test (no LLM needed):
python examples/two_agents.py

# 4-agent panel (needs Ollama + the models listed in examples/roster.json):
python examples/panel_demo.py --seed "What does honesty mean for a system like ours?"

# In another terminal, watch live or inject:
python -m mesh.inspector watch -c panel
python -m mesh.say --channel panel --as the_listening_one "Be honest, not performative."
python -m mesh.say --channel panel --as the_listening_one --to skeptic "Weakest claim so far?"
```

### Shell helpers (optional)

```bash
echo 'source ~/ai_mesh/bin/ai-mesh.sh' >> ~/.bashrc
source ~/.bashrc
mesh-help
```

That gives you `mesh-panel`, `mesh-watch`, `mesh-me`, `mesh-whisper`, `mesh-as`,
`mesh-roster`, `mesh-db`, etc.

## Design

- **Bus** = local SQLite file (`~/.ai-mesh/bus.db` by default).
  Producers `INSERT`, consumers poll for new rows on their channels.
  No network sockets, no daemons. Everything is a file you can `sqlite3`.
- **Agent** = anything with a `name`, a list of channels it subscribes to,
  and a callable `on_message(envelope)` that may `bus.send(...)` in response.
- **Inspector** = read-only SQL queries against the bus DB.

If you want network reach, mount the DB on shared storage or run a thin
HTTP shim around `bus.send / bus.fetch`. The core stays local-first.
