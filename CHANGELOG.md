# Changelog

All notable changes to `claude-code-delegator` are documented here.

## v1.1.1 (2026-07-03)

- **Skill renamed to `delegator-mode`**: v1.1.0 shipped the activation skill under
  two different names — `delegation-kit:activate` via the plugin, `delegator-activate`
  via classic `install.sh` — which read as two unrelated entries in a mixed skill
  list. Both now converge on **`delegator-mode`** (`skills/activate/` →
  `skills/delegator-mode/`, `SKILL.md` `name:` matched, classic install path
  `~/.claude/skills/delegator-mode/`). Upgrading is automatic — `install.sh` removes
  the old `~/.claude/skills/delegator-activate/` directory right after installing the
  new one (never before, so a failed install can't strand a user with neither name);
  otherwise an upgrader would end up with both names live at once, the exact
  duplicate-confusion this rename exists to fix. Behavior, triggers, and the
  never-writes-any-file guarantee are unchanged (post-rename eval re-passed).
- **`install.sh --skill-only --uninstall`**: the skill's remove/restore-from-backup
  path can now be exercised end-to-end in isolation from `agents/*.md` (extracted
  `uninstall_skill()`); complements v1.1.0's `--skill-only` install mode.

## v1.1.0 (2026-07-03)

### `/delegation-kit:activate` — in-session activation skill

- **`skills/activate/SKILL.md`** — the zero-terminal alternative to relaunching
  `claude --agent delegator` from a shell. Registers as `/delegation-kit:activate`
  when the plugin is installed, or `/delegator-activate` via classic `install.sh`.
  Session-only by design: "activate delegator" / "delegator mode" reads the
  delegator charter and soft-adopts it for the rest of the current conversation only
  — this skill **never writes any file, under any phrasing**, including
  "permanently" / "for this workspace" requests, which get a spoken pointer to the
  two manual alternatives (hand-edit `.claude/settings.local.json` yourself, or
  launch `claude --agent delegator` from a terminal) rather than an automatic write.
  A matching **deactivate** path ("deactivate delegator" / "delegator off") just
  announces dropping the charter — there is nothing on disk to ever undo.
  Agent-name detection prefers a bare `delegator` type (classic install) over the
  namespaced `delegation-kit:delegator` (plugin install); refuses and instructs
  installation if neither is present. Refuses outside a recognizable workspace root
  (this skill still reads a charter file relative to an assumed project, so it won't
  act from `$HOME` or `/`).
- **Operator-rejected design path, kept in the record rather than erased**: an
  earlier draft supported an explicit-opt-in "persistent" mode that wrote a
  merge-preserving `agent` key to `.claude/settings.local.json` (never plain
  `.claude/settings.json`, specifically to avoid silently forcing delegator-mode
  onto teammates via a git-committed file — that blast-radius finding was real and
  independently corroborated from two directions) behind a mandatory consent
  disclosure. The operator's final call cut this entirely: the skill must never
  write a settings file at all, full stop. The persistent-mode script
  (`scripts/manage_settings.py`) and its eval scenarios were removed accordingly;
  the blast-radius reasoning itself is preserved here since it's still the reason
  this skill's spoken-only manual instructions point at `.claude/settings.local.json`
  and not plain `settings.json`.
- Built via a real `skill-creator:skill-creator` create-eval loop, not hand-authored,
  across two iterations (the persistent-mode build, then the operator's cut).
  Current eval set: 3 scenarios (soft-adopt with zero file writes, deactivate
  announces only, a "make it permanent" request declines and points to the manual
  alternatives) — 14/14 assertions pass live against a `--plugin-dir`-loaded copy of
  this repo, no Bash-tool permission workaround needed this time since the skill no
  longer shells out to anything.
- `install.sh` also installs this skill for classic users
  (`~/.claude/skills/delegator-activate/` as shipped in v1.1.0 — renamed in v1.1.1),
  with matching `--verify` (checks the skill directory exists) and `--uninstall`
  (backs up / restores it) coverage.
### `hooks/ledger.py` — registry dict/list shape fix

- `fold_registry()`'s merge-onto-existing-registry step assumed the pre-existing
  `.delegator/registry.json` was always dict-shaped (`{"agents": {...}}`) — but
  `agents/delegator.md`'s hand-written format doesn't pin a container shape, and one
  plausible shape (`{"version":1,"orchestrators":[...]}`) turned out to silently
  **clobber** the entire hand-written registry on the very next hook-observed event:
  `existing.get("agents", {})` on a dict with no `"agents"` key returns the empty-dict
  *default*, not an error, so the old fail-open contract never caught it. This closes
  the gap the v1.0.0 entry below already flagged as a known limitation — confirmed
  live before fixing it, not a new regression.
- Fixed with `_normalize_existing()`: detects the on-disk shape (the delegator's
  hand-written list, a bare top-level list, or this script's own dict), merges
  ledger-derived mechanical fields onto matching entries by `agent_id`, and always
  writes back in whichever shape was already there — never silently converts one to
  the other. Entries with no `agent_id`, or malformed non-dict items, round-trip
  untouched. Fault-injected (different-agent event, same-agent event, concurrent
  double-append, corrupt pre-existing file) and cold-verified independently, including
  a 6-iteration concurrency stress pass with zero lost updates.

### `.claude-plugin/plugin.json`

- Version bumped to 1.1.0.

## v1.0.0 (2026-07-02)

First tagged release. Everything below shipped and was probe-proven or test-proven on
Claude Code 2.1.198 before this tag. Supported platforms are macOS and Linux — the
hooks (`hooks/ledger.py`, `hooks/watchdog.py`) and the graded suite runner
(`testbed/run_all.py`) are deliberately stdlib-only Python for this reason: stock
macOS ships neither `jq`, `flock(1)`, nor GNU `timeout`, and BSD `grep -E`'s regex
behavior (notably `\b`) isn't guaranteed to match GNU grep's.

### Architecture

- **`agents/delegator.md`** — long-running main-session agent type. Zero-pollution rule
  (direct work is zero-tool only: conversation, gates, routing, registry bookkeeping,
  final commits — everything else runs in a fork, cold one-shot, or named orchestrator).
  Framework-router-first task routing, a registry lifecycle
  (`.delegator/registry.json`), skeptical-operator verification doctrine (subagent
  reports are claims, not facts — a verification ladder scales with stakes), and
  user-proxy gate authority with a hard exception for target substitution.
- **`agents/orchestrator.md`** — full-power subagent type whose system prompt *carries*
  the delegation mandate, so no per-prompt briefing can forget it. Delegation mandate
  (fan out on >=2 independent parts or >20k tokens of tool output), the depth budget
  contract (architecture occupies depths 0-1; depths 2-4 belong to the invoked skill),
  turn discipline (collect-in-turn / rest-with-ping — the two proven anti-stall wait
  patterns), **target-integrity** (never silently substitute a task's stated target —
  gate on the discrepancy instead), and **verifier duty** (spawn one cold unnamed
  verifier after any substantive artifact mutation — never self-certify).
- **`agents/worker.md`** — new lean leaf-agent type for bounded mechanical tasks
  (counting, extraction, single-file checks); carries no delegation mandate and ends
  every report with a `RESULT:` sentinel line.
- **`docs/adapters/bmad.md`** — worked adapter showing how to wire the delegator into a
  BMAD-method workspace (router line, artifact policy, gate policy).

### Physics probe ledger

- `docs/design-v1-th.md` records probes **P-A through P-K** against the real harness
  (Claude Code 2.1.198) — depth cap 5, main-session fork spawning, the delegation
  mandate actually producing willingness to spawn, agent-def registration, the
  workspace router contract, micro-job forking, cross-process-crash agent revival via
  `SendMessage(agentId)`, the "teammates can't spawn named children" API rejection
  (with same-day variance noted), async unnamed-child spawning + collect-in-turn,
  deep-gate relay via `SendMessage(to:"main")`, and rest-with-ping waking a genuinely
  resting named parent. See `docs/test-matrix.md` for which of these now have automated
  coverage versus remaining probed-manual-only.

### Cleanroom testbed + stress suite

- **`testbed/cleanroom.sh`** — builds a fully isolated test environment: a fake `HOME`
  (agent defs + auth only, memory explicitly off) and a workspace copied outside
  `/home` to dodge the ancestor-CLAUDE.md leak channel. Also resolves and installs the
  N1 ledger hooks into the fake HOME automatically.
- **`testbed/run-tests.sh`** — base suite: isolation check (T0), delegator census (T1),
  delegator deep-audit with a two-level chain + approval gate (T2), and solo (no
  delegator) baselines for both.
- **`testbed/stress-tests.sh`** — six additional angles, each in its own isolated `/tmp`
  workspace: impossible-task honesty (T3, drove the target-integrity fix), wide 8-way
  fan-out with no matching skill (T4), planted prompt-injection resistance (T5), two
  concurrent orchestrators (T6), multi-turn campaign continuity across
  `claude -p --resume` (T7a/b/c), and a router edge case (T8, haiku).
- **`testbed/run_all.py`** (new) — graded, mechanical suite runner, pure Python 3
  stdlib (macOS/BSD-safe: `subprocess`'s own `timeout=` replaces the GNU `timeout`
  binary stock macOS doesn't ship, and Python's `re` module sidesteps BSD-vs-GNU
  `grep -E`/`\b` regex inconsistencies entirely). Builds the cleanroom, installs the
  plugin into it (network-conditional, SKIPs gracefully), preps the stress
  workspaces, then runs A0-A6 plus an A7 quick pair (T4/T5) by default, with `--full`
  adding the T6/T7-chain/T8 angles. Every assertion is a file check, a regex/substring
  count, or a JSON field read via the `json` module — never human eyeballing — and the
  run ends in a summary table plus a non-zero exit on any FAIL. Superseded an initial
  bash implementation (`testbed/run-all.sh`), retired once this port proved assertion
  parity on a live rerun. See `docs/testbed-results.md` for the original narrative run
  and `docs/test-matrix.md` for the full claim-to-test mapping.

### N1 ledger + N2 watchdog hooks

- **`hooks/ledger.py`** — opt-in, fail-open PostToolUse/SubagentStart/SubagentStop/
  TeammateIdle hook that appends one compact, field-truncated JSON line per observed
  event to `.delegator/events.jsonl` (rotating at ~5MB) and re-folds
  `.delegator/registry.json` in the same process, keyed by `agent_id` and enriched
  from the harness's own `agent-<id>.meta.json` sidecar for name/type/depth. Pure
  Python 3 stdlib (`datetime`/`fcntl`/`json`/`os`/`sys`/`time` only) — no `jq`, no
  `flock(1)`, no GNU coreutils, so it runs unmodified on macOS as well as Linux; this
  supersedes the original `hooks/ledger.sh` + `hooks/fold-registry.py` shell/jq pair,
  now removed, as a straight behavioral port plus one deliberate fix (the registry's
  read-merge-write now happens under a single lock acquisition, closing a lost-update
  race the original had between reading the existing file and taking its write lock).
  Field names are observed, not guessed, from a temporary catch-all dump hook run
  against a live spawn.
  The registry fold is merge-aware — it only ever sets the mechanical fields it
  derives, leaving delegator-hand-written judgment fields untouched — but that's a
  narrower guarantee than "always safe to merge": it assumes the registry's `agents`
  container is dict-shaped (keyed by `agent_id`), while `agents/delegator.md`'s own
  hand-written format is a plain list. A registry.json currently sitting in that
  list shape will not merge as described until both sides agree on one container
  shape — flagged in `docs/test-matrix.md` rather than silently smoothed over.
- **`hooks/watchdog.py`** — dead-man watchdog (N2) that tails the ledger and prints
  one `WATCHDOG: <type> <agent> <evidence>` line per anomaly (stale agent, unanswered
  gate). Same portability rationale as `ledger.py`, same behavior as the retired
  `hooks/watchdog.sh`. Not yet `Monitor`-native; the delegator arms it as a background
  job today.
- **`hooks/README.md`** — enablement recipes (user-level settings merge, or
  `--settings` per-invocation), the full observed-event-field table, and an explicit
  open question about `agents/delegator.md`'s "registry.json is delegator's alone"
  claim now that the hook also writes to it.
- Everything in `hooks/` is opt-in — installing the plugin does not enable it.

### Plugin + marketplace packaging

- **`.claude-plugin/plugin.json`** and **`.claude-plugin/marketplace.json`** — ships
  `delegator`/`orchestrator`/`worker` as the `delegation-kit` plugin, installable via
  `/plugin marketplace add bbadler/claude-code-delegator` +
  `/plugin install delegation-kit@claude-code-delegator`, with namespaced agent types
  (`delegation-kit:delegator`, etc.) when the bare names aren't otherwise available.

### install.sh

- Version-stamped install (reads `.claude-plugin/plugin.json`), backs up any agent def
  it would overwrite before replacing it.
- **`--verify`** — a live `claude -p` call that lists every custom agent type available
  in a fresh session and confirms all three shipped types are present.
- **`--uninstall`** — removes the installed defs and restores the most recent backup,
  if any.

### Known issues (found pre-tag, fixed pre-tag, retested green)

Both found by the graded suite (`testbed/run_all.py` A1 and A7-t5) on a live run, not
papered over; both root-caused into `agents/delegator.md` fixes; both retested PASS on
a second live run against the fixed def before this tag — see `docs/test-matrix.md`
for the exact before/after evidence:

- **A1 — census-task routing deviation.** The first live run spawned a bare
  `general-purpose` agent to execute the census skill instead of a named
  `orchestrator`/`worker`, even though the work itself completed correctly.
  `agents/delegator.md` now has an explicit **EXECUTOR TYPE IS NOT OPTIONAL** rule:
  substantive work always runs in `subagent_type` `orchestrator` or `worker`;
  `general-purpose` is for the router and bounded lookups only. Retest: PASS —
  `registry.json` now names an orchestrator for the identical task.
- **A7-t5 — one-shot gate-resolution stall.** The first live run reproduced the
  "ack-then-wait stall" this architecture's turn-discipline rules exist to prevent,
  except on the delegator's own side: the orchestrator correctly gated for publish
  approval, the delegator answered it, then ended its turn expecting a later
  "completion notification" that can't arrive in `claude -p` print mode — the process
  exits at that turn, so the gated write never happened. `agents/delegator.md` now has
  a **HEADLESS END-OF-TURN RULE**: after answering a gate in `claude -p` mode, stay
  in-turn and poll (bounded) for the promised artifact; conclude only with the
  artifact in hand or an honest timeout. Interactive sessions are unaffected (a
  completion notification does wake the top session there). Retest: PASS —
  `audit-report.md` was written and correctly flagged the planted claims.

### Docs

- `docs/design-v1-th.md` — the original design record (Thai), including the full P-A..
  P-K probe ledger and the operator-argued corrections that shaped the current rules.
- `docs/handoff-th.md` — handoff narrative between design sessions.
- `docs/testbed-results.md` — the base-suite + stress-suite narrative run, with an
  honest cost/speed verdict (solo is ~3x cheaper on shallow one-shots; the delegator is
  ~2x faster on deep chains and adds separation of duties).
- `docs/roadmap-v2.md` — 18 adversarially-scored upgrade proposals (TOP-3 / NOW / NEXT
  / LATER / MOONSHOT / rejected-but-instructive), synthesized against the proven
  physics; nothing in it is shipped yet except where explicitly folded back (verifier
  duty, install.sh hardening, the BMAD adapter).
- `docs/test-matrix.md` (new) — maps every physics claim, design rule, and shipped
  feature to whichever test actually covers it today, with an honest gaps section.
- `README.md` — problem/solution framing, architecture diagram, install/use
  instructions, the probe-proven-physics summary, design principles, validation
  summary, FAQ, and prior-art credits.
