#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
dest="$HOME/.claude/agents"
defs=(delegator orchestrator worker)

version() {
  python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown"
}

do_install() {
  echo "claude-code-delegator v$(version)"
  mkdir -p "$dest"
  for name in "${defs[@]}"; do
    f="agents/$name.md"
    base="$name.md"
    if [ -f "$dest/$base" ] && ! cmp -s "$f" "$dest/$base"; then
      cp "$dest/$base" "$dest/$base.bak.$(date +%s)"
      echo "backed up existing $base"
    fi
    cp "$f" "$dest/$base"
    echo "installed $base -> $dest/$base"
  done
  echo "done — launch with: claude --agent delegator (run ./install.sh --verify to confirm)"
}

do_verify() {
  echo "claude-code-delegator v$(version) — verifying via a live claude -p call..."
  out="$(claude -p --model sonnet "List every custom agent type available to you via the Agent tool in this session, one bare name per line, nothing else (no descriptions, no bullets)." 2>&1)" || {
    echo "verify: claude -p failed to run" >&2
    exit 1
  }
  status=0
  for name in "${defs[@]}"; do
    if grep -qiw "$name" <<<"$out"; then
      echo "  [ok] $name"
    else
      echo "  [MISSING] $name"
      status=1
    fi
  done
  if [ "$status" -eq 0 ]; then
    echo "verify: all agent types present"
  else
    echo "verify: FAILED — see MISSING above" >&2
    echo "--- raw claude -p output ---" >&2
    echo "$out" >&2
  fi
  exit "$status"
}

do_uninstall() {
  for name in "${defs[@]}"; do
    base="$name.md"
    target="$dest/$base"
    # plain lexical sort (portable: no GNU ls -v) -- safe because .bak.<epoch>
    # suffixes are fixed-width (10-digit seconds until year 2286), so lexical
    # order == numeric order == chronological order.
    latest_bak="$(ls -1 "$dest/$base.bak."* 2>/dev/null | sort | tail -1 || true)"
    if [ -f "$target" ]; then
      rm -f "$target"
      echo "removed $target"
    fi
    if [ -n "$latest_bak" ]; then
      mv "$latest_bak" "$target"
      echo "restored $target <- $(basename "$latest_bak")"
    fi
  done
  echo "uninstall done"
}

case "${1:-}" in
  --verify) do_verify ;;
  --uninstall) do_uninstall ;;
  "") do_install ;;
  *) echo "usage: $0 [--verify|--uninstall]" >&2; exit 2 ;;
esac
