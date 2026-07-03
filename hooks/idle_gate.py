#!/usr/bin/env python3
"""hooks/idle_gate.py — mechanical busy-presence enforcement for named
teammates (GATES v2, v1.4.0), the TeammateIdle-side counterpart of
hooks/stop_gate.py.

Fires when a named, backgrounded teammate — inside a REAL Claude Code "team"
(a `~/.claude/teams/session-*/config.json` structure; live-probed, P4: a
plain background Agent-tool spawn or a root `claude --bg` session never fires
this event at all, only genuine team formation does) — is about to go idle.
Blocks while its campaign has outstanding work, using the exact SAME check as
hooks/stop_gate.py (hooks/ledger.py's campaign_has_outstanding_work() — one
source of truth, not two competing definitions of "busy").

DELIVERY SCHEMA IS GENUINELY DIFFERENT FROM stop_gate.py, NOT SHARED CODE:
live-probed (P4) that TeammateIdle does not support the JSON
{"decision":"block",...} form Stop/SubagentStop use — it blocks via a plain
non-zero exit code (2) plus stderr text, delivered to the idling teammate
itself as a synthetic user turn labeled "TeammateIdle hook feedback:\\n
[<hook command>]: <stdout+stderr>". This is the ONE hook in this whole repo
that deliberately writes to stderr — everywhere else in this codebase, any
stderr output is treated as noise to eliminate (see hooks/stop_gate.py's own
docstring on why); here it is the load-bearing delivery channel, confirmed
live, not an oversight.

TeammateIdle's own hook payload carries `teammate_name`/`team_name` but
NOT `agent_id` (a genuinely different shape from every other hook this repo
wires — confirmed live, P4) — this gate doesn't need agent_id though: it asks
about the WHOLE campaign's outstanding-work state via `session_id`, exactly
the same question hooks/stop_gate.py asks, just triggered by a different
event and targeting whichever teammate is asking rather than the main
session.

REASON TEXT: same factual-state-not-command phrasing as hooks/stop_gate.py,
for the same reason (P2's live finding that imperative phrasing reads as
prompt-injection and gets refused even though the block itself still works).

Campaign resolution, the rest_ok escape hatch, and the fail-open contract are
all identical to hooks/stop_gate.py — see hooks/ledger.py's
campaign_has_outstanding_work() docstring for the exact rules. This hook
NEVER creates any directory or file.
"""
import json
import os
import sys

import ledger


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        return
    try:
        data = json.loads(raw)
    except Exception:
        return
    if not isinstance(data, dict):
        return

    project_dir = ledger.resolve_project_dir(data)
    if not project_dir:
        return

    home_session_id = ledger.resolve_home_session_id(project_dir, data.get("session_id"))
    if not home_session_id:
        return

    campaign_dir = os.path.join(project_dir, "delegator", home_session_id)
    outstanding, reason = ledger.campaign_has_outstanding_work(campaign_dir)
    if not outstanding:
        return

    sys.stderr.write(
        f"Busy-presence check: {reason}. If this is stale, set registry.json's "
        "top-level rest_ok:true once you've confirmed it yourself, or resolve "
        "the outstanding item.\n"
    )
    sys.stderr.flush()
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
