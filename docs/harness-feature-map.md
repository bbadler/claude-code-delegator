# Harness feature map — agent teams / subagents / hooks (v2.1.19x sweep, 2026-07-03)

Full research sweep of documented capabilities vs what delegation-kit uses. Compiled from
official docs (agent-teams.md, hooks.md, changelog 2.1.140→2.1.199). Items marked PROBE
are load-bearing claims we have not yet verified live — per repo rule, probe before building on them.

## Game-changers for this kit (priority order)

1. **Stop hook force-continue** — `decision: "block"` + `hookSpecificOutput.additionalContext`
   on the **Stop** event BLOCKS the turn from ending and injects feedback; the model keeps
   working (v2.1.186; documented, NOT an error label). → BUSY-PRESENCE ENFORCED MECHANICALLY:
   a campaign-aware Stop gate can refuse to let the delegator end its turn while registry rows
   have `owes: true`. Payload includes `background_tasks` (v2.1.145) for liveness cross-check. **PROBE**
2. **SubagentStop block+context** — same semantics on SubagentStop: block the SUBAGENT's stop,
   feed context back to THE SUBAGENT so it continues. Reconciles our earlier probe: additionalContext
   on SubagentStop does not inject into the MAIN session (3× confirmed) — the documented target is
   the stopping subagent itself, with `decision:"block"`. → ack-then-wait killer for subagents. **PROBE**
3. **SubagentStart additionalContext injection** — inject campaign context into every spawned
   agent at birth (campaign id, storage root, mode, spec pointer, owes contract) — mechanical,
   no brief discipline needed. **PROBE**
4. **TeammateIdle exit-2 blocking** (no additionalContext) — idle-gate (already queued). **PROBE**
5. **`CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS`** (default 600000) — real tunable for background-agent
   stall timeout. Document in hooks/README; long-render campaigns may raise it.
6. **SessionStart hook** — additionalContext + `reloadSkills` + sessionTitle; source: startup|resume|clear|compact.
   → CAMPAIGN AUTO-RESTORE: on resume, inject "active campaign <id>, registry at <path>, open owes: [...]".
7. **Task board long tail** — claiming uses real file locks; `addBlocks/addBlockedBy` auto-unblock
   dependents; TaskCreate input auto-repair (v2.1.186). → board can carry pipeline dependencies.
8. **Teammate plan-approval** — spawn with mode:plan; lead approves/rejects plans autonomously;
   teammate resubmits on rejection. → harness-level review gate for risky work.
9. **Resilience physics (v2.1.199)**: subagents cut off by rate limit/server error return PARTIAL
   work to the parent; API errors now report as FAILURES (not silent success). Update charter
   assumptions about silent death.
10. **No background subagents from in-process teammates** (documented limitation) + **no nested
    teams** (hard) — matches our probes; cite docs not just probes.

## Corrections to our prior beliefs

- "SubagentStop can't inject" → true only toward the MAIN session; with decision:block it feeds
  the stopping subagent (docs v2.1.186). Watchdog stays on PostToolUse/UserPromptSubmit for
  delegator-facing alerts.
- Native "delegate mode" exists as a UI restriction (Shift+Tab): lead limited to coordination-only
  tools. Adjacent to, not a replacement for, the delegator charter.
- Teammates inherit lead's effort (v2.1.186, tmux/split backends).
- Hook matchers: hyphenated identifiers exact-match since v2.1.195 (regex needs explicit syntax).

## Full hook-event matrix (from docs; blocking = exit 2 or decision field)

Blocking + context-capable: PreToolUse, UserPromptSubmit, UserPromptExpansion, Stop, PostToolBatch.
Blocking, no context: PermissionRequest, TeammateIdle, TaskCreated, TaskCompleted, ConfigChange,
PreCompact, WorktreeCreate, Elicitation(+Result).
Info-only with context: SessionStart, SubagentStart, PostToolUseFailure.
Info-only: PostToolUse*, PermissionDenied, StopFailure, Notification (agent_needs_input|agent_completed),
MessageDisplay (display transform), CwdChanged, FileChanged, InstructionsLoaded, SessionEnd,
WorktreeRemove, PostCompact, Setup, StopFailure.
(*PostToolUse additionalContext injection observed working live on this install — see CHANGELOG v1.3.0.)

Common payload: session_id, prompt_id, transcript_path, cwd, permission_mode, effort, hook_event_name,
agent_id + agent_type in subagent context. Stop/SubagentStop add background_tasks, session_crons.

## Tools we hold but haven't wired into the architecture

- **Monitor** (persistent event streams; stdout lines → notifications while the session keeps working)
  → live campaign feed: `tail -f <campaign>/events.jsonl` armed once by the delegator.
- **PushNotification** → human-boundary alerts to the operator's desktop/phone (DEFERRED items,
  campaign completion, failures) in autonomous mode.
- **Agent(run_in_background:false)** sync spawns; **mode:"plan"** teammates; **isolation:"remote"** cloud runs.
- **CronCreate** (session-only cron), **RemoteTrigger** (claude.ai cloud routines).

## Trigger-happy env vars (documented only)

CLAUDE_ASYNC_AGENT_STALL_TIMEOUT_MS · CLAUDE_ENABLE_STREAM_WATCHDOG (default on; 5-min stream
idle abort/retry) · CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP · CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS.
(330+ vars exist in the bundle; use documented ones only.)
