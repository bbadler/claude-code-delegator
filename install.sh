#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
dest="$HOME/.claude/agents"
mkdir -p "$dest"
for f in agents/delegator.md agents/orchestrator.md; do
  base="$(basename "$f")"
  if [ -f "$dest/$base" ] && ! cmp -s "$f" "$dest/$base"; then
    cp "$dest/$base" "$dest/$base.bak.$(date +%s)"
    echo "backed up existing $base"
  fi
  cp "$f" "$dest/$base"
  echo "installed $base -> $dest/$base"
done
echo "done — launch with: claude --agent delegator"
