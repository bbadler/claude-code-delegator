#!/usr/bin/env python3
"""hooks/ledger.py — portable (stdlib-only) replacement for ledger.sh + fold-registry.py.

Reads one Claude Code hook payload from stdin and, IF (and only if) that event
belongs to a registered delegator campaign, flock-appends a compact JSONL row to
that campaign's events.jsonl and folds its registry.json in the SAME process (one
interpreter start does both jobs). No jq, no flock(1), no GNU coreutils shell-outs
-- works unmodified on macOS: stock Python 3 ships `fcntl` (POSIX, present on macOS
and Linux alike; this repo targets those two only), and every filesystem op below
is os/json/datetime/re stdlib, nothing shelled out.

STORAGE (v1.2.0, per-session -- BREAKING change from v1.1.x's flat .delegator/ in
the workspace, see CHANGELOG): everything lives OUTSIDE the workspace tree, under
Claude Code's own per-project storage --

    ~/.claude/projects/<workspace-slug>/delegator/
      |-- sessions.json                 {session_id: home_session_id} routing map,
      |                                 written ONLY by delegators, never by this hook
      +-- <home-session-id>/            one dir per delegator campaign, named by the
          |-- registry.json             session id that started it (same idea as
          +-- events.jsonl               Claude Code's own <session-id>.jsonl transcripts
                                          -- persists across resume/crash, same lifetime)

Routing (resolve_project_dir + resolve_home_session_id, see below): an event is
logged only if (a) the project dir resolves, (b) it has a delegator/ subdirectory
(i.e. a campaign has run there at least once), and (c) the event's own session_id
is a registered entry in that project's sessions.json, mapping to some home
session id. Any other event -- an ordinary chat, an unrecognized session, a project
that has never run a campaign -- hits none of these and the hook returns having
written and created NOTHING. This hook NEVER calls os.makedirs/os.mkdir anywhere,
under any condition, including for a registered campaign's own <home-session-id>/
subdirectory on its first event -- directory creation is entirely the delegator's
own responsibility (its charter creates sessions.json's entry AND its own
storage directory eagerly at campaign start); if a write ever races ahead of that,
the fail-open contract below just drops that one event rather than create anything
here. This is a deliberate, repo-owner-specified invariant, not an oversight.

STDOUT: this script never prints anything, on any path, success or fail-open --
confirmed by inspection (no print() calls exist anywhere below) and by a live
probe capturing real session output around it (CHANGELOG v1.2.0). This matters
because hook auto-registration (hooks/hooks.json) means this script now runs on
every tool call in every project once the plugin is installed; any stdout it
produced would be a standing, silent token cost injected into every session's
context. Debug via stderr only, never stdout, if you ever add diagnostics here.

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
import re
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


def normalize_existing(existing):
    """The pre-existing registry.json can be in ANY of the shapes below -- this
    hook does not control what the delegator hand-writes, and agents/delegator.md's
    Registry section pins the PER-ENTRY field schema ({name, agent_id, session_id,
    cwd, purpose, status, ...}) but not the top-level container, so a hand-written
    file legitimately varies run to run. Confirmed live (2026-07-02): feeding a
    `{"version":1,"orchestrators":[...]}` file through the shape-naive version of
    this function silently CLOBBERED it -- `existing.get("agents", {})` returns the
    empty default on a dict that has no "agents" key (no exception, so the old
    fail-open contract alone did not catch it), discarding every judgment field.
    Confirmed live again (2026-07-03, cold-verifier finding during the v1.2.0
    storage rework): a REAL post-campaign registry landed in a 4th shape this
    function didn't recognize yet, `{"agents": [...]}` -- a LIST under "agents",
    not this script's own dict-under-"agents" -- which fell all the way through
    to the empty-default fallback the same way, silently starting the next fold
    from nothing. Fixed below by giving it its own recognized shape rather than
    letting it alias either "dict" or "bare_list".

    `{"version":1,"agents":{<agent_id>: {...}}}` (the "dict" shape, and also the
    fallback for a fresh/never-written registry) is the CANONICAL shape the
    delegator charter is being standardized on -- the other three are recognized
    purely for backward-compatible tolerance with hand-written variations this
    hook doesn't control, not because any of them is preferred.

    Returns (shape, entries_by_agent_id, passthrough, extra_keys), OR **None**.
      shape            "list" | "bare_list" | "dict" | "agents_list" -- which
                       convention to write back, so a fold NEVER converts a file
                       to a shape the delegator wasn't already using.
      entries_by_agent_id  dict of existing entries that DO carry an agent_id (mergeable).
      passthrough      list of existing entries with NO agent_id, or malformed
                       (non-dict) items -- nothing to merge onto, round-tripped as-is
                       so "preserve every existing entry" holds even for those.
      extra_keys       any other top-level keys on a dict-shaped file (e.g.
                       "version"), preserved untouched.

    **None** means: `existing` is a non-empty structure that matches NONE of the
    4 known shapes above -- e.g. a delegator variant this hook has never seen,
    like `{"campaigns": {...}}`. The caller MUST treat this the same as a
    fail-open skip (no write at all), never as "start fresh": an empty dict
    `{}` is NOT ambiguous (it correctly returns the canonical "dict" shape with
    zero entries below, matching a genuinely fresh/never-written registry), but
    ANY OTHER unrecognized structure might be real judgment data this hook
    simply doesn't understand yet, and folding onto it as if it were empty
    would silently destroy that data on write-back -- the exact clobber class
    already fixed twice above. Losing one mechanical update is cheap; silently
    destroying judgment fields is not.
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
    if isinstance(existing, dict) and isinstance(existing.get("agents"), list):
        entries, passthrough = split(existing["agents"])
        extra_keys = {k: v for k, v in existing.items() if k != "agents"}
        return "agents_list", entries, passthrough, extra_keys
    if existing == {}:
        # Genuinely empty/fresh: no pre-existing file (the caller defaults
        # `existing` to {} when the file is absent), or a file that legitimately
        # IS the empty object. Safe to treat as the canonical dict shape with
        # zero entries -- this is the one case where "start fresh" is correct,
        # not a guess.
        return "dict", {}, [], {}
    return None


def write_registry_shape(registry_path, shape, entries, passthrough, extra_keys):
    """Write registry entries back to disk in the given shape (one of
    normalize_existing()'s 4 recognized return shapes) -- extracted as its own
    function so fold_registry() below and hooks/watchdog.py's staleness-alert
    dedup stamp (which also needs to safely update ONE field on existing
    registry entries) share the exact same shape-dispatch logic instead of each
    maintaining their own copy that could quietly drift out of sync -- the
    entire reason the last two registry bugs existed was exactly this kind of
    duplicated understanding of "shape" going stale in one place but not the
    other. Callers MUST hold the ledger_dir's .registry.lock before calling this
    and must have already confirmed `shape` came from a real normalize_existing()
    call (never pass a guessed shape). Writes via a temp file + os.replace for
    an atomic swap; never partial-writes registry.json."""
    if shape == "list":
        out = dict(extra_keys)
        out.setdefault("version", 1)
        out["orchestrators"] = list(entries.values()) + passthrough
        out["updated_at"] = now_iso()
    elif shape == "bare_list":
        out = list(entries.values()) + passthrough
    elif shape == "agents_list":
        out = dict(extra_keys)
        out["agents"] = list(entries.values()) + passthrough
        out["updated_at"] = now_iso()
    else:
        out = dict(extra_keys)
        out["agents"] = entries
        out["updated_at"] = now_iso()

    tmp_path = registry_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(out, f, indent=2, sort_keys=True, ensure_ascii=False)
    os.replace(tmp_path, registry_path)


def fold_registry(ledger_dir):
    """Merge-aware: only sets/refreshes the MECHANICAL fields derived from the
    ledger (status, agent_type, name, depth, description, last_event*, session_id)
    on each agent's entry by agent_id, never touching keys it doesn't produce --
    see agents/delegator.md's Registry section for the judgment fields this leaves
    alone, and hooks/README.md for the open question that split raises. Handles
    ALL FOUR pre-existing shapes via normalize_existing -- see its docstring for
    the two clobber bugs this replaced: the canonical dict-shaped registry.json
    (this script's own {"agents": {<agent_id>: {...}}} format), the delegator's
    hand-written {"version":N,"orchestrators":[...]} list shape, a bare top-level
    list, or {"agents": [...]} (a list, not a dict, under "agents")."""
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
                    # Corrupt/unparseable pre-existing file (partial write, disk
                    # issue, manual edit gone wrong) -- do NOT guess and do NOT
                    # treat it as empty-and-safe-to-overwrite: whatever real
                    # content it had before is unknown, and this hook has no
                    # business destroying it. Skip this fold entirely, same as
                    # the unrecognized-shape case normalize_existing() flags
                    # with None below -- losing one mechanical update is cheap,
                    # silently destroying judgment fields is not.
                    return
            normalized = normalize_existing(existing)
            if normalized is None:
                # Parsed fine, but matches none of the known shapes -- see
                # normalize_existing()'s docstring. Same no-write rule.
                return
            shape, merged_entries, passthrough, extra_keys = normalized
            for aid, derived in agents.items():
                merged_row = dict(merged_entries.get(aid, {}))
                merged_row.update(derived)
                merged_entries[aid] = merged_row

            # Write back in the SAME shape that was already on disk -- never
            # convert a hand-written list into this script's own dict shape (or
            # vice versa); a fresh/never-written registry defaults to the
            # canonical dict shape, matching pre-dual-shape behavior exactly.
            write_registry_shape(registry_path, shape, merged_entries, passthrough, extra_keys)
        finally:
            flock_un(lockf)


# ---- project / campaign routing (v1.2.0 per-session storage) ----

_SLUG_RE = re.compile(r"[/._]")


def resolve_project_dir(data, home=None):
    """Resolve ~/.claude/projects/<slug>/ -- the same directory Claude Code
    itself uses for this workspace's own session transcripts.

    Prefers transcript_path from hook stdin: its parent directory IS the project
    dir (transcript_path = <project-dir>/<session-id>.jsonl), and a live probe
    across SessionStart/UserPromptSubmit/PreToolUse/SubagentStart/SubagentStop/
    PostToolUse/Stop/SessionEnd found it present on every single one (CHANGELOG
    v1.2.0) -- so this is the common path and it never needs to reimplement
    Claude Code's own slug scheme. Falls back to slug-encoding cwd only if
    transcript_path is ever absent on some future/unobserved event type.
    Returns None if neither resolves -- callers must treat that as a silent
    no-op, never a reason to guess further.
    """
    home = home or os.path.expanduser("~")
    tp = data.get("transcript_path")
    if isinstance(tp, str) and tp:
        return os.path.dirname(tp)
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR")
    if not isinstance(cwd, str) or not cwd:
        return None
    # Confirmed live against real ~/.claude/projects/ entries, including a
    # deliberately constructed path containing both '.' and '_' (CHANGELOG
    # v1.2.0): every '/', '.', and '_' becomes '-'; everything else (including a
    # literal '-' already in the path) is left alone. NOTE this mapping is not
    # injective -- distinct paths differing only in '/','.','_','-' at the same
    # position can collide onto an identical slug. The transcript_path branch
    # above never has this problem, which is the main reason it's preferred.
    slug = _SLUG_RE.sub("-", os.path.abspath(cwd))
    return os.path.join(home, ".claude", "projects", slug)


def resolve_home_session_id(project_dir, session_id):
    """Look up which delegator campaign, if any, owns this session_id by
    reading <project_dir>/delegator/sessions.json -- written ONLY by
    delegators, never by this hook (read-only from here, always). Returns None
    on every one of: no delegator/ subdirectory (no campaign has ever run in
    this project), no sessions.json, corrupt/non-dict JSON, or the session_id
    simply not present as a key -- all of these mean the same thing to this
    hook: this is not a registered campaign session, touch nothing.
    """
    if not session_id:
        return None
    delegator_dir = os.path.join(project_dir, "delegator")
    if not os.path.isdir(delegator_dir):
        return None
    map_path = os.path.join(delegator_dir, "sessions.json")
    try:
        with open(map_path) as f:
            sessions_map = json.load(f)
    except Exception:
        return None
    if not isinstance(sessions_map, dict):
        return None
    home_id = sessions_map.get(session_id)
    return home_id if isinstance(home_id, str) and home_id else None


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

    project_dir = resolve_project_dir(data)
    if not project_dir:
        return

    home_session_id = resolve_home_session_id(project_dir, data.get("session_id"))
    if not home_session_id:
        # Unregistered session (ordinary chat, or a project that has never run a
        # delegator campaign) -- silent no-op. Nothing is written, nothing is
        # created, not even a peek beyond the sessions.json read above.
        return

    campaign_dir = os.path.join(project_dir, "delegator", home_session_id)

    ts = now_iso()
    row = build_row(data, ts)
    if not row:
        return

    try:
        append_event(campaign_dir, row)
    except Exception:
        pass

    try:
        fold_registry(campaign_dir)
    except Exception:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
