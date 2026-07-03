#!/usr/bin/env python3
"""hooks/stop_gate.py — mechanical busy-presence enforcement (GATES v2, v1.4.0).

Fires on the Stop event -- the calling session's OWN turn trying to end.
Replaces charter-discipline polling (the delegator "choosing" to stay present
per agents/delegator.md's Forward pressure section) with a mechanical gate
that doesn't depend on model compliance at all: while its campaign has real
outstanding work, this hook returns {"decision": "block", "reason": "..."},
which live-probed CONFIRMS force-continues the turn -- the process does not
exit, and the reason text is delivered to the model as a synthetic user turn
("Stop hook feedback:\\n<reason>"), same mechanism P1's probe verified.

The outstanding-work check itself (campaign registry + events, the rest_ok
escape hatch) is shared with hooks/idle_gate.py via
hooks/ledger.py's campaign_has_outstanding_work() -- see that function's
docstring for the exact rules. This script is a thin wrapper: resolve the
campaign, ask the shared function, format the block response if warranted.

REASON TEXT IS PHRASED AS FACTUAL STATE, NEVER AS A COMMAND: live-probed
(P2, SubagentStop) that when injected hook feedback reads as a bare imperative
("you MUST do X"), the model recognizes it as looking like an untrusted
prompt-injection attempt and explicitly refuses to comply with the specific
instruction, even though the block itself still works (the turn still
continues). Phrasing the reason as "here's what the registry shows" rather
than "do X" is a deliberate choice made from that finding, not a guess.

Campaign resolution is identical to hooks/ledger.py's own (transcript_path ->
project dir -> that project's delegator/sessions.json -> home_session_id;
unregistered session or no campaign ever run here -> silent no-op, never
blocks). This hook NEVER creates any directory or file -- purely read-only
except for the block decision it prints.

STDOUT: only ever the single JSON block-decision object when genuinely
blocking; completely empty otherwise. STDERR: always empty -- live-probed
that even an unrelated stray warning line on stderr surfaces to the user as
a "Stop hook error" UI notification, even when the block itself works
correctly, so this script must never write to stderr under any condition.

FAIL-OPEN CONTRACT: matches every other hook in this repo -- any exception
anywhere is swallowed, this process always exits 0 (Stop-hook exit code is
irrelevant to blocking; the decision is carried in the JSON payload, not the
exit code -- confirmed live, unlike TeammateIdle's plain exit-2 convention in
hooks/idle_gate.py, a genuinely different delivery schema for a different
event).
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

    # LOOP GUARD: stop_hook_active is true when this Stop was itself triggered by
    # a prior stop-hook continuation. Re-blocking then would loop the turn until a
    # valve trips; the documented contract is "block once, not forever" -- so a
    # continuation chain that has already been nudged is allowed to conclude, and
    # only a genuinely fresh stop attempt (flag false) re-engages busy-presence.
    if data.get("stop_hook_active"):
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

    print(json.dumps({
        "decision": "block",
        "reason": (
            f"Busy-presence check: {reason}. If this is stale, set "
            "registry.json's top-level rest_ok:true once you've confirmed "
            "it yourself, or resolve the outstanding item."
        ),
    }))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
