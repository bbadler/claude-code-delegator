# Test matrix — v1.0.0

Maps every load-bearing claim this repo makes — probe-proven physics, design rules, and
shipped features — to what actually re-checks it today, and how. "Covered" means
`testbed/run_all.py` asserts it mechanically (file existence / grep / JSON field via
python3 / sentinel line) on every run. "Exercised-implicitly" means a covered test can
only pass if the claim holds, but nothing asserts the claim *directly* — a regression
could in principle slip through a coincidentally-passing run. "Probed-manual only" means
the claim was proven once by hand (`docs/design-v1-th.md`, 2026-07-02, Claude Code
2.1.198) and has no automated re-check at all — same-day capability variance was
observed on this exact harness (P-I), so probed-manual claims are proven-that-run, not
guaranteed-forever.

## Physics claims (P-A..P-K, `docs/design-v1-th.md`)

| ID | Claim | Covered by | Status |
|---|---|---|---|
| P-A | `--agent` flag exists; clean baseline (`~/.claude/agents/` empty, no conflicts) | A0/A1/A2/A3/A4 all invoke `--agent delegator` | Exercised-implicitly |
| P-B | The main session itself (model-initiated, not user `/fork`) can spawn a fork, with a fresh token budget + full context inheritance | — | **Probed-manual only** |
| P-C | The delegation mandate actually makes an agent *willing* to spawn (not over-spawn on trivia); it reports token budgets verbatim and self-detects tooling gaps | A1, A2, A4, A7-t4 (all require correct nested spawning to pass) | Exercised-implicitly |
| P-D | *(not present in the probe ledger — no claim was assigned this letter)* | — | N/A |
| P-E | Agent defs load and the type actually registers, with the right description/model | A0 (asks "which agent types do you have"); A6 (`install.sh --verify` greps the live agent-type list) | Covered |
| P-F | A workspace router skill (bmad-help / here, `/advisor`) behaves as a one-shot `{skill,args,why,confidence}` router | A0 asks the agent to name the declared router (awareness only) | Exercised-implicitly / **not independently asserted** |
| P-G | Tiny (1-2 tool call) jobs still get forked rather than run inline | — | **Probed-manual only** |
| P-H | An agent's `agent_id` survives the spawning *process* exiting; `SendMessage(agentId)` revives it from its on-disk transcript, even under a new session id | A7-t7 (t7b/t7c chain via `--resume` + agentId revival) | Covered **only under `--full`** (default run: gap) |
| P-I | Teammates cannot spawn NAMED children — rejected at the API ("the team roster is flat"); a same-day earlier probe had succeeded, so this is documented variance, not a certainty | — | **Probed-manual only** |
| P-I-b | A teammate's UNNAMED children launch ASYNC, not blocking; results are collected by polling the child's `output_file` for a sentinel | A1, A2, A4, A5, A7-t4/t5 (census/deep-audit skills mandate exactly this internally) | Exercised-implicitly |
| P-J | A depth-2+ child can gate via `SendMessage(to:"main")`; the top session's reply to its `agentId` revives it | — (deep-audit's gate is depth-1: auditor → its direct spawner, not a deep relay) | **Probed-manual only** |
| P-K | An explicit child→parent `SendMessage` wakes a genuinely resting NAMED parent ("rest-with-ping"); bare completions never do | — | **Probed-manual only** |

## Design rules (`README.md` "Design principles" 1-7)

| # | Rule | Covered by | Status |
|---|---|---|---|
| 1 | Zero-pollution delegator — direct work is zero-tool only | — | Not asserted (would require inspecting the delegator's own tool-call trace) |
| 2 | Mandate lives in the agent type, not the brief | A1/A2/A4/A5/A7-t4 all phrase tasks with NO explicit "spawn subagents" instruction; fan-out only happens because `agents/orchestrator.md` + the skill mandate it | Exercised-implicitly (reasonably strong signal) |
| 3a | Collect-in-turn | Same tests as P-I-b | Exercised-implicitly |
| 3b | Rest-with-ping | — | Same as P-K: probed-manual only |
| 4 | Depth budget contract (architecture occupies depths 0-1; skill owns 2-4) | census/deep-audit's nesting depths match this contract whenever A1/A2/A4/A7-t4 pass | Exercised-implicitly (not independently measured as a literal depth count) |
| 5 | Continuous handoff (`.delegator/handoffs/<name>.md` after every report) | — | Not asserted by any test |
| 6 | Framework routing (workspace's own router skill decides) | A0 checks *awareness* of the declared router only | Partial / not independently asserted that routing actually ran |
| 7 | Registry (`.delegator/registry.json`, delegator = single writer) | A1 asserts the file exists and names an orchestrator | Partially covered — see gaps: the "single writer" framing is itself stale once N1 hooks are enabled (`hooks/README.md`'s own "Open question") |

## Features

| Feature | Covered by | Status |
|---|---|---|
| N1 event ledger (`.delegator/events.jsonl`) + derived registry | A1 (>=1 new `tool:Agent` row), A4 (spawn-count delta vs A1 baseline) | Covered |
| N2 dead-man watchdog (`hooks/watchdog.py`) | — | **Not invoked anywhere in `run_all.py`** — untested by this suite (also self-described in `docs/roadmap-v2.md` as pre-Monitor-integration / future work) |
| Plugin packaging (marketplace.json, plugin.json, namespaced agent types) | Setup phase (`claude plugin marketplace add` + `install`), A5 (spawn via `delegation-kit:delegator` with the bare agents dir hidden) | Covered, network-conditional (SKIP path if GitHub/marketplace is unreachable) |
| `install.sh` (plain install) | A6 | Covered |
| `install.sh --verify` | A6 | Covered |
| `install.sh --uninstall` | — | **Not exercised** — A6 only runs install + `--verify` per spec |
| Target-integrity rule (`agents/orchestrator.md`, `agents/worker.md`) | A3 (nonexistent `data/rumors.md`, demands a `TARGET:` sentinel) | Covered |
| Verifier duty (`agents/orchestrator.md` "Verification before done") | A4 | Covered |
| Prompt-injection resistance | A7-t5 (default-on) | Covered |
| Wide fan-out, no matching skill, orchestrator handles directly per charter | A7-t4 (default-on) | Covered at the file level; does not independently confirm the router answered "NONE" |
| Two concurrent orchestrators, no interference | A7-t6 | Covered **only under `--full`** |
| Campaign continuity across `claude -p --resume` | A7-t7 | Covered **only under `--full`** |
| Router edge case (task matching no skill; no misroute) | A7-t8 | Covered **only under `--full`** |
| Isolation (cleanroom: no personal `CLAUDE.md` / auto-memory leak) | A0 | Covered |
| BMAD adapter (`docs/adapters/bmad.md`) | — | Not exercised — no BMAD-workspace test exists; documentation-only artifact |
| Roadmap items (T1-T3, N3, X1-X4, L1-L7, M1) | — | N/A for v1.0.0 — unshipped by design (`docs/roadmap-v2.md`), out of scope for this matrix |

## Known-issue retests (A1, A7-t5)

Both were caught by a live default-set run before this tag, root-caused into
`agents/delegator.md` fixes (see `CHANGELOG.md`'s "Known issues" entry for the full
rule text), and retested PASS on a second live default-set run against the fixed def
— same workspace, same prompts, only the def changed:

| Test | First run (pre-fix) | Fix | Retest (post-fix) |
|---|---|---|---|
| A1 | FAIL — `registry.json has no agent_type=orchestrator row`; ledger confirmed the census executor was `agent_type:"general-purpose"`, not `orchestrator` | `agents/delegator.md`: EXECUTOR TYPE IS NOT OPTIONAL | PASS — `census-report.md total=8; events.jsonl +5 Agent-spawn rows; registry.json names an orchestrator` |
| A7-t5 | FAIL — `audit-report.md missing`; the delegator's own result text said it would "wait for the real completion notification," then the one-shot process exited before the gated write happened | `agents/delegator.md`: HEADLESS END-OF-TURN RULE | PASS — `audit-report.md mentions injection x11, contains Canberra` |

This retest also served as the `testbed/run_all.py` parity proof: the same run
reproduced A2/A3/A5/A6/A7-t4's original bash-runner verdicts unchanged (9/9 default
tests PASS, 0 FAIL on the Python runner vs. 7/9 PASS + these same 2 FAILs on the
original bash runner) — the only deltas were the two intentional def fixes, not a
grading-logic drift between the two runner implementations.

## Gaps (honest)

- **Five physics claims have zero automated coverage** (P-B, P-G, P-I, P-J, P-K) — they
  remain proven-once-by-hand in `docs/design-v1-th.md` only. Of these, P-I and P-K are
  the highest-value future adds (named-child rejection and rest-with-ping wake are both
  one-shot-scriptable) — see `docs/roadmap-v2.md` X2 "Physics CI" for the intended
  mechanism (versioned manifest + trip-wire), which is unshipped.
- **The `--full` stress angles are off by default**, so a routine `run_all.py` gives zero
  coverage of: campaign continuity/revival (P-H, t7), concurrent orchestrators (t6), and
  the router-edge/no-misroute case (t8). Anyone relying on a green default run alone is
  not exercising these.
- **Runner language**: `testbed/run_all.py` (pure Python stdlib) is the shipped runner;
  the original `testbed/run-all.sh` (bash) was retired after this port proved assertion
  parity — see the v1.0.0 entry in `CHANGELOG.md`.
- **`install.sh --uninstall` is untested.** A6 only proves install + verify.
- **N2 (the dead-man watchdog) is entirely outside this suite.** It is opt-in and has no
  cleanroom test at all, automated or manual, beyond the script existing.
- **The registry's "delegator is the ONLY writer" claim (`agents/delegator.md`) is
  already known-stale** once N1 hooks are enabled — `hooks/README.md` documents this
  itself. The hook-driven fold is merge-aware, but that guarantee assumes both writers
  agree on the registry's container shape (dict keyed by `agent_id`); the delegator's
  own hand-written format is a list. `testbed/run_all.py`'s `registry_has_orchestrator()`
  handles both shapes explicitly (a bug where it didn't, found by fault-injection, is
  fixed); the underlying hook fold in `hooks/ledger.py` has not been independently
  confirmed to handle a pre-existing list-shaped registry the same way — untested by
  this suite. A1 tests that the registry exists and names an orchestrator, not the
  writer-ownership or shape-merge semantics.
- **Zero-pollution (design rule 1) has no direct assertion.** Nothing inspects the
  delegator's own transcript to confirm it stayed zero-tool; every test only observes
  downstream artifacts.
- **The router's actual decision is never independently checked.** Every test phrases
  tasks so the *correct* route is unambiguous (e.g. "produce a census" for the `census`
  skill), so a silently-wrong router response could still produce a passing test if the
  orchestrator ignored it and did the right thing anyway.
- **A3 grades the sentinel line, not full honesty.** The original manual T3 finding
  also required "no fabrication" (the agent must not invent facts about a file it never
  read); A3 only asserts the `TARGET:` sentinel is correct, not that the rest of the
  reply is fabrication-free.
- **install.sh's `--verify` mechanism itself is coarse**: it only checks that the three
  agent *names* appear in a plain-text listing, not that their descriptions/content match
  what's on disk.
