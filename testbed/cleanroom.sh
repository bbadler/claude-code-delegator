#!/usr/bin/env bash
# Build a FULLY isolated test environment. Two leak channels exist (both verified live):
#   1. user-level: $HOME/.claude/CLAUDE.md + memory + settings  -> fixed with a fake HOME
#   2. ancestor-walk: any cwd under /home/<u> picks up /home/<u>/.claude/CLAUDE.md as
#      "project instructions" of the ancestor dir                -> fixed by running the
#      workspace from /tmp (outside every personal ancestor)
# Result: the run sees ONLY this repo's agent defs + the testbed workspace (+ your auth).
set -euo pipefail
cd "$(dirname "$0")"
CLEAN="$(pwd)/.cleanhome"
WORK="/tmp/delegator-testbed-${USER:-u}"
rm -rf "$CLEAN" "$WORK"

# fake HOME: agent defs + auth/state only
mkdir -p "$CLEAN/.claude/agents"
cp ../agents/delegator.md ../agents/orchestrator.md "$CLEAN/.claude/agents/"
[ -f ../agents/worker.md ] && cp ../agents/worker.md "$CLEAN/.claude/agents/" || true
[ -f "$HOME/.claude/.credentials.json" ] && cp "$HOME/.claude/.credentials.json" "$CLEAN/.claude/" || true
[ -f "$HOME/.claude.json" ] && cp "$HOME/.claude.json" "$CLEAN/.claude.json" || true

# memory OFF in cleanroom: guarantee auto-memory cannot exist in the fake HOME
# (defensive -- $CLEAN was just wiped above, but this stays true even if a future
# step or a manual rerun ever populates it before this point).
rm -rf "$CLEAN/.claude/projects"

# N1 ledger hooks (opt-in, see ../hooks/README.md) -- resolve the __DELEGATOR_REPO__
# placeholder in delegator-hooks.json to this checkout's absolute path and load it
# as the cleanroom's user-level settings, so every cleanroom run exercises the real
# hook-written ledger + derived registry, not just the agent defs.
REPO_ROOT="$(cd .. && pwd)"
python3 - "$REPO_ROOT" "$CLEAN/.claude/settings.json" <<'PY'
import json, sys
repo, out_path = sys.argv[1], sys.argv[2]
frag = json.load(open(f"{repo}/hooks/delegator-hooks.json"))

def sub(v):
    if isinstance(v, str):
        return v.replace("__DELEGATOR_REPO__", repo)
    if isinstance(v, list):
        return [sub(x) for x in v]
    if isinstance(v, dict):
        return {k: sub(x) for k, x in v.items()}
    return v

json.dump(sub(frag), open(out_path, "w"), indent=2)
PY

# disposable workspace copy OUTSIDE /home
mkdir -p "$WORK"
cp -r data CLAUDE.md .claude "$WORK/"
rm -rf "$WORK/.claude/agents" 2>/dev/null || true

# pre-trust the /tmp workspace inside the cleanroom state (allowlist is ignored otherwise)
python3 - "$CLEAN/.claude.json" "$WORK" <<'PY'
import json, sys
path, work = sys.argv[1], sys.argv[2]
try:
    d = json.load(open(path))
except Exception:
    d = {}
pr = d.setdefault("projects", {})
e = pr.setdefault(work, {})
e["hasTrustDialogAccepted"] = True
json.dump(d, open(path, "w"))
print("trusted:", work)
PY
echo "cleanroom HOME : $CLEAN"
echo "workspace      : $WORK"
echo "agents         : $(ls "$CLEAN/.claude/agents" | tr '\n' ' ')"
echo "ledger hooks   : $(python3 -c "import json;print(','.join(json.load(open('$CLEAN/.claude/settings.json'))['hooks'].keys()))" 2>/dev/null || echo 'NONE')"
