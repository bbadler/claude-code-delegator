#!/usr/bin/env python3
"""hooks/ledger.py — portable (stdlib-only) replacement for ledger.sh + fold-registry.py.

Reads one Claude Code hook payload from stdin, flock-appends a compact JSONL row to
.delegator/events.jsonl in the workspace, then folds .delegator/registry.json in the
SAME process (one interpreter start does both jobs). No jq, no flock(1), no GNU
coreutils shell-outs -- works unmodified on macOS: stock Python 3 ships `fcntl`
(POSIX, present on macOS and Linux alike; this repo targets those two only), and
every filesystem op below is os/json/datetime stdlib, nothing shelled out.

FAIL-OPEN CONTRACT: this script must never block or fail the calling tool. Every
code path is wrapped so any exception is swallowed and the process exits 0.

Field names, truncation (400 chars), rotation size (~5MB), and the merge-aware
registry fold are ported unchanged in behavior from the shell/jq originals
(docs/roadmap-v2.md N1 probe, Claude Code 2.1.198, 2026-07-02 -- see
hooks/README.md for the observed-payload evidence those originals were built on).

One deliberate fix made while porting: the original fold-registry.py read the
existing registry.json BEFORE acquiring its write lock, then wrote after acquiring
it -- a read-outside-lock/write-inside-lock pattern that lets two concurrent folds
both read the same stale snapshot and the second writer silently discard the
first's merge (lost update). Here the read-merge-write happens under a single lock
acquisition, closing that race -- see the concurrent-double-append test in the N1
re-proof for a live check of this.
"""
import datetime
import fcntl
import json
import os
import sys
import time

MAX_FIELD = 400
MAX_BYTES = 5 * 1024 * 1024
LOCK_TIMEOUT_SEC = 2.0


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dig(d, *path):
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def trunc(s, maxlen=MAX_FIELD):
    if isinstance(s, str) and len(s) > maxlen:
        return s[:maxlen] + "…"
    return s


def first_content_text(data):
    content = dig(data, "tool_response", "content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            return first.get("text")
    return None


def build_row(data, ts):
    """Mirrors ledger.sh's jq filter field-for-field: same fallbacks, same
    null/empty/[] stripping (the `X // empty` object-construction gotcha the
    original hit doesn't exist here -- Python dict-comprehension filtering has no
    equivalent "zero outputs" trap)."""
    summary = (
        data.get("last_assistant_message")
        or first_content_text(data)
        or dig(data, "tool_input", "description")
        or ""
    )
    row = {
        "ts": ts,
        "event": data.get("hook_event_name") or "unknown",
        "session_id": data.get("session_id"),
        "transcript_path": data.get("transcript_path"),
        "agent_id": data.get("agent_id") or dig(data, "tool_response", "agentId"),
        "agent_type": (
            data.get("agent_type")
            or dig(data, "tool_response", "agentType")
            or dig(data, "tool_input", "subagent_type")
        ),
        "agent_name": dig(data, "tool_input", "name"),
        "tool": data.get("tool_name"),
        "summary": trunc(summary),
    }
    return {k: v for k, v in row.items() if v not in (None, "", [])}


def flock_ex(f, timeout=LOCK_TIMEOUT_SEC):
    """Blocking-with-timeout exclusive lock (fcntl has no native timeout arg):
    poll LOCK_NB until acquired or the deadline passes. Mirrors `flock -w 2`."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)


def flock_un(f):
    try:
        fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass


def append_event(ledger_dir, row):
    events_path = os.path.join(ledger_dir, "events.jsonl")
    lock_path = os.path.join(ledger_dir, ".ledger.lock")
    os.makedirs(ledger_dir, exist_ok=True)
    with open(lock_path, "a") as lockf:
        if not flock_ex(lockf):
            return  # fail-open: skip this event rather than block the tool call
        try:
            if os.path.isfile(events_path) and os.path.getsize(events_path) >= MAX_BYTES:
                bak_ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                os.replace(events_path, f"{events_path}.{bak_ts}.bak")
            with open(events_path, "a") as f:
                f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        finally:
            flock_un(lockf)


# ---- registry fold (ported from fold-registry.py, now in-process) ----

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


def _normalize_existing(existing):
    """The pre-existing registry.json can be in ANY of the shapes below -- this
    hook does not control what the delegator hand-writes, and agents/delegator.md's
    Registry section pins the PER-ENTRY field schema ({name, agent_id, session_id,
    cwd, purpose, status, ...}) but not the top-level container, so a hand-written
    file legitimately varies run to run. Confirmed live (2026-07-02): feeding a
    `{"version":1,"orchestrators":[...]}` file through the shape-naive version of
    this function silently CLOBBERED it -- `existing.get("agents", {})` returns the
    empty default on a dict that has no "agents" key (no exception, so the old
    fail-open contract alone did not catch it), discarding every judgment field.

    Returns (shape, entries_by_agent_id, passthrough, extra_keys):
      shape            "list" | "bare_list" | "dict" -- which convention to write back,
                       so a fold NEVER converts a file to a shape the delegator wasn't
                       already using.
      entries_by_agent_id  dict of existing entries that DO carry an agent_id (mergeable).
      passthrough      list of existing entries with NO agent_id, or malformed
                       (non-dict) items -- nothing to merge onto, round-tripped as-is
                       so "preserve every existing entry" holds even for those.
      extra_keys       any other top-level keys on a dict-shaped file (e.g.
                       "version"), preserved untouched.
    """
    def split(items):
        entries, passthrough = {}, []
        for e in items:
            if isinstance(e, dict) and e.get("agent_id"):
                entries[e["agent_id"]] = dict(e)
            else:
                passthrough.append(e)
        return entries, passthrough

    if isinstance(existing, dict) and isinstance(existing.get("orchestrators"), list):
        entries, passthrough = split(existing["orchestrators"])
        extra_keys = {k: v for k, v in existing.items() if k != "orchestrators"}
        return "list", entries, passthrough, extra_keys
    if isinstance(existing, list):
        entries, passthrough = split(existing)
        return "bare_list", entries, passthrough, {}
    if isinstance(existing, dict) and isinstance(existing.get("agents"), dict):
        extra_keys = {k: v for k, v in existing.items() if k != "agents"}
        return "dict", dict(existing["agents"]), [], extra_keys
    return "dict", {}, [], {}


def fold_registry(ledger_dir):
    """Merge-aware: only sets/refreshes the MECHANICAL fields derived from the
    ledger (status, agent_type, name, depth, description, last_event*, session_id)
    on each agent's entry by agent_id, never touching keys it doesn't produce --
    see agents/delegator.md's Registry section for the judgment fields this leaves
    alone, and hooks/README.md for the open question that split raises. Handles
    BOTH a dict-shaped registry.json (this script's own {"agents": {...}} format)
    and the delegator's hand-written {"version":N,"orchestrators":[...]} list shape
    (or a bare top-level list) via _normalize_existing -- see its docstring for the
    clobber bug this replaced."""
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

    lock_path = os.path.join(ledger_dir, ".registry.lock")
    tmp_path = registry_path + ".tmp"
    with open(lock_path, "a") as lockf:
        if not flock_ex(lockf):
            return  # fail-open: skip this fold rather than race the file unlocked
        try:
            # Read-merge-write all under the SAME lock acquisition (the fix noted
            # in the module docstring: reading outside the lock would let two
            # concurrent folds both merge onto the same stale snapshot).
            existing = {}
            if os.path.isfile(registry_path):
                try:
                    with open(registry_path) as f:
                        existing = json.load(f)
                except Exception:
                    existing = {}
            shape, merged_entries, passthrough, extra_keys = _normalize_existing(existing)
            for aid, derived in agents.items():
                merged_row = dict(merged_entries.get(aid, {}))
                merged_row.update(derived)
                merged_entries[aid] = merged_row

            # Write back in the SAME shape that was already on disk -- never
            # convert a hand-written list into this script's own dict shape (or
            # vice versa); a fresh/never-written registry defaults to the
            # original dict shape, matching pre-dual-shape behavior exactly.
            if shape == "list":
                out = dict(extra_keys)
                out.setdefault("version", 1)
                out["orchestrators"] = list(merged_entries.values()) + passthrough
                out["updated_at"] = now_iso()
            elif shape == "bare_list":
                out = list(merged_entries.values()) + passthrough
            else:
                out = dict(extra_keys)
                out["agents"] = merged_entries
                out["updated_at"] = now_iso()

            with open(tmp_path, "w") as f:
                json.dump(out, f, indent=2, sort_keys=True, ensure_ascii=False)
            os.replace(tmp_path, registry_path)
        finally:
            flock_un(lockf)


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

    ts = now_iso()
    row = build_row(data, ts)
    if not row:
        return

    workdir = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    ledger_dir = os.path.join(workdir, ".delegator")

    try:
        append_event(ledger_dir, row)
    except Exception:
        pass

    try:
        fold_registry(ledger_dir)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
