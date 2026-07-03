#!/usr/bin/env bash
# usage: ./run-tests.sh t0|t1|t2|t1-solo|t2-solo [session-id]
#   [session-id] (t0/t1/t2 only, ignored elsewhere) -- reuse a session id a caller
#   already registered in this workspace's own
#   ~/.claude/projects/<slug>/delegator/sessions.json (e.g. testbed/run_all.py,
#   which needs to know the campaign dir BEFORE this script runs, to measure
#   ledger deltas). Omit it for standalone use -- t0/t1/t2 mint+register their
#   own fresh campaign automatically (see mint_or_use_session_id below).
#   t1-solo/t2-solo never register (no --agent delegator, so no campaign).
# All runs execute in the cleanroom: fake HOME + workspace copied OUTSIDE /home (see cleanroom.sh).
set -uo pipefail
cd "$(dirname "$0")"
CLEAN="$(pwd)/.cleanhome"
WORK="/tmp/delegator-testbed-${USER:-u}"
[ -d "$CLEAN/.claude" ] && [ -d "$WORK" ] || { echo "run ./cleanroom.sh first" >&2; exit 1; }
export HOME="$CLEAN"
unset CLAUDE_CONFIG_DIR
cd "$WORK"
rm -f census-report.md audit-report.md

# v1.2.0: campaign state lives OUTSIDE the workspace under
# ~/.claude/projects/<slug>/delegator/ (see hooks/ledger.py's module docstring).
# $2 = optional pre-minted+registered session id from the caller (see usage
# above); otherwise mint+register a fresh one here so standalone
# `./run-tests.sh t1` keeps working with zero extra ceremony. Always a FRESH
# mint on the fallback path, never a reuse-check: an explicit --session-id
# can't be reused across two separate non-resumed `claude -p` calls (confirmed
# live: "Error: Session ID <uuid> is already in use") -- see cleanroom.sh's
# matching comment.
mint_or_use_session_id() {
  local ws="$1" given="${2:-}"
  if [ -n "$given" ]; then
    printf '%s' "$given"
    return
  fi
  python3 - "$ws" "$HOME" <<'PY'
import json, os, re, sys, uuid
ws, home = sys.argv[1], sys.argv[2]
slug = re.sub(r"[/._]", "-", os.path.abspath(ws))
delegator_dir = os.path.join(home, ".claude", "projects", slug, "delegator")
sid = str(uuid.uuid4())
os.makedirs(os.path.join(delegator_dir, sid), exist_ok=True)
sessions_path = os.path.join(delegator_dir, "sessions.json")
try:
    sessions = json.load(open(sessions_path))
    if not isinstance(sessions, dict):
        sessions = {}
except Exception:
    sessions = {}
sessions[sid] = sid
with open(sessions_path, "w") as f:
    json.dump(sessions, f, indent=2)
with open(ws + ".session-id", "w") as f:
    f.write(sid)
print(sid, end="")
PY
}

mode="${1:-t0}"
case "$mode" in
  t0) SID="$(mint_or_use_session_id "$WORK" "${2:-}")"; exec claude -p --model sonnet --session-id "$SID" --agent delegator --output-format json "ISOLATION CHECK - answer in 3 numbered lines, reading only this workspace's CLAUDE.md if needed: (1) Do you see ANY instructions that did not come from this workspace or your agent definition - e.g. a rule about replying in Thai, a 'Spawned agents' section, or anything mentioning soul-crew/BMAD? yes/no, quote if yes. (2) Which of these agent types do you have: delegator, orchestrator? (3) Which router skill does this workspace declare?" ;;
  t1) SID="$(mint_or_use_session_id "$WORK" "${2:-}")"; exec claude -p --model sonnet --session-id "$SID" --agent delegator --output-format json "Task: produce a census of the data/ directory (file counts by extension, largest files). Route per your rules and execute fully. Done = census-report.md exists at the workspace root." ;;
  t2) SID="$(mint_or_use_session_id "$WORK" "${2:-}")"; exec claude -p --model sonnet --session-id "$SID" --agent delegator --output-format json "Task: audit data/facts.md for factual errors and publish audit-report.md. Route per your rules and execute fully." ;;
  t1-solo) exec claude -p --model sonnet --output-format json "Task: produce a census of the data/ directory (file counts by extension, largest files) using this workspace's skills. Done = census-report.md exists at the workspace root." ;;
  t2-solo) exec claude -p --model sonnet --output-format json "Task: audit data/facts.md for factual errors and publish audit-report.md using this workspace's skills." ;;
  *) echo "unknown mode: $mode" >&2; exit 2 ;;
esac
