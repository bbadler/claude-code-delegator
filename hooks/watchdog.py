#!/usr/bin/env python3
"""hooks/watchdog.py — portable (stdlib-only) dead-man watchdog (N2), replacing
watchdog.sh. Reads .delegator/events.jsonl (written by hooks/ledger.py) and prints
one line per anomaly:
    WATCHDOG: <type> <agent> <evidence>
No Monitor integration yet -- arm this yourself (see hooks/README.md "Dead-man
watchdog" section). Silent output = healthy. No jq -- pure stdlib json/datetime,
works unmodified on macOS.

usage: watchdog.py [workspace-dir] [stale-minutes]
"""
import datetime
import json
import os
import sys


def load_rows(events_path):
    rows = []
    if not os.path.isfile(events_path):
        return rows
    with open(events_path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def parse_ts(ts):
    # Matches jq's fromdateiso8601 for our own "%Y-%m-%dT%H:%M:%SZ" ledger format.
    return datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=datetime.timezone.utc
    )


def check_stale_agents(rows, now, stale_sec):
    """STALE_AGENT: an agent's latest ledger row is still SubagentStart (it never
    reached SubagentStop/PostToolUse) and that row is older than stale_sec."""
    latest = {}
    for r in rows:
        aid = r.get("agent_id")
        if not aid:
            continue
        if aid not in latest or r.get("ts", "") > latest[aid].get("ts", ""):
            latest[aid] = r

    out = []
    for aid, r in latest.items():
        if r.get("event") != "SubagentStart":
            continue
        try:
            ts_dt = parse_ts(r["ts"])
        except Exception:
            continue
        idle_sec = (now - ts_dt).total_seconds()
        if idle_sec > stale_sec:
            idle_min = int(idle_sec // 60)
            out.append(
                f"WATCHDOG: STALE_AGENT {aid} last_event={r.get('event')}@{r.get('ts')} idle_min={idle_min}"
            )
    return out


def check_unanswered_gates(rows):
    """UNANSWERED_GATE: a row whose summary carries a gate marker, with no later
    ledger row at all for that same session_id (the session went quiet right
    after)."""
    out = []
    for g in rows:
        summary = g.get("summary")
        if not summary:
            continue
        low = summary.lower()
        if "gate" not in low and "sendmessage me" not in low:
            continue
        sid = g.get("session_id")
        gts = g.get("ts", "")
        later = any(r.get("session_id") == sid and r.get("ts", "") > gts for r in rows)
        if later:
            continue
        who = g.get("agent_id") or g.get("session_id") or "unknown"
        out.append(f"WATCHDOG: UNANSWERED_GATE {who} summary={summary}")
    return out


def main():
    workdir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    stale_min = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    events_path = os.path.join(workdir, ".delegator", "events.jsonl")
    rows = load_rows(events_path)
    if not rows:
        return
    now = datetime.datetime.now(datetime.timezone.utc)
    for line in check_stale_agents(rows, now, stale_min * 60):
        print(line)
    for line in check_unanswered_gates(rows):
        print(line)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
