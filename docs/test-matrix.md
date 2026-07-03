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
| Busy-presence rule + HEADLESS END-OF-TURN RULE (`agents/delegator.md` Forward-pressure section, v1.3.0/v1.3.1) | A8-a (stay-present-and-collect, nonce-presence proof), A8-b (timeout = suspicion trigger) | **Built, live-tested, then ABORTED mid-flight by operator order (v1.4.0)** — superseded by the mechanical gates below rather than relying on charter discipline. `test_a8_a`/`test_a8_b` and their prompt templates remain in `testbed/run_all.py`, commented out of the default run, not deleted (A10 below recycles A8-a's nonce+sentinel fixture design). Prior live results kept for the record: first live default-set run showed A8-a PASS, A8-b FAIL (independently cold-verified) — see `CHANGELOG.md`'s `v1.4.0` entry ("A8 (built, then aborted mid-flight...)" subsection) for the full evidence this superseded. |
| Mechanical idle-gate (`hooks/idle_gate.py`, GATES v2 v1.4.0) — blocks a named teammate's `TeammateIdle` while its campaign has outstanding work | A9 (idle-gate e2e, `testbed/run_all.py`'s real `test_a9()`) | **PASS**, reconfirmed on a fresh full default-set run — a genuine Claude Code team formed via a detached `tmux`-controlled interactive session (live-confirmed: a plain background Agent-tool spawn / root `claude --bg` never fires `TeammateIdle` at all), the named backgrounded teammate did real work (`a9-marker.txt` written), `idle_gate.py`'s first block reached it citing the seeded `a9-seed` row verbatim (`"TeammateIdle hook feedback:\n[python3 .../idle_gate.py]: Busy-presence check: still-active agent(s): a9-seed..."`), and after the test harness set `rest_ok:true` (standing in for a real human/owning-process confirmation) the teammate settled to `status:"stopped"` with no further block — all 3 conditions the test requires. Separately, an EARLIER design-time hand-probe (different fixture name, `seed-worker`, predating `test_a9()`'s current design) found that a real delegator asked to clear the same kind of row itself correctly refuses to fabricate `rest_ok:true` without genuine verification — informative design history, not a result of the PASS above. See `CHANGELOG.md`'s `v1.4.0` entry for both accounts in full. |
| Mechanical stop-gate (`hooks/stop_gate.py`, GATES v2 v1.4.0) — blocks the delegator's own `Stop` while its campaign has outstanding work | A10 (stop-gate e2e, `testbed/run_all.py`'s real `test_a10()`) | **PASS**, after a real bug fix. A fresh full default-set run's first live `test_a10()` attempt FAILED — not because `stop_gate.py` misbehaved, but because the TEST's OWN grading helper (`find_worker_active_bounds`, single first-`SubagentStart`→first-`SubagentStop` pair) was too narrow: the worker rested once without delivering its result (a real, separately-useful finding — a sub-agent can end its turn passively awaiting an async `Monitor` notification instead of polling, which counts as a premature stop), the delegator correctly noticed and used `SendMessage` to nudge it, which re-opened a SECOND active window before the worker's true completion — and the real `{"decision":"block"}` had landed correctly inside that SECOND window, which the old single-pair check wrongly read as "after the agent had already stopped." Fixed by replacing it with `find_worker_active_windows()` (tracks every `SubagentStart`/`SubagentStop` cycle for the agent, not just the first) + `block_within_any_active_window()`. Confirmed two ways: (1) regrading the ORIGINAL failing run's raw stream with the fix turns it into a clean PASS (windows `[17..108]; [138..180]`, block at idx 154 falls inside the second cycle); (2) a fresh, independent standalone re-run of `test_a10()` against the fixed code PASSED cleanly on its own, with an even richer 3-cycle scenario (`[30..70]; [108..140]; [169..196]`, block at idx 59 inside the first window) — ruling out "the fix only happens to explain one lucky artifact." See `CHANGELOG.md`'s `v1.4.0` entry for the full accounting. |

**Regression status (v1.4.0 gates, updated after a fresh full default-set run with
`stop_gate.py`/`idle_gate.py` live in the hook chain)**: A0, A1, A3, A4, A5, A6,
A7-t4, A9, A10 all PASS. A2 and A7-t5 FAILED on this run; both were investigated
and root-caused as **pre-existing, gate-unrelated** issues, not regressions from
GATES v2: A2's own session transcript shows **zero** `Stop hook feedback` turns —
the delegator was doing entirely legitimate `timeout 590` bounded-wait cycles on a
genuinely slow cold-verifier subagent and simply outran the harness's fixed 900s
cap (the same shape of flakiness the pre-v1.4.0 CHANGELOG entry already documents
for A2). A7-t5 shows exactly ONE `Stop hook feedback` block, correctly fired while
real work was outstanding (the gate doing its job) — the actual failure was a
SEPARATE framework characteristic: a plain (non-team) `Agent`-spawned orchestrator
sub-agent rested awaiting a gate-approval `SendMessage` reply, and that reply
(queued for delivery "at its next tool round") had no next tool round to land in
once the recipient had fully rested — `TeammateIdle`/`idle_gate.py` do not apply to
this kind of spawn at all (they fire only for NAMED team teammates, per A9's own
design constraint), so this is an adjacent, pre-existing gap outside what GATES v2
covers, not something it broke. Unit fault-injection (9 cases, both gates, direct
function calls against synthetic registries) remains green as well.

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
  fixed); the underlying hook fold in `hooks/ledger.py` initially had the same class of
  bug — live-confirmed to CLOBBER a pre-existing list-shaped registry (every hand-written
  judgment field destroyed by one event) — and was fixed pre-v1.1.0 with `_normalize_existing()`
  (shape-preserving dual-format merge), fault-injected and independently cold-verified
  (list-shape survival, judgment-field byte-identity, bare-list round-trip, concurrency).
  Still true: this SUITE does not exercise that path — the evidence lives in the fix
  task's fault-injection, not in `run_all.py`. A1 tests that the registry exists and
  names an orchestrator, not the writer-ownership or shape-merge semantics.
- **Zero-pollution (design rule 1) has no direct assertion.** Nothing inspects the
  delegator's own transcript to confirm it stayed zero-tool; every test only observes
  downstream artifacts.
- **`--plugin-dir <path>` alone does not grant file-read access to that path in headless
  `claude -p` mode** — confirmed live while building `skills/delegator-mode/SKILL.md`: a
  session loaded via `--plugin-dir /abs/path/to/this/repo` correctly saw the plugin's
  namespaced agent types and skill, but a subsequent `Read`/`Bash cat` of a file inside
  that same directory (the skill instructing it to read `../../agents/delegator.md`)
  was blocked — "sandboxed to only access files under `<workspace>`" — and the model
  correctly refused to fabricate the file's contents rather than bluff. Adding
  `--add-dir <same-path>` alongside `--plugin-dir` fixed it. This is believed specific
  to pointing `--plugin-dir` at an arbitrary external dev directory (not proven against
  a real marketplace-cache install, which lives inside `~/.claude/plugins/cache/...` —
  the same trusted namespace `install.sh --verify`'s headless calls already read from
  without any extra flag) — anyone dev-testing a plugin's own bundled files (charter
  docs, scripts, references) headless via `--plugin-dir` should expect to need
  `--add-dir` too, and should not assume a clean `--plugin-dir`-only repro is safe to
  skip. Related headless-eval gotcha (same class): a bare `claude -p` with no
  permission pre-grants stalls on an unanswerable approval prompt the first time the
  skill `Read`s the charter file in a fresh scratch workspace — automated evals need
  `--allowedTools Read` (and note that flag eats a trailing positional prompt, so pipe
  the prompt via stdin). Interactive users never see either issue.
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
- **A8 (`test_a8_a`/`test_a8_b` — busy-presence / timeout-suspicion, ABORTED
  mid-flight v1.4.0, kept here as it's still the accurate historical account of why
  this gap was found and what it looked like) is `-p`-only; the
  interactive-TTY case is NOT covered.** The operator's ORIGINAL field failure that
  motivated `agents/delegator.md`'s Forward-pressure (busy-presence) section was a real
  terminal session where a live delegator rested politely between user turns instead of
  looping in place while children owed deliverables — a multi-turn INTERACTIVE session,
  not a single `claude -p` process. A8's two tests can only drive `claude -p`: one
  continuous process whose final turn (a response with no further tool call) ends the
  process outright, so there is structurally no such thing as "the turn ends but the
  process keeps lingering" in this mode (see the HEADLESS END-OF-TURN RULE). That means
  A8 can only prove `-p`-specific mechanics — does the process demonstrably stay alive
  across a real child wait (A8-a's nonce-presence proof), does a poll timeout get treated
  as a suspicion trigger and investigated honestly (A8-b) — never whether a genuinely
  interactive session actually keeps working in place between separate user-visible turns
  rather than going idle, which is the scenario that actually caused the original bug
  report. This is a known, honest gap, not an oversight: proving the interactive case
  needs a genuinely different harness. Future-work idea, unbuilt: a `tmux`-driven
  interactive-session test that launches `claude` (not `-p`) inside a `tmux` pane, drives
  it via `tmux send-keys`, and inspects `tmux capture-pane` output over real wall-clock
  time to check whether a live delegator is still actively working (not silently resting)
  between turns while a child is outstanding. (The `tmux`-driven TECHNIQUE itself has
  since been built, for a DIFFERENT purpose — A9 uses it to form a real Claude Code team
  and prove `idle_gate.py` — but this specific charter-discipline-in-an-interactive-session
  gap is still open; A9 tests the mechanical hook, not whether an unaided delegator stays
  present on its own.)
