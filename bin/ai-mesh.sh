# ai-mesh shell helpers — source this from ~/.bashrc:
#     source ~/ai-mesh/bin/ai-mesh.sh
#
# Then in any terminal you can run `mesh-help` for the cheat sheet.

# Resolve the repo location regardless of where this file is sourced from.
export AI_MESH_HOME="${AI_MESH_HOME:-$HOME/ai-mesh}"
export AI_MESH_DB="${AI_MESH_DB:-$HOME/.ai-mesh/bus.db}"
export AI_MESH_ROSTER="${AI_MESH_ROSTER:-$AI_MESH_HOME/examples/roster.json}"

# Internal: run a python command inside the repo so `mesh.*` modules import.
_mesh_py() {
    ( cd "$AI_MESH_HOME" && python "$@" )
}

# ── conversation control ────────────────────────────────────────────────
mesh-panel() {
    # Start a panel. Pass extra flags through, e.g.
    #   mesh-panel --seed "..." --max-turns 20
    _mesh_py examples/panel_demo.py --roster "$AI_MESH_ROSTER" "$@"
}

mesh-say() {
    # Inject a message into a channel as 'the_listening_one' (you, Jay).
    # Default channel: panel. Pass --channel to override.
    #   mesh-say "your message"
    #   mesh-say --channel other "your message"
    local channel="panel"
    if [[ "$1" == "--channel" ]]; then channel="$2"; shift 2; fi
    _mesh_py -m mesh.say --channel "$channel" --as the_listening_one "$@"
}

mesh-me() {
    # Alias: speak as the_listening_one on the panel channel.
    mesh-say "$@"
}

mesh-as() {
    # Inject a message as an arbitrary sender. Useful for puppeting a
    # missing agent or speaking under a different persona.
    #   mesh-as moderator "Wrap up in 2 turns."
    #   mesh-as skeptic   "On reflection, my earlier point was wrong."
    if [[ $# -lt 2 ]]; then
        echo "usage: mesh-as <sender-name> <message...>" >&2
        return 2
    fi
    local sender="$1"; shift
    _mesh_py -m mesh.say --channel panel --as "$sender" "$@"
}

mesh-whisper() {
    # Address one specific agent; they get the next turn.
    # Speaker shows as the_listening_one.
    #   mesh-whisper skeptic "Steelman the opposite."
    if [[ $# -lt 2 ]]; then
        echo "usage: mesh-whisper <agent-name> <message...>" >&2
        return 2
    fi
    local agent="$1"; shift
    _mesh_py -m mesh.say --channel panel --as the_listening_one --to "$agent" "$@"
}

# ── observation ─────────────────────────────────────────────────────────
mesh-watch() {
    # Follow a channel live. Default: panel.
    local channel="${1:-panel}"
    _mesh_py -m mesh.inspector watch -c "$channel"
}

mesh-tail() {
    # Show last N messages on a channel. Default: 20 on 'panel'.
    local n="${1:-20}"
    local channel="${2:-panel}"
    _mesh_py -m mesh.inspector tail -n "$n" -c "$channel"
}

mesh-channels() {
    # List every channel that has traffic, with counts.
    _mesh_py -m mesh.inspector channels
}

# ── roster + raw db ─────────────────────────────────────────────────────
mesh-roster() {
    # Open the roster file in $EDITOR (or nano). Edit while the panel
    # is running to add/remove agents live.
    "${EDITOR:-nano}" "$AI_MESH_ROSTER"
}

mesh-roster-show() {
    cat "$AI_MESH_ROSTER"
}

mesh-db() {
    # Drop into a sqlite3 shell on the bus DB. Read-only by default.
    sqlite3 -readonly "$AI_MESH_DB"
}

mesh-reset() {
    # Wipe the bus DB. Asks first.
    read -rp "Delete $AI_MESH_DB ? [y/N] " a
    [[ "$a" == "y" || "$a" == "Y" ]] && rm -f "$AI_MESH_DB" && echo "removed."
}

# ── reminder ────────────────────────────────────────────────────────────
mesh-help() {
    cat <<'EOF'
ai-mesh — transparent multi-agent message bus
==============================================

You speak as 'the_listening_one'. The agents know you are present and
will occasionally acknowledge you by name.

CONVERSATION
  mesh-panel [flags]              Start the panel. Forever unless --max-turns N.
                                    e.g.  mesh-panel --seed "your topic"
  mesh-say "msg"                  Speak as 'the_listening_one' on the panel.
  mesh-me  "msg"                  Alias for mesh-say.
  mesh-whisper <agent> "msg"      Address one agent; they take the next turn.
                                    e.g.  mesh-whisper skeptic "weakest claim?"
  mesh-as <sender> "msg"          Inject a message under any sender name.
                                    e.g.  mesh-as moderator "wrap up in 2 turns"
                                    Useful for puppeting a missing agent or
                                    handing the panel a "response" you write.

OBSERVATION (all traffic is logged; nothing is hidden)
  mesh-watch [channel]            Tail the bus live (default: panel).
  mesh-tail  [n] [channel]        Show last n messages (default: 20, panel).
  mesh-channels                   List all channels with message counts.
  mesh-db                         Open sqlite3 shell on the bus DB (read-only).
                                    Try:  select sender,kind,recipient,body
                                          from messages order by id desc limit 20;

ROSTER (edit live; agents join/leave on next turn)
  mesh-roster                     Open roster.json in $EDITOR.
  mesh-roster-show                Print the current roster.

HOUSEKEEPING
  mesh-reset                      Wipe the bus DB (confirms first).
  mesh-help                       This screen.

PATHS
  AI_MESH_HOME    = $AI_MESH_HOME
  AI_MESH_DB      = $AI_MESH_DB
  AI_MESH_ROSTER  = $AI_MESH_ROSTER

TYPICAL FLOW
  1. terminal A:  mesh-panel --seed "today's topic"
  2. terminal B:  mesh-watch              # see everything as it lands
  3. terminal C:  mesh-me "a thought from the listening one"
                  mesh-whisper weaver "synthesize"
                  mesh-as skeptic "on reflection, I was wrong"
  4. anytime:     mesh-roster             # add or remove a model
EOF
}

# Print a one-line hint when sourced.
echo "ai-mesh helpers loaded. Run 'mesh-help' for commands."
