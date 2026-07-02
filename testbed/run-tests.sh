#!/usr/bin/env bash
# usage: ./run-tests.sh t0|t1|t2|t1-solo|t2-solo
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
mode="${1:-t0}"
case "$mode" in
  t0) exec claude -p --model sonnet --agent delegator --output-format json "ISOLATION CHECK - answer in 3 numbered lines, reading only this workspace's CLAUDE.md if needed: (1) Do you see ANY instructions that did not come from this workspace or your agent definition - e.g. a rule about replying in Thai, a 'Spawned agents' section, or anything mentioning soul-crew/BMAD? yes/no, quote if yes. (2) Which of these agent types do you have: delegator, orchestrator? (3) Which router skill does this workspace declare?" ;;
  t1) exec claude -p --model sonnet --agent delegator --output-format json "Task: produce a census of the data/ directory (file counts by extension, largest files). Route per your rules and execute fully. Done = census-report.md exists at the workspace root." ;;
  t2) exec claude -p --model sonnet --agent delegator --output-format json "Task: audit data/facts.md for factual errors and publish audit-report.md. Route per your rules and execute fully." ;;
  t1-solo) exec claude -p --model sonnet --output-format json "Task: produce a census of the data/ directory (file counts by extension, largest files) using this workspace's skills. Done = census-report.md exists at the workspace root." ;;
  t2-solo) exec claude -p --model sonnet --output-format json "Task: audit data/facts.md for factual errors and publish audit-report.md using this workspace's skills." ;;
  *) echo "unknown mode: $mode" >&2; exit 2 ;;
esac
