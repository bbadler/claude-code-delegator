#!/usr/bin/env bash
# hooks/watchdog.sh — dead-man watchdog (N2). Reads .delegator/events.jsonl (written
# by hooks/ledger.sh) and prints one line per anomaly:
#   WATCHDOG: <type> <agent> <evidence>
# No Monitor integration yet -- the delegator arms this itself as a background Bash
# job (see hooks/README.md "Dead-man watchdog" section). Silent output = healthy.
# usage: watchdog.sh [workspace-dir] [stale-minutes]
set -u
WORKDIR="${1:-$PWD}"
STALE_MIN="${2:-20}"
EVENTS="$WORKDIR/.delegator/events.jsonl"
[ -f "$EVENTS" ] || exit 0

# STALE_AGENT: an agent's latest ledger row is still SubagentStart (it never reached
# SubagentStop/PostToolUse) and that row is older than STALE_MIN minutes.
jq -rn --argjson now "$(date -u +%s)" --argjson stale_sec "$((STALE_MIN * 60))" '
  [inputs] as $all
  | ( $all | group_by(.agent_id) | map(select(.[0].agent_id != null) | max_by(.ts)) )[]
  | select(.event == "SubagentStart")
  | ($now - (.ts | fromdateiso8601)) as $idle_sec
  | select($idle_sec > $stale_sec)
  | "WATCHDOG: STALE_AGENT \(.agent_id) last_event=\(.event)@\(.ts) idle_min=\(($idle_sec / 60) | floor)"
' "$EVENTS"

# UNANSWERED_GATE: a row whose summary carries a gate marker, with no later ledger
# row at all for that same session_id (i.e. the session went quiet right after).
jq -rn '
  [inputs] as $all
  | $all[]
  | select(.summary != null and (.summary | test("gate|SendMessage me"; "i")))
  | . as $g
  | select( ($all | map(select(.session_id == $g.session_id and .ts > $g.ts)) | length) == 0 )
  | "WATCHDOG: UNANSWERED_GATE \($g.agent_id // $g.session_id // "unknown") summary=\($g.summary)"
' "$EVENTS"

exit 0
