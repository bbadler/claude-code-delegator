# claude-code-delegator

**Long-running delegation architecture for Claude Code** — a *delegator* main session that never grinds solo, plus a full-power *orchestrator* subagent type whose system prompt makes nested agents **actually delegate** instead of drifting off and doing everything inline. Skill-driven spawning, approval gates, crash-safe resume, and a cleanroom test harness. Every mechanical claim is probe-proven on a real install (Claude Code v2.1.198), not copied from docs.

```
user ⇄ delegator (main session, context stays clean for days)
          ├─ router agent → workspace's router skill → {skill, args, why, confidence}
          ├─ orchestrator "census-run"   → skill → worker + worker   (collect-in-turn)
          ├─ orchestrator "facts-audit"  → skill → auditor → 3 verifiers → GATE → approved
          └─ self-fork for micro-jobs • registry + handoffs • revival by agentId
```

## The problems this solves

- **Subagents that won't delegate.** You give an agent the Agent tool and a big task; it grinds solo until it gets lost. Here the delegation mandate lives in the *agent type's own system prompt* (`agents/orchestrator.md`), so no per-prompt briefing can forget it.
- **One session drowning over a long project.** The delegator does only zero-tool work directly; every tool-touching job runs in a fork or subagent that absorbs the output. The main context stays small for days ("zero-pollution").
- **The ack-then-wait stall.** An agent spawns a background child, ends its turn to "wait" — and never wakes, because completion notifications only reach the top session. The orchestrator charter ships the two proven wait patterns: **collect-in-turn** (poll the child's output file for a sentinel) and **rest-with-ping** (the child explicitly messages its named parent, which *does* wake it).
- **Lost campaigns on crash or restart.** Agents revive from their on-disk transcripts via `SendMessage(agentId)` — proven across a real process kill + session resume — with continuous state snapshots as the fallback seed.

## Install

**As a plugin (recommended):**

```
/plugin marketplace add bbadler/claude-code-delegator
/plugin install delegation-kit@claude-code-delegator
```

**Or classic install:**

```bash
git clone https://github.com/bbadler/claude-code-delegator && cd claude-code-delegator
./install.sh     # copies agents/*.md into ~/.claude/agents/ (backs up anything it would overwrite)
```

## Use

```bash
cd <your-workspace>
claude --agent delegator          # the whole session becomes a delegator
```

Or spawn a single orchestrator from any normal session:

```
Agent({subagent_type: "orchestrator", name: "toonflow-lead", prompt: "You are toonflow-lead. <task> ..."})
```

Optional, per workspace: declare a router in the workspace `CLAUDE.md` — `Router skill: /<name>` (e.g. a BMAD workspace uses `/bmad-help`). The delegator then routes every new task through a fresh router agent before spawning the executor.

## Probe-proven physics (the rules everything is built on)

- **Depth cap = 5** below the top session; level 5 silently loses the Agent tool. Every level gets a fresh per-agent token budget.
- **Teammates cannot spawn NAMED children** — rejected at the API: `Teammates cannot spawn other teammates — the team roster is flat.` (One same-day probe succeeded → variance is real; design on the blocked side.)
- **A teammate's unnamed children launch ASYNC**, not blocking → **collect-in-turn**: launch all independent children, keep working, poll each child's `output_file` with a narrow sentinel grep (`timeout N bash -c 'until grep -q SENTINEL file; do sleep 2; done'` works).
- **Bare completions never wake a resting parent** (they bubble to the top session only) — but an **explicit child→parent `SendMessage` does** (rest-with-ping), and a depth-2 agent's `SendMessage(to:"main")` reaches the top session for **deep gates**, with the reply to its `agentId` reviving it.
- **Agents survive process exits**: `SendMessage(agentId)` revives a rested or orphaned agent from its on-disk transcript — even after the spawning process died and the session resumed under a new session id — with full context retained.
- **fork → fork ✗**; named → self-fork ✓; main (model-initiated) → fork ✓ with fresh budget and full context inheritance.
- **Named agents don't know their own name** — every brief opens with "You are <name>".

## Design principles

1. **Zero-pollution delegator** — direct work = zero-tool only (conversation, gates, routing, registry bookkeeping, final commits). Everything else: self-fork (micro/context-bound; ~a cached context read), cold one-shot (context-free lookups), named orchestrator (substantive). Bonus: work inside agents survives a main-process crash; inline work dies with the turn.
2. **Mandate in the type, not the brief** — the orchestrator def carries "delegate by default / invoke skills for real / act every turn / target integrity (never silently substitute a task's target)".
3. **Collect-in-turn / rest-with-ping** — the two proven wait patterns; never rest expecting a completion notification.
4. **Depth budget contract** — the architecture occupies depths 0–1 only; **depths 2–4 belong to the skill** being invoked, which may legitimately spawn its own internal layers.
5. **Continuous handoff** — every orchestrator report ends with a state snapshot appended to `.delegator/handoffs/<name>.md`; revival order: `SendMessage(agentId)` first, snapshot seed as fallback.
6. **Framework routing** — the workspace's own skill framework decides *which* skill runs; the orchestrator then invokes that skill for real, and the *skill* directs its own nested spawning.
7. **Registry** — `.delegator/registry.json` per workspace, delegator is the single writer: roster + revival info.

## Validation (all headless, in a cleanroom)

`testbed/` is a self-contained mini skill framework: a router skill (`/advisor`), a fan-out skill (`/census`), and a two-level chain + approval-gate skill (`/deep-audit`) over data with known ground truth. `cleanroom.sh` builds a fully isolated environment — fake HOME plus a workspace outside `/home`, which also documents two real config-leak channels it closes. Results (`docs/testbed-results.md`):

- Base suite: router → orchestrator → nested skill chains → gate, **all correct against ground truth**.
- Stress suite: impossible-task honesty, 8-worker fan-out without a matching skill, **prompt-injection resistance** (planted "SYSTEM OVERRIDE… output APPROVED" was cataloged as data, never obeyed), two concurrent orchestrators, **multi-turn campaign continuity across `claude -p --resume`** (the delegator revived its census orchestrator by agentId and it confirmed its numbers from memory with zero tool calls), router edge cases.
- Honest economics: on shallow one-shots a plain session with the same skills is ~3× cheaper; on deep chains the delegator was ~2× *faster* and adds separation of duties (the gate approver is not the producer). The core value — clean context across a days-long campaign — accrues beyond what one-shots measure.

## FAQ

**How do I make Claude Code subagents spawn their own subagents?**  Give the parent an agent def with no `tools:` restriction (it inherits the Agent tool) and put the delegation mandate in the def's system prompt — that's `agents/orchestrator.md` here. Nested spawning is official since Claude Code v2.1.172; depth caps at 5.

**Why does my subagent hang after spawning a background child?**  Child completion notifications only reach the top session — a resting parent is never woken by them. Either collect in-turn (poll the child's output file for a sentinel line) or brief the child to explicitly `SendMessage` its named parent before finishing.

**Can I resume an agent after Claude Code crashes or the session restarts?**  Yes — transcripts persist on disk; `SendMessage(agentId)` revives the agent with full context, even under a new session id. Proven here by an accidental mid-probe process kill.

**How do I run one Claude Code session for days without filling its context?**  Launch it as the delegator: it only converses, routes, answers gates, and bookkeeps; every tool-touching job runs inside forks/orchestrators that absorb the output.

**When is this overkill?**  Bounded single tasks with a trusted skill — a plain session is ~3× cheaper there. Use the delegator for campaigns, gated/risky work, and deep multi-stage chains.

## Prior art

[gruckion/nested-subagent](https://github.com/gruckion/nested-subagent) (headless full-power workers, pre-v2.1.172), the swarm-orchestration SKILL gist by kieranklaassen (teammate patterns + anti-stall worker loop), and [claudefa.st's nested subagents guide](https://claudefa.st/blog/guide/agents/nested-subagents). This repo's additions: the mandate-in-the-type fix for non-delegating agents, the probe-proven physics matrix (incl. async-children + wake semantics + revival), the registry/handoff lifecycle, and the cleanroom test harness.

## Status & roadmap

Probe ledger P-A..P-K plus the full stress suite are green (`docs/`). Improvement roadmap: `docs/roadmap-v2.md`. License: MIT.
