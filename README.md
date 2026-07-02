# claude-delegator

Long-running delegation architecture for Claude Code: a main session that never grinds solo. It routes every substantive task to full-power **orchestrator** subagents, keeps a roster registry, answers their gates, and protects its own context window as the campaign's scarcest asset — so one session can run for days without drowning in tool output.

Built and probe-proven on Claude Code **v2.1.198** (2026-07-02). Every mechanical claim below was verified by a live probe on a real install, not docs.

## What's inside

| Path | What it is |
|---|---|
| `agents/delegator.md` | The switch — launch a whole session as the delegator: `claude --agent delegator` |
| `agents/orchestrator.md` | Registered agent type; the full delegation mandate rides in the TYPE's own system prompt, so briefs can't forget it |
| `docs/design-v1-th.md` | Full design rationale, critique verdicts, and the probe ledger P-A..P-J (Thai) |
| `docs/handoff-th.md` | Archival: the original handoff with operator prompts verbatim + probes 1–5 (Thai) |
| `install.sh` | Copies the agent defs into `~/.claude/agents/` (backs up anything it would overwrite) |

## Install & use

```bash
./install.sh
cd <your-workspace>
claude --agent delegator        # the whole session becomes a delegator
```

Or from any normal session, spawn a single orchestrator:

```
Agent({subagent_type: "orchestrator", name: "toonflow-lead", prompt: "You are toonflow-lead. <task> ..."})
```

This repo is the source of truth — edit here, re-run `install.sh` to deploy. Agent defs hot-register into running sessions as well as new ones.

## Probe-proven physics (the rules everything is built on)

- **Depth cap = 5** below the top session; level 5 silently loses the Agent tool. Every level gets a fresh per-agent token budget.
- **Teammates cannot spawn NAMED children** — rejected at the API: `Teammates cannot spawn other teammates — the team roster is flat.` (One same-day probe succeeded → variance is real; design on the blocked side.)
- **A teammate's unnamed children launch ASYNC**, not blocking → **collect-in-turn**: launch all independent children, keep working, poll each child's `output_file` with a narrow sentinel grep. **Never end a turn with children outstanding** — completion notifications reach ONLY the top session; a resting teammate is never woken by them.
- **Deep gates work**: a depth-2 agent's `SendMessage(to:"main")` delivers to the top session, and the answer sent to its `agentId` revives it to finish (P-J).
- **Rest-with-ping**: an explicit child→parent `SendMessage(to:"<parent-name>")` DOES wake a rested named parent (P-K) — bare completions never do. Second wait pattern for long-running children; orphan risk covered by the delegator's watchdog nudge.
- **Agents survive process exits**: `SendMessage(agentId)` revives a rested/orphaned agent from its on-disk transcript — even after the spawning process died and the session resumed under a new session id, with full context retained.
- **fork → fork ✗**; named → self-fork ✓; main (model-initiated) → fork ✓ with fresh budget and full context inheritance.
- **Named agents don't know their own name** — every brief opens with "You are <name>".

## Design principles

1. **Zero-pollution delegator** — the delegator does directly only zero-tool work (conversation, gates, routing, registry bookkeeping, final commits). ALL other tool work runs outside its window: self-**fork** for micro/context-bound jobs (a fork inherits everything — one-line brief, absorbs raw output, costs ~a cached context read), cold one-shot for context-free lookups, orchestrator for substantive work. Bonus: work inside agents survives a main-process crash; inline work dies with the turn.
2. **Mandate in the type, not the brief** — `orchestrator.md` carries "delegate by default / invoke skills for real / act every turn", so the disease of subagents grinding solo is fixed at the system-prompt layer.
3. **Collect-in-turn** (see physics above) — the one hard anti-stall rule.
4. **Depth budget contract** — the architecture occupies depths 0–1 only (delegator, orchestrator); **depths 2–4 belong to the skill** being invoked, which may legitimately spawn its own internal layers.
5. **Continuous handoff** — every orchestrator report ends with a state snapshot appended to `.delegator/handoffs/<name>.md`; crash/retire/staleness recovery is always one seed away. Revival order: `SendMessage(agentId)` first, handoff file as fallback.
6. **Framework routing** — a workspace declares `Router skill: /<name>` in its CLAUDE.md (e.g. `/bmad-help`); the delegator routes each new task through a fresh router agent that returns `{skill, args, why, confidence}`, then the orchestrator invokes that skill for real.
7. **Registry** — `.delegator/registry.json` per workspace, delegator is the single writer: roster + revival info (`agent_id`, `session_id`, `handoff_file`, `staleness_flags`).

## Testbed (self-contained proof)

`testbed/` is a mini skill framework — a router skill (`/advisor`, the bmad-help analogue) plus work skills that MANDATE nested subagent spawning (`/census`: parallel fan-out; `/deep-audit`: two-level chain + approval gate) over a dataset with known ground truth. `testbed/cleanroom.sh` builds a fully isolated environment (fake HOME + workspace outside /home — zero personal config), and `testbed/run-tests.sh` drives headless `claude -p --agent delegator` runs plus solo baselines. Full results: `docs/testbed-results.md` — all runs 100% correct; solo is ~3× cheaper on shallow one-shots, the delegator is ~2× faster on deep chains and adds separation of duties (the gate approver is not the producer); the architecture's core value (clean context across a days-long campaign) accrues beyond what one-shots measure.

## Status

Canary-proven end-to-end: probe ledger P-A..P-K in `docs/design-v1-th.md` + headless cleanroom validation in `docs/testbed-results.md` (router → orchestrator → nested skill chains → gate, all correct against ground truth). Pending: first live production campaign, context-hub router wiring, cross-lineage addressing probe, registry-persistence compliance in live runs.
