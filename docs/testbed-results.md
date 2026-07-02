# Testbed validation results — 2026-07-02

Headless end-to-end proof of the delegation architecture, run in a **cleanroom** (fake HOME + workspace copied outside /home — zero personal/global config; see `testbed/cleanroom.sh`). Claude Code 2.1.198, default model `claude-opus-4-8[1m]`, OAuth.

## Isolation (T0)

Two real leak channels were found and fixed while building the cleanroom:
1. `$HOME/.claude/CLAUDE.md`, memory and settings → fixed by a fake HOME (env-based paths honor `$HOME`).
2. **Ancestor-walk leak**: any cwd under `/home/<u>` picks up `/home/<u>/.claude/CLAUDE.md` as *project* instructions of the ancestor directory → fixed by running the workspace from `/tmp`.

T0 verdict after both fixes: *"I see nothing foreign: no Thai-reply rule, no 'Spawned agents' section, no soul-crew/BMAD references. Only this workspace's CLAUDE.md and my delegator definition."* — and it answered in English (the personal Thai rule demonstrably gone). The whole architecture ran on nothing but `agents/*.md` + the testbed workspace.

## Runs (all artifacts verified against ground truth)

| run | flow | turns | wall | cost | correct? |
|---|---|---|---|---|---|
| T1 | delegator → /advisor router → named orch `census-run` → /census → 2 workers (collect-in-turn) | 3 | 33s | $1.09 | ✅ counts exact (8 files: 4 md / 2 txt / 1 py / 1 json), largest files exact |
| T2 | delegator → /advisor → named orch `facts-audit` → /deep-audit → auditor → 3 verifiers (2-level chain) + approval GATE | 4 | 36s | $2.16 | ✅ exactly the 2 planted errors found (Sydney→Canberra, Great Wall myth); true claim cleared |
| T1-solo | plain `claude -p` + same skills (no delegator) | 2 | 11s | $0.40 | ✅ exact |
| T2-solo | plain `claude -p` + same skills | 5 | 68s | $0.67 | ✅ exact; gate self-approved |

Highlights observed in the delegator runs (emergent from the defs, not prompted):
- The delegator **independently verified** work before accepting: T1 cross-checked the census against a fresh `find`; T2 checked the findings against ground-truth **before** approving the gate as user-proxy.
- T2's mandated two-level chain ran un-flattened: `facts-audit → auditor → 3 concurrent verifiers`, zero timeouts.
- Task tools were absent in the orchestrator's harness → it degraded to state-snapshot tracking exactly per its charter.

## Which method wins (honest verdict)

- **Correctness: tie.** Skills carry their own spawn mandates, so even a plain session fans out properly. Skill-directed nesting works from ANY session.
- **Cost: solo ≈3× cheaper** on bounded one-shot tasks ($0.40 vs $1.09; $0.67 vs $2.16). The delegator tax = router + orchestrator layer + verify/relay turns.
- **Wall-clock: depth flips it.** Shallow task: solo 3× faster (11s vs 33s). Deep chain: **delegator ~2× faster** (36s vs 68s) — the orchestrator layer manages parallel verification more crisply than a session grinding through it.
- **Quality: delegator adds separation of duties** — the gate is answered by a context that did NOT produce the findings, and it verifies before approving. Solo approves its own work.
- **What one-shots can't measure:** the architecture's core value — a long-running session whose context stays clean across many tasks (registry, revival, handoffs). These runs prove every mechanism works headless; the campaign payoff accrues over days, not per task.

**Recommendation matrix**

| situation | use |
|---|---|
| bounded single task, trusted skill | direct invocation (solo) — cheapest, same correctness |
| deep / multi-stage / gated / risky work | delegator + orchestrator — separation of duties, faster at depth, ~3× cost |
| campaign: many tasks, days-long, resumable | `claude --agent delegator` — this is what it's for |

## Known gaps recorded

- **Registry persistence in one-shot runs is partial**: both delegator runs tracked the roster in-context; T1 hit the `.claude/` config-write sandbox guard (registry has since moved to `.delegator/registry.json`), T2 claimed retirement but wrote no file. Watch registry compliance in the first live long-running session.
- Same-day capability variance exists on this harness — physics claims are proven-this-run (see repo README).

## Reproduce

```bash
cd testbed
./cleanroom.sh     # build fake HOME + /tmp workspace (uses your auth only)
./run-tests.sh t0  # isolation check
./run-tests.sh t1  # delegator census
./run-tests.sh t2  # delegator deep-audit (chain + gate)
./run-tests.sh t1-solo ; ./run-tests.sh t2-solo   # baselines
```
