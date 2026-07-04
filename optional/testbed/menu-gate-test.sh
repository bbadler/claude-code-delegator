#!/usr/bin/env bash
# BMAD menu-gate relay e2e — FULLY ISOLATED from the shared .cleanhome / stress
# workspaces (own cleanhome + own /tmp workspaces) so it can run alongside a live
# stress-tests / run_all campaign without colliding. Mirrors cleanroom.sh (fake
# HOME + trusted /tmp workspace + ledger hooks + campaign seed) and stress-tests.sh
# (per-run mint_campaign, `claude -p --agent delegator`).
#
#   ./menu-gate-test.sh build          # isolated cleanhome + pos/neg workspaces
#   ./menu-gate-test.sh pos            # positive: orchestrator brief HAS the relay-gate line
#   ./menu-gate-test.sh neg            # negative control: brief OMITS the relay-gate line
#   ./menu-gate-test.sh harvest pos|neg
set -uo pipefail
cd "$(dirname "$0")"
TESTBED="$(pwd)"
REPO_ROOT="$(cd .. && pwd)"
CLEAN="$TESTBED/.cleanhome-menu"
BASE="/tmp/delegator-menugate-${USER:-u}"
LOGDIR="$TESTBED/.menu-gate-logs"
export HOME="$CLEAN"; unset CLAUDE_CONFIG_DIR

mint_campaign() {  # $1 = workspace path -> mints+registers a fresh sid, echoes it
  python3 - "$1" "$HOME" <<'PY'
import json, os, re, sys, uuid
ws, home = sys.argv[1], sys.argv[2]
slug = re.sub(r"[/._]", "-", os.path.abspath(ws))
deldir = os.path.join(home, ".claude", "projects", slug, "delegator")
sid = str(uuid.uuid4())
os.makedirs(os.path.join(deldir, sid), exist_ok=True)
sp = os.path.join(deldir, "sessions.json")
try:
    s = json.load(open(sp))
    if not isinstance(s, dict): s = {}
except Exception:
    s = {}
s[sid] = sid
json.dump(s, open(sp, "w"), indent=2)
open(ws + ".session-id", "w").write(sid)
print(sid, end="")
PY
}

build() {
  rm -rf "$CLEAN" "$BASE-pos" "$BASE-neg"
  mkdir -p "$CLEAN/.claude/agents" "$LOGDIR"
  cp "$REPO_ROOT/agents/delegator.md" "$REPO_ROOT/agents/orchestrator.md" "$CLEAN/.claude/agents/"
  [ -f "$REPO_ROOT/agents/worker.md" ] && cp "$REPO_ROOT/agents/worker.md" "$CLEAN/.claude/agents/" || true
  [ -f "$REAL_HOME/.claude/.credentials.json" ] && cp "$REAL_HOME/.claude/.credentials.json" "$CLEAN/.claude/" || true
  [ -f "$REAL_HOME/.claude.json" ] && cp "$REAL_HOME/.claude.json" "$CLEAN/.claude.json" || true
  rm -rf "$CLEAN/.claude/projects"
  # ledger hooks resolved to this checkout (same as cleanroom.sh)
  python3 - "$REPO_ROOT" "$CLEAN/.claude/settings.json" <<'PY'
import json, sys
repo, out = sys.argv[1], sys.argv[2]
frag = json.load(open(f"{repo}/hooks/delegator-hooks.json"))
def sub(v):
    if isinstance(v, str): return v.replace("__DELEGATOR_REPO__", repo)
    if isinstance(v, list): return [sub(x) for x in v]
    if isinstance(v, dict): return {k: sub(x) for k, x in v.items()}
    return v
json.dump(sub(frag), open(out, "w"), indent=2)
PY
  for suf in pos neg; do
    ws="$BASE-$suf"
    mkdir -p "$ws"
    cp -r "$TESTBED/data" "$TESTBED/CLAUDE.md" "$TESTBED/.claude" "$ws/"
    rm -rf "$ws/.claude/agents" 2>/dev/null || true
    rm -f "$ws/menu-gate-analysis.md" "$ws/census-report.md" "$ws/audit-report.md"
    mint_campaign "$ws" >/dev/null
    python3 - "$CLEAN/.claude.json" "$ws" <<'PY'
import json, sys
path, work = sys.argv[1], sys.argv[2]
try: d = json.load(open(path))
except Exception: d = {}
d.setdefault("projects", {}).setdefault(work, {})["hasTrustDialogAccepted"] = True
json.dump(d, open(path, "w"))
PY
  done
  echo "cleanhome : $CLEAN"
  echo "agents    : $(ls "$CLEAN/.claude/agents" | tr '\n' ' ')"
  echo "menu-gate : $([ -f "$BASE-pos/.claude/skills/menu-gate/SKILL.md" ] && echo present || echo MISSING) in workspace copies"
  echo "pos ws    : $BASE-pos (sid $(cat "$BASE-pos.session-id"))"
  echo "neg ws    : $BASE-neg (sid $(cat "$BASE-neg.session-id"))"
}

# ---- orchestrator briefs: identical EXCEPT the one relay-gate sentence ----
GATE_LINE='Any interactive decision or menu the skill presents to the user, you MUST relay to me (your spawner) via SendMessage, VERBATIM (copy its exact text), and then WAIT for my answer before continuing — never pick an option yourself.'
NOGATE_LINE='Execute every step of the skill and report back when you are done.'

lead_prompt() {  # $1 = the orchestrator brief's gate/no-gate sentence
  cat <<EOF
You are the LEAD of a delegation team. Routing is already decided for you: the work is the /menu-gate skill. Do NOT run any router/advisor, do NOT invoke any skill yourself, and do NOT do the analysis yourself.

Step 1 — spawn ONE named orchestrator with the Agent tool, exactly:
  subagent_type: "orchestrator", name: "menu-runner"
  brief: "You are menu-runner. Invoke the /menu-gate skill FOR REAL on this workspace (your current working directory) using the Skill tool. $1 When the skill is fully finished, report back to me."

Step 2 — act as the user-proxy for menu-runner:
  - If menu-runner sends you an interactive menu or asks you to choose, reply to it (SendMessage to "menu-runner") with EXACTLY this text and nothing else: [C]
  - If menu-runner finishes WITHOUT ever asking you to choose, do not send [C]; just note that it never asked.

You are headless (claude -p): your final turn ends the process, so do NOT conclude while menu-runner still owes a deliverable. After you answer (or if it never asks), stay in-turn and poll for menu-runner's completion and for the file menu-gate-analysis.md at the workspace root. Conclude only once menu-runner has reported done, or after a clear bounded timeout.

Final report — answer these exactly:
  (a) Did menu-runner ask you to choose? If yes, paste its message to you VERBATIM.
  (b) What did you reply, if anything?
  (c) Does menu-gate-analysis.md now exist at the workspace root?
EOF
}

run() {  # $1 = suffix (pos|neg), $2 = brief sentence
  local suf="$1" line="$2" ws="$BASE-$1"
  [ -d "$CLEAN/.claude" ] && [ -d "$ws" ] || { echo "run ./menu-gate-test.sh build first" >&2; exit 1; }
  local sid; sid="$(cat "$ws.session-id")"
  mkdir -p "$LOGDIR"
  lead_prompt "$line" > "$LOGDIR/$suf.prompt.txt"
  echo "[$suf] sid=$sid ws=$ws  -> $LOGDIR/$suf.json"
  cd "$ws" && timeout "${MENU_TIMEOUT:-900}" claude -p --model sonnet --session-id "$sid" --agent delegator \
      --output-format json "$(cat "$LOGDIR/$suf.prompt.txt")" \
      > "$LOGDIR/$suf.json" 2> "$LOGDIR/$suf.stderr.log"
  echo "[$suf] exit=$? -> $LOGDIR/$suf.json"
}

harvest() {  # $1 = suffix — snapshot transcripts + ledger + artifact into LOGDIR
  local suf="$1" ws="$BASE-$1"
  local slug; slug="$(python3 -c "import os,re;print(re.sub(r'[/._]','-',os.path.abspath('$ws')))")"
  local proj="$CLEAN/.claude/projects/$slug"
  local out="$LOGDIR/$suf"
  rm -rf "$out"; mkdir -p "$out/transcripts"
  cp -r "$proj"/*.jsonl "$out/transcripts/" 2>/dev/null || true
  find "$proj" -path "*/subagents/*.jsonl" -exec cp {} "$out/transcripts/" \; 2>/dev/null || true
  cp "$proj"/delegator/*/events.jsonl "$out/events.jsonl" 2>/dev/null || true
  cp "$proj"/delegator/*/registry.json "$out/registry.json" 2>/dev/null || true
  cp "$ws/menu-gate-analysis.md" "$out/menu-gate-analysis.md" 2>/dev/null || echo "NO menu-gate-analysis.md" > "$out/NO-ARTIFACT"
  echo "harvested $suf -> $out ($(ls "$out/transcripts" | wc -l) transcripts)"
}

: "${REAL_HOME:=/home/${USER:-user}}"
case "${1:-}" in
  build)   build ;;
  pos)     run pos "$GATE_LINE" ;;
  neg)     run neg "$NOGATE_LINE" ;;
  harvest) harvest "${2:?pos|neg}" ;;
  *) echo "usage: build | pos | neg | harvest pos|neg" >&2; exit 2 ;;
esac
