#!/usr/bin/env python3
"""hooks/watchdog.py — portable (stdlib-only) dead-man watchdog (N2), replacing
watchdog.sh. Reads the events.jsonl of one or more delegator campaigns (written by
hooks/ledger.py, see its module docstring for the v1.2.0 per-session storage
layout under ~/.claude/projects/<slug>/delegator/) and prints one line per
anomaly:
    WATCHDOG: <type> <agent> <evidence>                        (single campaign)
    WATCHDOG: [<home-session-id>] <type> <agent> <evidence>     (scanning >1 campaign)
No Monitor integration yet -- arm this yourself (see hooks/README.md "Dead-man
watchdog" section). Silent output = healthy. No jq -- pure stdlib json/datetime/re,
works unmodified on macOS.

This script is NOT registered in hooks/hooks.json or hooks/delegator-hooks.json --
unlike ledger.py it never receives a hook payload on stdin, it's armed directly by
a running delegator as a background process (see hooks/README.md). Its stdout
(the WATCHDOG: lines above) is a DELIBERATE, intended context injection when the
delegator reads it back -- unlike ledger.py, which never prints anything, this
script's whole purpose is the alert text; the design guard is scope (it only ever
reads a registered campaign's own events, see resolve_project_dir/
list_campaign_dirs below, so its output stays confined to real campaign
workspaces), not silence.

usage: watchdog.py [workspace-dir] [stale-minutes] [home-session-id]
  workspace-dir     defaults to $PWD -- the delegator's own campaign workspace,
                    used only to derive its ~/.claude/projects/<slug>/ (same slug
                    scheme as ledger.py's cwd-fallback path; watchdog.py has no
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


_SLUG_RE = re.compile(r"[/._]")


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


def main():
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
