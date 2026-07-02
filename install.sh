#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
dest="$HOME/.claude/agents"
defs=(delegator orchestrator worker)
skill_src="skills/delegator-mode"
skill_dest="$HOME/.claude/skills/delegator-mode"
# Old (pre-rename) install location -- migrated away from on every install, see
# the migration block in install_skill() below. The skill used to install as
# "delegator-activate"; the plugin registered it as "delegation-kit:activate" --
# two different names for one skill was confusing in a mixed skill list, so both
# now converge on "delegator-mode".
old_skill_dest="$HOME/.claude/skills/delegator-activate"
# Skill backups must NEVER live under ~/.claude/skills/ as a SKILL.md-bearing
# directory -- Claude Code's skill discovery scans every directory there for a
# SKILL.md and registers whatever it finds, so a plain
# "delegator-activate.bak.<epoch>/" directory (still containing SKILL.md at its
# original name inside) silently comes back as a second, live, duplicate skill.
# Confirmed live: a backup created this way showed up in a real session's skill
# list. Agent-def backups don't have this problem (bare .md FILES aren't scanned
# for skill registration), so only the skill needs a separate tree.
skill_backup_dir="$HOME/.claude/skills-backups"

version() {
  python3 -c "import json; print(json.load(open('.claude-plugin/plugin.json'))['version'])" 2>/dev/null || echo "unknown"
}

install_skill() {
  mkdir -p "$(dirname "$skill_dest")"
  if [ -d "$skill_dest" ] && ! diff -r "$skill_src" "$skill_dest" >/dev/null 2>&1; then
    mkdir -p "$skill_backup_dir"
    mv "$skill_dest" "$skill_backup_dir/delegator-mode.$(date +%s)"
    echo "backed up existing delegator-mode skill -> $skill_backup_dir"
  fi
  if [ ! -d "$skill_dest" ]; then
    cp -r "$skill_src" "$skill_dest"
    echo "installed skill delegator-mode -> $skill_dest (classic /delegator-mode)"
  fi
  # Migration from the old name: only remove it AFTER the new one is safely in
  # place, so a failed install never leaves the user with neither. Otherwise an
  # upgrader ends up with both "delegator-activate" and "delegator-mode" live at
  # once -- two names for one skill, the exact confusion this rename fixes.
  if [ -d "$old_skill_dest" ]; then
    rm -rf "$old_skill_dest"
    echo "migrated: removed old skill name delegator-activate ($old_skill_dest) -> use delegator-mode"
  fi
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
  install_skill
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
  if [ -d "$skill_dest" ] && [ -f "$skill_dest/SKILL.md" ]; then
    echo "  [ok] skill: delegator-mode ($skill_dest)"
  else
    echo "  [MISSING] skill: delegator-mode ($skill_dest)"
    status=1
  fi
  if [ "$status" -eq 0 ]; then
    echo "verify: all agent types and the delegator-mode skill are present"
  else
    echo "verify: FAILED — see MISSING above" >&2
    echo "--- raw claude -p output ---" >&2
    echo "$out" >&2
  fi
  exit "$status"
}

uninstall_skill() {
  latest_skill_bak="$(ls -1d "$skill_backup_dir"/delegator-mode.* 2>/dev/null | sort | tail -1 || true)"
  if [ -d "$skill_dest" ]; then
    rm -rf "$skill_dest"
    echo "removed $skill_dest"
  fi
  if [ -n "$latest_skill_bak" ]; then
    mv "$latest_skill_bak" "$skill_dest"
    echo "restored $skill_dest <- $(basename "$latest_skill_bak")"
  fi
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
  uninstall_skill
  echo "uninstall done"
}

case "${1:-}" in
  --verify) do_verify ;;
  --uninstall) do_uninstall ;;
  # Syncs ONLY the skill directory -- never touches agents/*.md. Use this for
  # any skill-only testing/syncing; agents/delegator.md and agents/orchestrator.md
  # are lead-owned and must never be copied over as a side effect of unrelated
  # work (confirmed live: a plain `./install.sh` re-sync once clobbered
  # in-flight edits to both files because the default action always re-copies
  # every def alongside the skill). `--skill-only --uninstall` exercises the
  # skill's own remove/restore-from-backup path the same way, still without
  # ever touching agents/*.md -- lets the full skill lifecycle (install /
  # reinstall-with-diff / uninstall / restore) be proven in isolation.
  --skill-only)
    case "${2:-}" in
      --uninstall) uninstall_skill; echo "skill uninstall done" ;;
      "") install_skill ;;
      *) echo "usage: $0 --skill-only [--uninstall]" >&2; exit 2 ;;
    esac
    ;;
  "") do_install ;;
  *) echo "usage: $0 [--verify|--uninstall|--skill-only [--uninstall]]" >&2; exit 2 ;;
esac
