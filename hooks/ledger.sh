#!/usr/bin/env bash
# hooks/ledger.sh — flock-append one compact event line to .delegator/events.jsonl,
# then re-fold .delegator/registry.json in the same invocation. Opt-in only (see
# hooks/README.md) — not wired into the plugin manifest.
#
# FAIL-OPEN CONTRACT: this script must never block or fail the tool call it observes.
# It always exits 0. Any internal error is swallowed.
#
# Field names below are OBSERVED, not guessed: captured live on Claude Code 2.1.198
# via a temporary catch-all dump hook (docs/roadmap-v2.md N1 first step) around a
# single named-subagent spawn. Events confirmed to fire: PreToolUse, PostToolUse,
# SessionStart, SessionEnd, Stop, SubagentStart, SubagentStop, UserPromptSubmit.
# TeammateIdle was accepted by the settings schema (no validation error) but did not
# fire in that probe (a one-shot `claude -p` exits at completion, so a named child
# never sits genuinely idle) — it is wired defensively below since the ledger only
# reads the fields common to every event (hook_event_name, session_id, cwd, ...),
# never a TeammateIdle-specific field that was never observed.
set -u

IN="$(cat)"
[ -n "$IN" ] || exit 0

# Workspace root: the hook payload's own .cwd was present on every event type
# observed; $CLAUDE_PROJECT_DIR (confirmed set in the hook's env) and $PWD are
# fallbacks only. Never fail the hook over this.
WORKDIR="$(printf '%s' "$IN" | jq -r '.cwd // empty' 2>/dev/null)"
[ -n "$WORKDIR" ] || WORKDIR="${CLAUDE_PROJECT_DIR:-$PWD}"

LEDGER_DIR="$WORKDIR/.delegator"
EVENTS="$LEDGER_DIR/events.jsonl"
LOCK="$LEDGER_DIR/.ledger.lock"
MAX_FIELD=400
MAX_BYTES=$((5 * 1024 * 1024))

mkdir -p "$LEDGER_DIR" 2>/dev/null || exit 0

TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Compact one event down to the fields the registry fold needs; truncate any long
# string to MAX_FIELD chars; drop null/empty/[] keys to keep rows small.
#
# GOTCHA (found + fixed while building this): `X // empty` inside an object
# constructor makes the WHOLE row vanish when X is absent, because `empty` yields
# zero outputs and object construction is a cartesian product over each field's
# generator — one empty field silently drops the entire line. Fix: fall back to
# `// null` (a real value) everywhere, then strip nulls once at the end via
# with_entries(select(...)). Verified against all 8 observed payload shapes.
ROW="$(printf '%s' "$IN" | jq -cS --arg ts "$TS" --argjson maxlen "$MAX_FIELD" '
  def trunc: if type == "string" and (length > $maxlen) then (.[0:$maxlen] + "…") else . end;
  {
    ts: $ts,
    event: (.hook_event_name // "unknown"),
    session_id: (.session_id // null),
    transcript_path: (.transcript_path // null),
    agent_id: (.agent_id // .tool_response.agentId // null),
    agent_type: (.agent_type // .tool_response.agentType // .tool_input.subagent_type // null),
    agent_name: (.tool_input.name // null),
    tool: (.tool_name // null),
    summary: ((.last_assistant_message // .tool_response.content[0].text // .tool_input.description // "") | trunc)
  }
  | with_entries(select(.value != null and .value != "" and .value != []))
' 2>/dev/null)"
[ -n "$ROW" ] || exit 0

(
  flock -w 2 200 || exit 0
  if [ -f "$EVENTS" ] && [ "$(stat -c%s "$EVENTS" 2>/dev/null || echo 0)" -ge "$MAX_BYTES" ]; then
    mv -f "$EVENTS" "$EVENTS.$(date -u +%Y%m%dT%H%M%SZ).bak" 2>/dev/null
  fi
  printf '%s\n' "$ROW" >> "$EVENTS"
) 200>"$LOCK" 2>/dev/null

# Re-fold the registry from the ledger in the same invocation. Best-effort: a fold
# failure must never surface as a hook failure.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
[ -n "$SCRIPT_DIR" ] && python3 "$SCRIPT_DIR/fold-registry.py" "$LEDGER_DIR" >/dev/null 2>&1

exit 0
