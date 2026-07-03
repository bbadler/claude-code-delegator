# Architecture v2 — native-first realignment (2026-07-03)

Every concern mapped to the RIGHT harness mechanism (per docs/harness-feature-map.md).
Invented workarounds survive only where nothing native exists. Status: ✅ shipped ·
🔨 in flight (GATES task, probes P1-P4) · 📋 this wave · charter = judgment layer.

## Layer 1 — Enforcement (hooks: mechanical, zero model discipline)

| Concern | Mechanism | Status |
|---|---|---|
| Delegator must not end turn while children owe | **stop_gate.py** — Stop `decision:block` + additionalContext (lists owing agents) | 🔨 P2 |
| Teammates must not idle while owing | **idle_gate.py** — TeammateIdle exit 2 + stderr coaching | 🔨 P1 |
| Subagent ack-then-wait death | SubagentStop block+context → feeds the stopping subagent | 🔨 P3 |
| Campaign context at agent birth | SubagentStart additionalContext injection | 🔨 P4 |
| Stall detection (named agents) | watchdog.py — STALE_AGENT via PostToolUse/UserPromptSubmit injection | ✅ v1.3.0 |
| Event ledger → derived registry | ledger.py, per-session campaign dirs, 4-shape tolerant + no-write guard | ✅ v1.2.0 |
| Campaign auto-restore on resume | SessionStart hook: inject active campaign + owing roster; reloadSkills | 📋 after GATES |
| Long-op tolerance | soft_timeout_minutes per agent + CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS documented | ✅/📋 docs |

## Layer 2 — Coordination (native tools over inventions)

| Concern | Mechanism | Status |
|---|---|---|
| Spec channel + amendments | Task board: description prose + **metadata {spec_version, spec_file}**; TaskUpdate + nudge; files only for oversized/multi-session | ✅ |
| Pipeline dependencies | TaskUpdate **addBlocks/addBlockedBy** — harness auto-unblocks dependents | 📋 charter |
| Breaking amendments | **TaskStop(name) → SendMessage revival** (proven live; board carries spec through the kill) | ✅ |
| Live campaign feed | **Monitor**(tail -f campaign events.jsonl, persistent) armed at campaign start | 📋 charter |
| Human boundary (autonomous) | **PushNotification** — DEFERRED gates, completion, stall escalation | 📋 charter |
| Mode intake + human gates | **AskUserQuestion** (main-only; subagent-blocked probed) | ✅ v1.2.1 |
| Sync leaf collection | Agent **run_in_background:false** / TaskOutput(block) for need-result-now spawns | 📋 charter |
| Bulk deterministic fan-out | **Workflow** engine (schema'd agent() leaves, budgets, resume-from-journal) as a phase tool | 📋 charter |
| Risky work review | Agent **mode:"plan"** — teammate must submit a plan; delegator approves | 📋 charter |
| Isolation | isolation:worktree per spawn; EnterWorktree for session-level lanes | ✅ documented |
| Cloud/scale | isolation:remote, RemoteTrigger routines | future |

## Layer 3 — Judgment (charter: what hooks cannot decide)

Routing + briefs + skeptical-operator ladder + ask-don't-interpret + fork escalation +
research-first + quality bar (lazy resolutions forbidden) + growth-liveness (time never
kills work) + mode policy + user-proxy gate answering + platform-inventory-before-design.
Charter prose THINS where a hook now enforces mechanically: the rule stays as the WHY,
the hook is the HOW.

## Migration notes

- v1.4.0 = GATES (stop/idle) + charter coordination wave + this doc. Full alignment
  release may be badged v2.0.0.
- Charter-polling busy-presence loop becomes the FALLBACK for hook-less installs
  (classic install.sh without the manual hook merge) — documented, not deleted.
- Every 🔨 item ships only with its probe evidence attached (docs lied to us twice today).
