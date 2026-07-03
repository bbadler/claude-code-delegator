#!/usr/bin/env python3
"""hooks/watchdog.py — portable (stdlib-only) dead-man watchdog (N2 + v1.3.0
auto-wired proactive alerts, github issue #1). No jq -- pure stdlib
json/datetime/re, works unmodified on macOS. Two independent modes, dispatched
by whether any positional argv is given (see main() below):

HOOK MODE (bare invocation, no argv -- how hooks/hooks.json and
hooks/delegator-hooks.json now call this): reads one Claude Code hook payload
from stdin, resolves the campaign exactly like hooks/ledger.py (transcript_path
-> project dir -> sessions.json -> home_session_id; unregistered/no-campaign ->
silent no-op, same contract, see ledger.py's module docstring), then checks
every ACTIVE agent (registry status not in stopped/retired/died) for silence
past its own soft_timeout_minutes (default 15) since its last ledger event. Any
stale agent gets ONE line -- `STALE_AGENT <name> silent <n>m last_event=<type>
(owes: <description-or-purpose>)` -- joined into a single structured hook
output so it becomes real conversation context, not just a log line:
    {"hookSpecificOutput": {"hookEventName": "<event>", "additionalContext": "<the STALE_AGENT lines>"}}
This is the ONE deliberate exception to always-silent output (matching
ledger.py's contract otherwise): nothing is emitted when nothing is stale, and
even when something is, the ONLY thing emitted is this one structured JSON
object -- never bare print(), which Claude Code's hook system captures in its
own telemetry but does NOT surface to the model (live-probed, see CHANGELOG
v1.3.0's PHYSICS note). Wired to PostToolUse (matcher "Agent|SendMessage") and
UserPromptSubmit, both confirmed live to inject additionalContext into the
calling session's context; also wired to TeammateIdle, which is UNPROBED --
kept as unconfirmed upside, a silent no-op costs nothing if that event type
turns out not to support injection. Deliberately NOT wired to SubagentStop --
3 convergent live negatives proved it cannot inject additionalContext on this
Claude Code version, despite it being on-paper documented as capable of it;
hooks/ledger.py keeps listening to SubagentStop for its own event-collection
purposes, unaffected by this finding.

Never alerts twice on the same agent within 10 minutes: stamps a
`last_alert_at` mechanical field onto that agent's own registry.json entry
(via stamp_last_alert_at() below, reusing hooks/ledger.py's exact lock +
shape-tolerant read/write logic so this can never drift from fold_registry()'s
own understanding of registry shape -- imported, not duplicated). This dedupe
window is load-bearing on UserPromptSubmit specifically, since that event
fires on every single user turn, not just when the delegator itself acts.

MANUAL/BACKGROUND MODE (workdir positional arg given -- the original N2
design, predates hook-registration, still works standalone): arm this
yourself as a background process, or run it in the foreground for a one-off
check (see hooks/README.md "Dead-man watchdog" section). Prints
`WATCHDOG: <type> <agent> <evidence>` per anomaly found, or nothing if
healthy. This mode was never hook-registered and isn't affected by the
additionalContext-vs-bare-stdout finding above -- its stdout is read directly
by whatever process armed it, not by Claude Code's hook telemetry.

usage: watchdog.py [workspace-dir] [stale-minutes] [home-session-id]
  workspace-dir     defaults to $PWD -- the delegator's own campaign workspace,
                    used only to derive its ~/.claude/projects/<slug>/ (same slug
                    scheme as ledger.py's cwd-fallback path; this mode has no
                    hook stdin to read a transcript_path from, so it always
                    computes the slug rather than preferring one).
  stale-minutes     STALE_AGENT threshold, default 20.
  home-session-id   check only this one campaign. Omit to scan every campaign
                    subdirectory under this project's delegator/ (useful for an
                    operator checking a project with several past/concurrent
                    campaigns at once).
"""
import datetime
import json
import os
import re
import sys

import ledger

_SLUG_RE = re.compile(r"[/._]")

DEFAULT_SOFT_TIMEOUT_MIN = 15.0
DEDUPE_WINDOW_SEC = 10 * 60
EXCLUDED_STATUSES = {"stopped", "retired", "died"}


def resolve_project_dir(workdir, home=None):
    """Same slug scheme as hooks/ledger.py's resolve_project_dir cwd-fallback
    branch -- see that module's docstring for the live-probed encoding rule and
    its known collision caveat."""
    home = home or os.path.expanduser("~")
    slug = _SLUG_RE.sub("-", os.path.abspath(workdir))
    return os.path.join(home, ".claude", "projects", slug)


def list_campaign_dirs(delegator_dir, home_session_id=None):
    """One (name, path) pair per campaign to scan. Explicit home_session_id ->
    just that one, if it exists. Otherwise every subdirectory of delegator/
    except sessions.json itself."""
    if home_session_id:
        d = os.path.join(delegator_dir, home_session_id)
        return [(home_session_id, d)] if os.path.isdir(d) else []
    out = []
    try:
        entries = os.listdir(delegator_dir)
    except Exception:
        return []
    for name in sorted(entries):
        if name == "sessions.json":
            continue
        d = os.path.join(delegator_dir, name)
        if os.path.isdir(d):
            out.append((name, d))
    return out


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


# ---- hook mode (v1.3.0, github issue #1) ----

def compute_latest_by_agent(rows):
    """Latest ledger row per agent_id, by ISO-8601 UTC string comparison (they
    sort lexicographically the same as chronologically) -- same approach as
    check_stale_agents() above, kept separate so hook mode's broader "any
    active agent, regardless of its last event TYPE" check never has to touch
    that function's narrower "last event was literally SubagentStart"
    semantics, which manual mode still relies on unchanged."""
    latest = {}
    for r in rows:
        aid = r.get("agent_id")
        if not aid:
            continue
        if aid not in latest or r.get("ts", "") > latest[aid].get("ts", ""):
            latest[aid] = r
    return latest


def build_stale_alerts(latest_by_agent, entries_by_agent_id, now):
    """For each agent the registry actually knows about (nothing to check a
    threshold or status against otherwise), excluding any whose status is
    stopped/retired/died, compute silence = now - last_event and flag it past
    its own soft_timeout_minutes (a judgment field the delegator charter
    writes; default 15 if absent/invalid) unless a still-fresh last_alert_at
    (<10 min old) already covers it. Returns (alert_lines, agent_ids_to_stamp)
    -- the caller stamps last_alert_at only for the ids actually alerted on."""
    alerts, to_stamp = [], []
    for aid, row in latest_by_agent.items():
        entry = entries_by_agent_id.get(aid)
        if not entry:
            continue
        if entry.get("status", "unknown") in EXCLUDED_STATUSES:
            continue
        try:
            ts_dt = parse_ts(row["ts"])
        except Exception:
            continue
        idle_sec = (now - ts_dt).total_seconds()
        threshold_min = entry.get("soft_timeout_minutes")
        if not isinstance(threshold_min, (int, float)) or threshold_min <= 0:
            threshold_min = DEFAULT_SOFT_TIMEOUT_MIN
        if idle_sec <= threshold_min * 60:
            continue
        last_alert_at = entry.get("last_alert_at")
        if last_alert_at:
            try:
                since_alert = (now - parse_ts(last_alert_at)).total_seconds()
                if since_alert < DEDUPE_WINDOW_SEC:
                    continue
            except Exception:
                pass  # malformed last_alert_at must never suppress a real alert
        name = entry.get("name") or aid
        idle_min = int(idle_sec // 60)
        last_event_type = row.get("event", "unknown")
        owes = entry.get("description") or entry.get("purpose")
        line = f"STALE_AGENT {name} silent {idle_min}m last_event={last_event_type}"
        if owes:
            line += f" (owes: {owes})"
        alerts.append(line)
        to_stamp.append(aid)
    return alerts, to_stamp


def stamp_last_alert_at(campaign_dir, agent_ids, ts):
    """Safely stamp last_alert_at=ts onto each of the given agent_ids' existing
    registry entries. Reuses hooks/ledger.py's exact lock (the SAME
    .registry.lock file, so this and fold_registry() are mutually exclusive,
    never racing each other) and shape-tolerant read/normalize/write logic
    (imported, not duplicated) so this can never drift from fold_registry()'s
    own understanding of registry shape -- the entire reason the last two
    registry bugs existed was exactly this kind of duplicated understanding
    going stale in one place but not the other. Never creates anything: if the
    registry can't be read in a known shape, or an agent_id isn't present,
    that agent silently doesn't get stamped -- the alert itself already
    printed and matters more than the dedup record surviving. Fully fail-open:
    any exception here is swallowed, never propagated."""
    if not agent_ids:
        return
    registry_path = os.path.join(campaign_dir, "registry.json")
    lock_path = os.path.join(campaign_dir, ".registry.lock")
    try:
        with open(lock_path, "a") as lockf:
            if not ledger.flock_ex(lockf):
                return
            try:
                if not os.path.isfile(registry_path):
                    return
                try:
                    with open(registry_path) as f:
                        existing = json.load(f)
                except Exception:
                    return
                normalized = ledger.normalize_existing(existing)
                if normalized is None:
                    return
                shape, entries, passthrough, extra_keys = normalized
                changed = False
                for aid in agent_ids:
                    if aid in entries:
                        entries[aid] = dict(entries[aid])
                        entries[aid]["last_alert_at"] = ts
                        changed = True
                if changed:
                    ledger.write_registry_shape(registry_path, shape, entries, passthrough, extra_keys)
            finally:
                ledger.flock_un(lockf)
    except Exception:
        pass


def hook_main(raw):
    """Entry point for the auto-registered hook path (PostToolUse,
    UserPromptSubmit, TeammateIdle -- see module docstring). Silent no-op on
    anything unexpected: empty/malformed stdin, unregistered session, missing
    registry, unrecognized registry shape, or simply nothing stale to report."""
    try:
        data = json.loads(raw)
    except Exception:
        return
    if not isinstance(data, dict):
        return

    event_name = data.get("hook_event_name") or "unknown"

    project_dir = ledger.resolve_project_dir(data)
    if not project_dir:
        return

    home_session_id = ledger.resolve_home_session_id(project_dir, data.get("session_id"))
    if not home_session_id:
        return

    campaign_dir = os.path.join(project_dir, "delegator", home_session_id)
    events_path = os.path.join(campaign_dir, "events.jsonl")
    registry_path = os.path.join(campaign_dir, "registry.json")

    rows = load_rows(events_path)
    if not rows:
        return

    if not os.path.isfile(registry_path):
        return
    try:
        with open(registry_path) as f:
            existing = json.load(f)
    except Exception:
        return
    normalized = ledger.normalize_existing(existing)
    if normalized is None:
        return
    _, entries_by_agent_id, _, _ = normalized

    now = datetime.datetime.now(datetime.timezone.utc)
    latest = compute_latest_by_agent(rows)
    alerts, to_stamp = build_stale_alerts(latest, entries_by_agent_id, now)
    if not alerts:
        return

    stamp_last_alert_at(campaign_dir, to_stamp, ledger.now_iso())

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": "\n".join(alerts),
        }
    }))


def main():
    if len(sys.argv) == 1:
        # No positional args -- a hook invocation (Claude Code calls hook
        # commands bare, payload on stdin), never the manual/background-arm
        # usage below. See module docstring.
        raw = sys.stdin.read()
        if not raw.strip():
            return
        hook_main(raw)
        return

    workdir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    stale_min = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
    home_session_id = sys.argv[3] if len(sys.argv) > 3 else None

    project_dir = resolve_project_dir(workdir)
    delegator_dir = os.path.join(project_dir, "delegator")
    # This script only ever reads -- never creates delegator/ or any campaign
    # subdirectory -- so it's already side-effect-free with nothing here; this
    # guard just makes the "only registered campaigns get watched" contract
    # explicit rather than relying on load_rows()'s isfile check to imply it.
    if not os.path.isdir(delegator_dir):
        return

    campaigns = list_campaign_dirs(delegator_dir, home_session_id)
    if not campaigns:
        return

    now = datetime.datetime.now(datetime.timezone.utc)
    multi = len(campaigns) > 1
    for cid, cdir in campaigns:
        rows = load_rows(os.path.join(cdir, "events.jsonl"))
        if not rows:
            continue
        lines = check_stale_agents(rows, now, stale_min * 60) + check_unanswered_gates(rows)
        for line in lines:
            if multi:
                # re-tag "WATCHDOG: X ..." as "WATCHDOG: [<cid>] X ..." so a
                # multi-campaign scan's output stays attributable per line.
                print(f"WATCHDOG: [{cid}] {line[len('WATCHDOG: '):]}")
            else:
                print(line)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
