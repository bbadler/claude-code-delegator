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
[ -f "$HOME/.claude/.credentials.json" ] && cp "$HOME/.claude/.credentials.json" "$CLEAN/.claude/" || true
[ -f "$HOME/.claude.json" ] && cp "$HOME/.claude.json" "$CLEAN/.claude.json" || true
echo '{}' > "$CLEAN/.claude/settings.json"

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
