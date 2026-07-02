#!/usr/bin/env python3
"""hooks/fold-registry.py — re-fold .delegator/events.jsonl into .delegator/registry.json.

Called by hooks/ledger.sh after every ledger append. Best-effort and MERGE-aware:
registry.json may already carry delegator-hand-maintained judgment fields (purpose,
handoff_file, staleness_flags, cwd -- see agents/delegator.md's Registry section,
which predates this script and names the delegator "the ONLY writer" of this path).
This fold only sets/refreshes the MECHANICAL fields it derives from the ledger
(status, agent_type, name, depth, description, last_event*, session_id) on each
agent's entry by agent_id, and never touches keys it doesn't produce -- so a
concurrent delegator write and this hook-driven fold are additive, not destructive.
This is a pragmatic compromise, not a full concurrency fix -- see hooks/README.md
for the open question this raises for agents/delegator.md's single-writer charter.

Never raises out of main(): a fold failure must not surface as a hook failure.
"""
import datetime
import json
import os
import sys


def read_sidecar(transcript_path, agent_id):
    """Best-effort read of the harness's own agent-<id>.meta.json sidecar, which
    sits next to the per-agent transcript at <session-dir>/subagents/agent-<id>.meta.json
    (session-dir = the session's own transcript_path with .jsonl stripped -- verified
    live: docs/roadmap-v2.md N1 probe, 2026-07-02, on Claude Code 2.1.198)."""
    if not transcript_path or not transcript_path.endswith(".jsonl"):
        return {}
    session_dir = transcript_path[: -len(".jsonl")]
    meta_path = os.path.join(session_dir, "subagents", f"agent-{agent_id}.meta.json")
    try:
        with open(meta_path) as f:
            return json.load(f)
    except Exception:
        return {}


def fold(ledger_dir):
    events_path = os.path.join(ledger_dir, "events.jsonl")
    registry_path = os.path.join(ledger_dir, "registry.json")
    if not os.path.isfile(events_path):
        return

    agents = {}
    with open(events_path, "r", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            aid = row.get("agent_id")
            if not aid:
                continue
            a = agents.setdefault(aid, {"agent_id": aid, "first_seen": row.get("ts")})
            a["last_event"] = row.get("ts")
            a["last_event_type"] = row.get("event")
            if row.get("session_id"):
                a["session_id"] = row["session_id"]
            if row.get("transcript_path"):
                a["_transcript_path"] = row["transcript_path"]  # session-level; sidecar lookup only
            if row.get("agent_type"):
                a["agent_type"] = row["agent_type"]
            if row.get("agent_name"):
                a["name"] = row["agent_name"]
            if row.get("summary"):
                a["last_summary"] = row["summary"]
            evt = row.get("event")
            if evt == "SubagentStart":
                a["status"] = "active"
            elif evt == "SubagentStop" or (evt == "PostToolUse" and row.get("tool") == "Agent"):
                a["status"] = "stopped"

    # Enrich from the harness sidecar (authoritative name/type/depth), then drop
    # the internal-only transcript-path helper key.
    for aid, a in agents.items():
        sidecar = read_sidecar(a.pop("_transcript_path", None), aid)
        if sidecar.get("name"):
            a["name"] = sidecar["name"]
        if sidecar.get("agentType"):
            a["agent_type"] = sidecar["agentType"]
        if sidecar.get("description"):
            a["description"] = sidecar["description"]
        if "spawnDepth" in sidecar:
            a["depth"] = sidecar["spawnDepth"]
        a.setdefault("status", "unknown")

    # Merge into any existing registry.json rather than overwriting it outright --
    # preserves delegator-hand-written judgment fields this fold never produces.
    existing = {}
    if os.path.isfile(registry_path):
        try:
            with open(registry_path) as f:
                existing = json.load(f)
        except Exception:
            existing = {}
    merged_agents = existing.get("agents", {}) if isinstance(existing, dict) else {}
    for aid, derived in agents.items():
        row = dict(merged_agents.get(aid, {}))
        row.update(derived)
        merged_agents[aid] = row

    out = {
        "updated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agents": merged_agents,
    }

    lock_path = os.path.join(ledger_dir, ".registry.lock")
    tmp_path = registry_path + ".tmp"
    try:
        import fcntl
        with open(lock_path, "w") as lockf:
            fcntl.flock(lockf, fcntl.LOCK_EX)
            with open(tmp_path, "w") as f:
                json.dump(out, f, indent=2, sort_keys=True)
            os.replace(tmp_path, registry_path)
    except Exception:
        try:
            with open(tmp_path, "w") as f:
                json.dump(out, f, indent=2, sort_keys=True)
            os.replace(tmp_path, registry_path)
        except Exception:
            pass


def main():
    if len(sys.argv) < 2:
        return
    try:
        fold(sys.argv[1])
    except Exception:
        pass


if __name__ == "__main__":
    main()
