# Changelog

All notable changes to `claude-code-delegator` are documented here.

## Unreleased

- **`LOOP_AGENT` watchdog signal (closes #4).** The v1.4 watchdog catches a child
  that is *silent-and-still* (`STALE_AGENT`) but had no signal for the sibling
  failure — a child that is *noisy-but-spinning*: making the SAME tool call with the
  SAME args over and over inside one turn, so it never idles and every time-based
  liveness cue (ledger freshness, transcript growth) reads as healthy. This is the
  149×-identical-`check-status-gate` loop that only a human's transcript audit caught.
  The ledger can't see it (`PostToolUse` is wired only for `Agent|SendMessage`, so an
  MCP-tool loop emits zero ledger rows), so detection reads the child's OWN transcript
  at `<project>/<session>/subagents/agent-<id>.jsonl`, hashes each `tool_use`'s
  (name, args), and flags a trailing run of ≥5 identical consecutive calls —
  `LOOP_AGENT <name> repeated <tool> x<n> (same args) (owes: …)`, injected the same
  way `STALE_AGENT` is (PostToolUse / UserPromptSubmit `additionalContext`). Emitted in
  both hook mode and the manual/background sweep. Consecutive-identical (not "N in a
  window") keeps false positives near zero — a healthy agent hammering one tool varies
  its args. Deduped via a separate `last_loop_alert_at` field so a loop and a stale
  alert never suppress each other. Fully fail-open, stdlib-only. New self-test
  `hooks/test_watchdog_loop.py` (6 checks). Still open in #4: interrupting a
  within-turn loop (SendMessage only lands at a turn boundary) and a child-side
  auto-escalation reflex — this closes the *detection* half.

## v1.4.1 (2026-07-03)

Bug-fix follow-up to v1.4.0 — all found by investigating the first real full-suite
run and closing the three issues it surfaced (#2, #3). Gate mechanism unchanged;
these fix the read-side race, a test grader, and document a resting-subagent rule.

- **First premature Stop now blocks (closes #3 Gap 1 + #2).** `campaign_has_outstanding_work()`
  read only the ledger-derived `registry.json`, which LAGS at a spawn boundary — the
  first `Stop` could fire before the just-spawned worker's `SubagentStart` had folded
  into `status`, so the gate saw "nothing active" and allowed a premature stop. It now
  also honors the delegator's `owes:true`/per-agent `rest_ok` judgment fields, which are
  written SYNCHRONOUSLY at spawn (beating the async fold) — closing the race and the
  long-standing owes-contract divergence in one change. Verified by 5 synthetic cases,
  zero live sessions.
- **Multi-cycle A10 grader (test-harness only).** The shipped `test_a10` grader tracked
  only the worker's FIRST `SubagentStart..SubagentStop` cycle, false-failing a legitimate
  run whose correct Stop-block landed in a SECOND cycle (after the worker rested once and
  was nudged). Replaced with all-cycles tracking; A10 passes on two independent runs.
- **Resting-subagent answer rule (closes #3 Gap 2).** Probe-confirmed: `SendMessage(agentId)`
  revives a rested subagent ("resumed it in the background with your message"), but a
  mailbox/name send to a fully-rested recipient "queues for the next tool round" — which a
  rested agent never takes — and hangs (the A7-t5 root cause). The delegator charter now
  mandates answering resting agents via `agentId` revival, never a name/mailbox send.

## v1.4.0 (2026-07-03)

### Verified state (honest — release-gate spot-check by the delegator)

The gate MECHANISM is proven: a synthetic Stop payload against an owing campaign
registry yields exactly `{"decision":"block", "reason":"Busy-presence check…"}` and an
empty allow on a settled one (plus 4 real `Stop hook feedback` blocks in the `calib2`
hand-probe). `idle_gate.py` A9 e2e: clean PASS via real team formation. Unit
fault-injections: 9/9.

**Update, same tag**: the items below were the honest known-issues list at the point
of the operator "works-is-enough" trim (full-suite regression, cold-verify, and
repeated e2e were cut at that time). A follow-up pass has since completed that
work — see "A9/A10 — live end-to-end evidence" below for the full accounting,
including the real bug `test_a10()` had (in its own grading code, not the gate)
and its fix. Kept here, struck through in spirit but not in fact, for the honest
record of what was and wasn't known at each point:
- ~~`test_a10()` automated regression does NOT pass (7/7 attempts failed:
  rate-limits, timeouts, and a "nonce not found" bookkeeping bug).~~ **Root-caused
  and fixed**: the one clean, reproducible FAIL (once a fresh full default-set run
  was actually done) was the test's OWN grading helper only tracking a worker
  agent's FIRST `SubagentStart`→`SubagentStop` cycle, missing a later, genuinely
  correct block that landed during a SECOND cycle (after the worker rested once
  without delivering its result and got nudged back via `SendMessage`). Fixed;
  `test_a10()` now PASSES, confirmed on two independent live runs. Full details below.
- **Loop guard fixed post-report**: `stop_gate.py` ignored `stop_hook_active`, so a
  continuation chain could re-block instead of concluding once (a likely contributor to
  the A10 timeouts). Now allows when `stop_hook_active` is true; re-verified by synthetic
  probe (block-once, re-engage on fresh stop). No live session needed.
- **Release-contract divergence**: the gate keys off `status=="active"` + a top-level
  `rest_ok` escape, NOT the charter's per-agent `owes` field. Flipping `owes:false` alone
  does not release the gate today. Reconcile the charter's owes-contract with the gate's
  status-based logic in a follow-up (no `stop_blocks` consecutive-valve yet either).

### Mechanical busy-presence gates (GATES v2) — replaces charter-discipline polling

- **Why**: A8 (below) proved the busy-presence rule works when the delegator *chooses*
  to comply with its own charter — but that's still discipline, not enforcement. The
  operator ordered a pivot mid-A8 (`TaskStop`, A8 aborted — its test functions and
  prompt templates are left in `testbed/run_all.py`, uncalled, for A10 to recycle
  rather than rebuild): if Claude Code's own hook system can *mechanically* block a
  premature Stop/TeammateIdle, busy-presence no longer depends on model compliance
  at all. Four foundational claims were live-probed before building anything —
  **do not trust the docs alone** was the operating rule, and it caught real gaps:
  1. **P1 — Stop force-continue: CONFIRMED.** `{"decision":"block","reason":"..."}`
     on the `Stop` event genuinely prevents the process from exiting; delivered to
     the model as a synthetic user turn (`"Stop hook feedback:\n<reason>"`); the
     model complied and produced exactly the continuation asked for. `stop_hook_active`
     flips `true` on the retry — the loop-guard signal a gate checks to know it's
     seeing a re-fire, not a fresh attempt.
  2. **P2 — SubagentStop feeds the STOPPING SUBAGENT, not the parent: CONFIRMED.**
     Reconciles the v1.3.0 finding that `additionalContext` never reaches the main
     session from `SubagentStop` — with `decision:"block"` it targets the child
     instead, and the child's own `stop_hook_active` flips true, proving the
     mechanism. **Real nuance found**: phrasing the injected reason as a bare
     imperative ("you MUST do X") gets the child to recognize it as
     prompt-injection-shaped and explicitly *refuse* the instruction, even though
     the block itself still forces another turn. Both gates below phrase their
     reason as factual state ("registry shows...") rather than a command, because
     of this finding.
  3. **P3 — SubagentStart birth injection: CONFIRMED.** Delivered via a distinct
     `hook_additional_context` *attachment* event, not a synthetic user turn like
     Stop/SubagentStop — a genuinely different delivery shape, not currently used by
     either gate below but confirmed available for future campaign-context-at-birth
     work.
  4. **P4 — TeammateIdle blocking: CONFIRMED**, after ruling out two wrong
     hypotheses first: a named+background Agent-tool spawn from a `-p` lead never
     fires `TeammateIdle` at all, and neither does a root `claude --bg` session
     (which *did* reveal `--bg` sessions are scriptable non-interactively via
     `claude agents --json`/`claude logs`/`claude stop` — updates a prior belief in
     this repo). The real trigger needs genuine Claude Code "team" formation
     (`~/.claude/teams/session-*/config.json`) — reached here via a detached `tmux`
     pane, a new technique for this repo. Blocks via **plain exit code 2 + stderr**
     text (not the JSON `decision` form) — a genuinely different schema from
     Stop/SubagentStop, delivered as a synthetic user turn labeled
     `"TeammateIdle hook feedback:\n[<hook command>]: <stdout+stderr>"`.
  - **Operational gotcha found across all four probes**: any stray stderr output
    from a hook script (even an incidental Python `DeprecationWarning`) surfaces to
    the user and can trigger a "Stop hook error" UI notification, even when the
    block itself works correctly — both gates below are written stderr-clean except
    for `idle_gate.py`'s one deliberate, load-bearing stderr write when actually
    blocking.
- **`hooks/stop_gate.py`** (new) — registered on `Stop`. **`hooks/idle_gate.py`**
  (new) — registered on `TeammateIdle`, alongside `hooks/ledger.py`/`hooks/watchdog.py`
  which already listen there. Both share one outstanding-work check,
  `hooks/ledger.py`'s new `campaign_has_outstanding_work()` — one source of truth
  so the two gates can never silently diverge on what counts as "busy", the same
  drift class that caused the registry shape bugs this module already fixed twice.
  The check has **three valves**: two that trigger a block —
  (1) any registered agent whose `status` is not `stopped`/`retired`/`died` (a
  child still actively running, per `fold_registry()`'s own status derivation),
  (2) an unanswered-gate condition in `events.jsonl` (reusing
  `hooks/watchdog.py`'s `check_unanswered_gates()`, not duplicating it) — and one
  release valve: an explicit `rest_ok: true` at `registry.json`'s top level, written
  only by a delegator itself, which always wins over either trigger — the
  delegator's own informed judgment (it reached one of its three legitimate
  end-states per `agents/delegator.md`'s Forward-pressure section) overrides a
  possibly-stale mechanical read. Both gates fail-open on every uncertain case
  (missing/corrupt registry, unresolved campaign, any exception) — they only ever
  block on positive evidence of outstanding work, never on doubt. Neither gate ever
  creates a directory or file. 9 fault-injection cases (owing→block, done→allow,
  `rest_ok` valve trip→allow, unanswered-gate→block, unregistered session→untouched,
  corrupt registry→fail-open, no registry→fail-open, mixed active/stopped agents
  →names only the active one, no campaign at all→untouched) all pass directly
  against both gate scripts.
- **A9/A10 — live end-to-end evidence.** The account below has two layers: the
  original evidence (checked against artifacts already on disk per an operator
  trim order — no new e2e attempts, no full regression suite) that shipped with
  this tag, plus a follow-up pass that ran the full default-set suite fresh, hit
  a real, fixable bug in A10's own test code, fixed it, and reconfirmed both
  tests live. Both layers are kept for the honest record:
  - **A9 (idle-gate e2e, `testbed/run_all.py`'s real `test_a9()`) — PASS.**
    Direct evidence from a completed run (`/tmp/.../a9-drive.log`): a genuine
    Claude Code team formed, the named backgrounded teammate did real work
    (wrote its marker file), `idle_gate.py`'s FIRST `TeammateIdle` block reached
    it citing the seeded `a9-seed` row verbatim
    (`"TeammateIdle hook feedback:\n[python3 .../hooks/idle_gate.py]: Busy-presence
    check: still-active agent(s): a9-seed..."`), and after the test harness set
    `rest_ok:true` (standing in for the human/owning-process confirmation a real
    delegator would need — see below), the teammate's registry row settled to
    `status:"stopped"` with no further block. Clean pass, all three conditions the
    test requires.
    - **A genuinely useful earlier finding, from design-time calibration, not
      this run**: an EARLIER hand-probe (before `test_a9()`'s current fixture
      design existed, using a differently-named fixture, `seed-worker`) revealed
      that a real delegator session, asked to clear the SAME kind of seeded
      "still active" row itself, correctly REFUSED to fabricate `rest_ok:true`
      without genuine verification — producing an honest, if unresolved,
      deadlock rather than false confirmation. That finding is *why* `test_a9()`
      has the test harness itself provide the resolution (mimicking a real
      human/owning-process confirming the item), rather than expecting the model
      to self-clear an item it has no way to verify — a real design lesson, kept
      here for the record, not a result from the run being reported as PASS above.
      It also surfaces a genuine production risk worth a documented recovery path
      before this ships unattended: an orphaned/stuck-`active` registry row with
      no real owner has no built-in way to clear itself (a human confirmation, or
      a staleness timeout on `active` status, are the two options that come to
      mind). Evidence: `/tmp/delegator-a9-calib-dump.jsonl` (17 lines, full
      transcript).
    - **Reconfirmed** on the fresh full default-set run described below — same
      three conditions, clean pass, no regression.
  - **A10 (stop-gate e2e, `testbed/run_all.py`'s real `test_a10()`) — PASS**,
    after a full accounting of everything that came before and one real bug
    found and fixed along the way. Original evidence at the time of the
    operator trim, kept for the record: **FAIL across all 7 recorded attempts**
    (rate limits, timeouts, one run where `stop_gate.py` was never exercised at
    all by the time `Stop` fired, two runs where the nonce never appeared in the
    delegator's final result text) — the underlying MECHANISM was separately,
    convincingly confirmed working by a hand-driven calibration probe
    (`/tmp/a10-calib2-stream.jsonl`, predating `test_a10()`'s current design):
    repeated real `"Stop hook feedback:\nBusy-presence check: still-active
    agent(s): <id>..."` blocks (`num_turns: 19` vs. a control run's `2`)
    followed by the delegator's own final reply containing the correct worker
    nonce — real evidence the gate itself works, but not the same claim as "the
    automated e2e test passes reliably," which at that point it had not.
    - **Follow-up: a fresh full default-set suite run (`./run_all.py`, no
      `--full`) was actually done** — the thing the trim explicitly skipped.
      `test_a10()`'s FIRST live attempt under this run FAILED with: "Stop-block
      at stream idx 154 does not fall strictly within the worker agent's own
      active window (SubagentStart idx 17 .. SubagentStop idx 108)." Full
      forensic read of the raw `--include-hook-events` stream and the
      session's own `events.jsonl` (real UTC timestamps) showed this was NOT
      `stop_gate.py` misbehaving: the worker rested once at 14:22:26Z without
      delivering its result (a real, separately-useful finding in its own
      right — a sub-agent can end its turn passively awaiting an async
      `Monitor` notification instead of polling, which counts as a premature
      stop), the delegator noticed via its own busy-presence check and used
      `SendMessage` to nudge it at 14:22:52Z, re-opening a SECOND
      `SubagentStart`→`SubagentStop` window before the worker's true
      completion at 14:23:13Z — and the real `{"decision":"block"}` (stream idx
      154) had landed correctly inside THAT second window. The test's own
      grading helper, `find_worker_active_bounds()`, only tracked the FIRST
      Start→Stop pair (idx 17..108) and wrongly read the later, genuinely
      correct block as landing "after" that too-narrow window — a bug in the
      test's own code, not in the gate. Separately, that SAME run's FIRST Stop
      attempt (right after the delegator's forced one-line status reply, while
      the worker's first window was still open) was allowed through with an
      empty hook response rather than blocked — noted here as an honest, not
      fully root-caused, open observation (plausibly a hook-ordering nuance
      specific to that instant), since it did not affect the run's outcome
      (the SECOND, later attempt was correctly blocked, and stop_gate.py's own
      unit fault-injection coverage separately confirms the block logic itself
      is correct against a synthetic registry).
    - **Fix**: replaced `find_worker_active_bounds()` with
      `find_worker_active_windows()` (returns every `SubagentStart`/`SubagentStop`
      cycle for the agent, not just the first) plus
      `block_within_any_active_window()` (true if the block index falls inside
      ANY of them). Confirmed two ways: (1) regrading the ORIGINAL failing run's
      raw stream with the fix alone turns it into a clean PASS — windows
      `[17..108]; [138..180]`, block at idx 154 falls inside the second; (2) an
      independent fresh standalone re-run of `test_a10()` against the fixed code
      PASSED cleanly on its own with an even richer 3-cycle scenario (windows
      `[30..70]; [108..140]; [169..196]`, block at idx 59 inside the first) —
      ruling out "the fix only happens to explain one lucky artifact."
    - **Full default-set regression, now actually done**: A0, A1, A3, A4, A5, A6,
      A7-t4, A9, A10 all PASS on the same fresh run. A2 and A7-t5 FAILED; both
      were investigated and root-caused as pre-existing, gate-unrelated issues,
      not regressions from GATES v2 — full accounting in `docs/test-matrix.md`'s
      regression-status note (A2: zero `Stop hook feedback` turns in its own
      transcript, a genuinely slow cold-verifier chain that outran the harness's
      fixed 900s cap, same shape as a previously-documented flakiness class; A7-t5:
      exactly one `Stop hook feedback` block, correctly fired while real work was
      outstanding, with the actual failure being a separate SendMessage-to-a-
      fully-rested-non-team-subagent delivery gap that `TeammateIdle`/
      `idle_gate.py` do not cover at all, since that mechanism only applies to
      NAMED team teammates). Unit fault-injection (9 cases, both gates) remains
      green throughout.
- **`hooks/hooks.json`/`hooks/delegator-hooks.json`**: `stop_gate.py` added as a new
  `Stop` entry; `idle_gate.py` added alongside the existing `ledger.py`/`watchdog.py`
  commands under `TeammateIdle`.
- **`.claude-plugin/plugin.json`**: version bumped to 1.4.0.

### A8 (built, then aborted mid-flight — kept in the record, not erased)

Everything below shipped code-complete and was live-tested before the operator
ordered a pivot to the mechanical gates above; `test_a8_a`/`test_a8_b` and their
prompt templates remain in `testbed/run_all.py`, commented out of the default run
rather than deleted, specifically so A10 above could recycle the nonce-child
fixture design rather than rebuild it from scratch.

- **A8 — permanent regression pair for the busy-presence rule (`agents/delegator.md`'s
  Forward-pressure section) and the HEADLESS END-OF-TURN RULE it generalizes**
  (`testbed/run_all.py`: `test_a8_a`/`test_a8_b`, wired into the default set immediately
  after `test_a7_t5()`). Two new, permanent live `claude -p --agent delegator` tests —
  every future default `./run_all.py` run now exercises this rule mechanically, not just
  once by hand.
  - **A8-a (stay-present-and-collect)** briefs the delegator to spawn one worker running
    a genuinely slow (~90s) `sleep 90 && echo 'RESULT: SLOW-OK <nonce>'` and relay the
    exact RESULT line. The nonce is a fresh `uuid4` minted every run — never hardcoded —
    so there is no ambiguity about coincidence. **PASS is anchored on one load-bearing,
    structural fact**: that nonce, only ever emitted by the worker ~90+ real seconds into
    the run, showing up in the delegator's OWN final `-p` result text. Per the HEADLESS
    END-OF-TURN RULE, a `-p` process's final turn (a response with no further tool call)
    ends the process outright — there is no "turn ends but the process lingers" state —
    so that nonce cannot reach the final answer unless the process was genuinely still
    alive, polling/waiting, when the worker finished. Mechanism evidence (which polling
    idiom actually fired — the charter's own `timeout N bash -c 'until grep...'`,
    `Monitor`, or the harness-native `ScheduleWakeup`) is gathered from the raw session
    transcript for transparency only and never overrides a clean nonce-presence PASS.
  - **A8-b (timeout = suspicion trigger)** — same shape, but the worker's command
    (`sleep 600`) is meant to stall with no result ever emitted; the delegator's brief
    bakes in only a soft "~2 minutes" expectation, never instructions on how to detect or
    react to a stall (that reaction is exactly what's under test). PASS requires
    transcript evidence of (1) a bounded-wait poll actually reaching its own deadline
    without a match, (2) a ground-truth check or SendMessage classify-nudge following
    that timeout, and (3) an honest final report — acknowledging non-delivery, not
    claiming success, and not making a forward-looking "I will keep monitoring / wait for
    its completion notification" promise a process that has already ended can never
    keep (that last clause was added after a live diagnostic run produced exactly that
    phrasing and a naive keyword check would have misgraded it as honest).
  - **Live findings (first real runs against the current charter, not hypothetical —
    full transcripts retained, independently cold-verified, see below)**: on the
    recorded default-set run, **A8-a PASSED** — nonce present, and the delegator's own
    transcript shows real skeptical-operator behavior: its first bounded-wait poll
    returned a coincidental false-positive (grepping "RESULT:" against the worker's own
    echoed prompt text, not real output), and rather than trusting it, the delegator
    ground-truthed the actual output file's size directly and ran a second, genuine
    ~79-second bounded wait before reporting. **A8-b FAILED** — but the worker's `sleep
    600` was intercepted in ~2ms by the Bash tool's own guardrail against standalone
    long sleeps ("Blocked: standalone sleep 600 ... use Monitor ... or
    run_in_background"), so the intended multi-minute stall never actually occurred; the
    delegator's final report was independently confirmed honest and non-fabricating, but
    conditions (1) and (2) were structurally unmet because there was no real stall to
    detect — a scenario-design gap in A8-b worth refining (a command that reliably keeps
    running in the background rather than tripping this guardrail), not evidence of
    dishonest or hung behavior. Separately and unprompted, a **pre-existing, unrelated
    test (A2, `audit data/facts.md`) failed on the SAME live run** with the exact bug
    class A8 exists to catch: a long, otherwise-exemplary multi-cycle busy-presence
    session (real ground-truth checks, real classify-nudges, correct no-relay
    discipline, ~284 transcript lines of genuine work) still ended its very last turn on
    "I'll stop here and let the harness re-invoke me on the wakeup or next event" —
    fatal in `-p` mode regardless of how much correct behavior preceded it. This
    independently corroborates that the gap A8 is built to catch is real and systemic,
    not an artifact of A8's own task phrasing — confirmed uncaused by this change (A2's
    code path is untouched by and disjoint from the A8 additions).
  - **Cold-verified**: a fresh, independent verifier (no shared context) re-read the raw
    `.json` results and raw session `.jsonl` transcripts from scratch and independently
    reproduced both verdicts (PASS/FAIL) — agreeing with `record()`'s logged results on
    both tests, while flagging that the specific "mechanism evidence" line logged for
    A8-a cited the coincidental false-positive poll rather than the delegator's own
    genuine second one (informational, does not change the PASS), and that A8-b's
    "final report not honest" clause was a keyword-regex miss on honest
    policy-block language rather than a real dishonesty finding (informational, does not
    change the FAIL, since conditions (1)/(2) already fail it independently).
  - **Known, honest gap**: both tests are `-p`-only and structurally cannot exercise the
    interactive-TTY case (a live terminal session where a delegator rests between user
    turns rather than looping inside one continuous `-p` invocation) — the operator's
    ORIGINAL field case that motivated the busy-presence rule. See `docs/test-matrix.md`'s
    Gaps section for the full write-up and a `tmux`-driven interactive-harness idea for
    future work.

## v1.3.1 (2026-07-03)

- **BUSY-PRESENCE RULE (operator field report, screenshot evidence)**: a live
  delegator sat "waiting politely" across multiple turns — ending turns into idle
  while children owed deliverables, citing discipline rules as reasons for
  passivity — and instantly decided 8+ pending items the moment the human kicked
  it. Root cause: the charter allowed turn-ending waits. Fixed: while ANY child
  owes a deliverable the delegator does not end its turn — it loops advance-check
  (decide/advance everything decidable, in batch) → bounded in-turn wait (one
  cheap `timeout … until grep` call per interval) → on timeout, the silence IS
  the suspicion trigger (ground-truth sweep + classify-nudge). The poll-timeout
  replaces any need for an external heartbeat. Turns may end only on: milestone
  complete (report at milestone granularity), a genuinely-human gate, or
  retirement. The headless end-of-turn rule is thereby generalized to every mode.
- **NO-RELAY ≠ NO-LOOK**: the no-relay rule forbids forwarding a grandchild's
  results around its parent — it never forbids the delegator READING completed
  outputs that feed its own decisions; the live session had misread it as
  look-prohibition.

## v1.3.0 (2026-07-03)

### Proactive watchdog: automatic STALE_AGENT alerts (github issue #1)

- **The mechanical half of "stalls should be caught by the delegator, not the
  human"**: a real live campaign hit children going idle mid-task without
  reporting back, sitting silent until a human noticed and pointed it out
  twice before the delegator investigated (full repro in issue #1). This ships
  the automatic-detection half — `hooks/watchdog.py` is now hook-registered
  (previously manual-arm only) and injects a `STALE_AGENT` notice directly
  into the delegator's own context the moment any registered campaign has an
  active agent that's gone quiet past its own threshold, with zero reliance on
  the delegator remembering to check.
- **PHYSICS FINDING, release-notes-worthy on its own**: the obvious design —
  wire the alert to `SubagentStop`, the event that fires exactly when a child
  finishes or goes idle — **does not work**. Live-probed on Claude Code 2.1.199:
  structured `{"hookSpecificOutput": {"hookEventName": ..., "additionalContext": ...}}`
  output genuinely reaches the calling session's context for `PostToolUse` and
  `UserPromptSubmit` (confirmed by the model quoting injected text back
  character-for-character, including a dynamic value), but for `SubagentStop`
  specifically it does not — 3 convergent negative tests (bare stdout, the
  correct JSON schema, a same-turn follow-up tool call) against a clean
  positive control on `UserPromptSubmit`, ruling out a methodology error.
  Claude Code's own hook telemetry shows the `SubagentStop` hook firing,
  exiting 0, and producing well-formed output — the model just never sees it.
  Alerts are wired to `PostToolUse` (matcher `Agent|SendMessage`, the same
  matcher `hooks/ledger.py` uses — this covers the delegator's own
  spawn/nudge/gate-answer moments) and `UserPromptSubmit` (covers "the human
  returns and says anything → stale agents surface immediately", issue #1's
  scenario inverted). `hooks/ledger.py` keeps listening to `SubagentStop` for
  its own event-collection purposes, unaffected by this finding — the split is
  clean: `SubagentStop` feeds data, `PostToolUse`/`UserPromptSubmit` deliver
  alerts. `TeammateIdle` is wired too, as unconfirmed upside (a silent no-op if
  it doesn't support injection costs nothing) — two honest live attempts to
  trigger a genuine idle transition were both structurally blocked (a one-shot
  session can't produce one; `--bg` needs a real interactive TTY this
  automation can't drive) — documented as UNPROBED, not claimed as working.
- **Alert format**: `STALE_AGENT <name> silent <N>m last_event=<type> (owes:
  <description-or-purpose>)`, one line per stale agent, newline-joined into a
  single `additionalContext` if more than one agent is stale at once. Only
  agents whose registry `status` is NOT `stopped`/`retired`/`died` are
  considered. Threshold is a per-agent `soft_timeout_minutes` judgment field
  (the delegator charter writes it; default 15 if absent/invalid). Alerts
  dedupe per agent for 10 minutes via a new `last_alert_at` mechanical field
  stamped onto that agent's own registry entry — load-bearing specifically on
  `UserPromptSubmit`, since that fires on every single user turn, not just
  when the delegator acts.
- **`hooks/ledger.py` refactor enabling this safely**: extracted the
  shape-dispatch write-back logic from `fold_registry()` into a new shared
  `write_registry_shape()` function, and renamed `_normalize_existing()` to
  `normalize_existing()` (dropping the leading underscore — it's no longer
  private to `ledger.py` alone). `hooks/watchdog.py` now does
  `import ledger` (works because both files live in `hooks/` together) and
  calls these exact same functions to safely stamp `last_alert_at`, so its
  registry write can never drift from `fold_registry()`'s own understanding of
  registry shape — the entire reason the last two registry bugs existed was
  exactly this kind of duplicated understanding going stale in one place but
  not the other. Confirmed behavior-preserving: re-ran all 5 prior
  shape/no-write fault-injection cases against the refactored code, identical
  results.
- **Fault-injected directly (12 cases) then proven end-to-end live (6 probes)**:
  direct calls to the new hook-mode logic covered default/custom thresholds,
  status exclusion, dedup both directions, multi-agent alerts in one
  `additionalContext`, missing registry entries, and a missing registry file
  entirely — all passed. Separately, a real campaign in an isolated scratch
  `$HOME` (never the real one) proved the full path end-to-end: a genuinely
  stale real agent's alert reached the model's own context verbatim (matching
  its actual elapsed silence), a stopped agent and fresh activity both stayed
  silent, the dedup window suppressed a same-agent re-alert within 10 minutes
  and correctly re-fired after backdating past it, an unregistered session
  produced zero output and zero writes anywhere (workspace tree byte-identical
  before/after), and `hooks/ledger.py`'s own event collection was confirmed
  unaffected. One methodology note worth keeping: hand-editing a registry
  entry to simulate staleness and then firing ANOTHER `PostToolUse(Agent)`
  event doesn't work as a test technique, because `fold_registry()` (which
  also listens to that event) re-derives the real status from `events.jsonl`
  history and overwrites the simulated edit before `watchdog.py` runs — not a
  bug, a real and arguably desirable self-healing property of the design, just
  something to route around when hand-simulating staleness for a test.

### `.claude-plugin/plugin.json`

- Version bumped to 1.3.0.

## v1.2.4 (2026-07-03)

- **Skill gates: the delegator answers them ITSELF (operator clarification of
  v1.2.3)**: relayed skill gates (menus / HALT / elicitation) are the delegator's
  to decide in EVERY mode — that is what user-proxy means; forwarding a skill's
  menu to the human is NOT the default even in interactive mode. The human sees a
  skill gate only when it genuinely needs their intent (scope, money, publish
  targets, identity — the fork-escalation bar).

## v1.2.3 (2026-07-03)

- **Skill gates are not forks (operator clarification)**: any decision point a
  SKILL presents (menu / HALT / elicitation / "ask the user") is the user's
  decision by design — it bypasses the orchestrator's self-answer/research ladder
  entirely and is ALWAYS relayed verbatim to the spawner, in every mode; the
  delegator answers it as user-proxy per the mode policy and never bounces it
  back down. The ladder applies only to ambiguities in the agent's own work.

## v1.2.2 (2026-07-03)

- **Autonomy correction (operator-caught)**: v1.2.1's orchestrator bullet told
  agents to self-resolve forks in autonomous runs — contradicting the delegator
  charter ("answer every child gate, never leave a child hanging") and pushing
  decisions down to the least-context level. Corrected: autonomous mode changes
  the orchestrator's gate discipline NOT AT ALL (its spawner is a machine, always
  present, holds campaign context, can commission research); the mode matters only
  at the human boundary, where the delegator answers or returns "DEFERRED — skip
  that step, complete the rest". "The human boundary is your spawner's problem,
  never yours."
- README caught up to v1.2.x: plugin quick-start now leads with auto-wired hooks +
  guard, per-session storage paths in the diagram and problems table, new
  autonomy/mode-intake row, 18+ probes badge.

## v1.2.1 (2026-07-03)

Charter-only release — the autonomy DNA wave (operator-driven, four rounds):

- **Gate policy by mode + MODE INTAKE**: the delegator asks the user
  interactive-vs-autonomous via AskUserQuestion at campaign start (main-session
  tool; hard-blocked in subagents — probed), skips the ask when the user already
  stated it, sticky per campaign, headless defaults to autonomous; the mode rides
  in every brief. Autonomous = the delegator IS the final gate: answers every
  child gate, logs resolved forks as Judgment calls, defers only human-territory
  irreversibles (child skips that step and finishes the rest — a run never hangs
  on a question).
- **Self-answer first**: a gate is earned — exhaust spec/repo/probe self-service
  before asking; the gate message must show the attempt.
- **Research is a self-answer tool**: practice/approach forks get a bounded
  web-research worker; PORT the field's established answer with a citation — it
  only becomes a judgment fork after research comes up empty.
- **Fork-resolution quality bar**: autonomous mode is not a quality discount —
  self-resolved forks must pick the defensible best-practice option; lazy
  resolutions (stub/fake, error-swallowing, hardcoding, silent scope cuts,
  outliving "temporary" hacks) are named and forbidden; equal options → prefer
  reversible; the delegator audits Judgment calls and flags lazy-fork as
  overclaim-class.

## v1.2.0 (2026-07-03)

### Plugin installs now auto-wire the hooks

- **`hooks/hooks.json`** (new file) — the operator asked why installing the plugin
  didn't also turn on the event ledger; it turns out Claude Code auto-registers a
  plugin's own `hooks/hooks.json` purely by its location inside the plugin (no
  reference needed in `.claude-plugin/plugin.json` — confirmed by reading two
  real, currently-live official Anthropic plugins that use exactly this pattern,
  `hookify` and `security-guidance`). Wires the same events as the classic
  `hooks/delegator-hooks.json` fragment (`SubagentStart`, `SubagentStop`,
  `PostToolUse` matching `Agent|SendMessage`, `TeammateIdle`), all pointing at
  `hooks/ledger.py` via `${CLAUDE_PLUGIN_ROOT}` so the path resolves correctly
  wherever Claude Code caches the installed plugin. `claude plugin validate .`
  passes. Live-probed (not just docs-trusted) on Claude Code 2.1.199: hooks fire
  under `--plugin-dir` with no marketplace install needed, confirmed with a
  rigorous negative control (an identical run against a copy of this repo with
  only `hooks/hooks.json` removed produced zero ledger activity) plus independent
  corroboration via Claude Code's own plugin-usage tracking in `~/.claude.json`.
  `hooks/delegator-hooks.json` and its manual-merge instructions in
  `hooks/README.md` stay in place unchanged for classic `install.sh` installs,
  which still don't wire hooks automatically.
- **Storage moved out of the workspace entirely, per-session (BREAKING change
  from v1.1.x's flat `.delegator/` inside the workspace)**: auto-registered hooks
  fire in *every* project the user touches, not just delegator campaigns, so a
  workspace-tree location was never going to be safe long-term — zero repo
  pollution, nothing to gitignore or accidentally commit, was the bar. Campaign
  state now lives under Claude Code's own per-project storage, one directory per
  delegator session (same lifetime model as Claude Code's own `<session-id>.jsonl`
  transcripts — persists across resume and crash, never a session-temp location):
  ```
  ~/.claude/projects/<workspace-slug>/delegator/
    |-- sessions.json          {session_id: home_session_id} routing map,
    |                          written ONLY by a delegator, never by the hooks
    +-- <home-session-id>/     one dir per campaign, named by the session id
        |-- registry.json      that started it
        +-- events.jsonl
  ```
  `home_session_id` is the delegator's own `$CLAUDE_CODE_SESSION_ID` at campaign
  start; the delegator's own charter is responsible for writing its `sessions.json`
  entry and creating its own campaign directory (out of scope for this change —
  `agents/delegator.md` is being aligned separately).
- **Routing, not a directory-existence guard**: `hooks/ledger.py` resolves the
  project directory from `transcript_path` on hook stdin (its parent dir *is* the
  project dir — live-probed present on every event type observed: SessionStart,
  UserPromptSubmit, PreToolUse, SubagentStart, SubagentStop, PostToolUse, Stop,
  SessionEnd; falls back to slug-encoding `cwd` only if a future event type ever
  lacks it), then looks up the event's own `session_id` in that project's
  `delegator/sessions.json`. Mapped → write only inside that session's own
  directory. Not mapped, or no `delegator/` for this project, or the map is
  unreadable → return immediately, write and create **nothing**. `hooks/watchdog.py`
  got the same routing (it has no hook stdin, so it always slug-encodes the
  workspace path it's given) plus the ability to scan every campaign under one
  project when no specific session is requested. Neither script ever calls
  `os.makedirs`/`os.mkdir`, under any circumstance, including a registered
  campaign's own first-ever event — if a write ever races ahead of its directory
  existing, it fails open (the event is silently dropped) rather than create
  anything; this is a deliberate invariant, not an oversight.
- **Slug encoding, live-probed, not assumed**: every `/`, `.`, and `_` in the
  absolute workspace path becomes `-`; every other character (including a literal
  `-` already present) is left alone. Confirmed against real `~/.claude/projects/`
  entries plus a deliberately constructed path containing both `.` and `_`. Not
  injective — distinct paths differing only in those four characters at the same
  position can collide onto an identical slug; the `transcript_path` branch above
  (the common case) never hits this, since it reads Claude Code's own resolved
  path rather than recomputing one.
- **Isolation proven live**, in a scratch `$HOME` (never the real one), across
  the full probe set: a registered session's events land only in its own
  directory, byte-for-byte, with zero cross-contamination from a second
  concurrently-registered session or from any unregistered session in the same
  workspace; the workspace tree itself stayed byte-identical before/after in
  every scenario tested, including a real multi-agent campaign through the
  classic manual-hooks path (5 distinct agents, correctly folded). A deliberate
  race test (session registered, its directory *not* pre-created, then a real
  hook event fired) confirmed the fail-open behavior: no crash, no directory
  created, the event just silently dropped.
- **Stdout silence audited**: `hooks/ledger.py` has zero `print()` calls on any
  path — confirmed by inspection and by capturing real session output around it
  (`--include-hook-events` shows all three hook firings with empty stdout).
  `hooks/watchdog.py` is not registered in `hooks/hooks.json` or
  `hooks/delegator-hooks.json` at all — it's armed directly by a running
  delegator as a background process, never hook-invoked — so its alert lines are
  a deliberate, scoped output (confined to campaigns that are actually
  registered), not an auto-firing token cost.
- **Migration note (manual, no auto-migration code shipped)**: a v1.1.x
  workspace with an existing flat `.delegator/registry.json`/`events.jsonl` can
  move it by hand — pick a session id to own it as its new home (an existing one
  if you want to keep appending under a live campaign, or any fresh UUID
  otherwise), then `mkdir -p ~/.claude/projects/<your-workspace-slug>/delegator/<that-id>`,
  move both files there, and add `{"<that-id>": "<that-id>"}` to (or create)
  `~/.claude/projects/<your-workspace-slug>/delegator/sessions.json`. Delete the
  old `.delegator/` from the workspace afterward — the hooks no longer look there
  at all.
- **One empirical finding worth flagging past this change's own scope**: plain
  `claude --resume <session-id>` (without `--fork-session`) was probed and does
  **not** assign a new session id by default — the resumed session keeps the
  exact same id. The two-id (`current` vs `home`) distinction this design
  anticipates only actually arises via the separate, non-default `--fork-session`
  flag. The routing code above is correct either way (it's a plain map lookup,
  indifferent to how session ids get assigned), but whoever finishes the
  delegator charter's resume-handling logic should know the "re-upsert
  `sessions.json` after every resume" step is much less frequently load-bearing
  than a design built around "resume always changes the id" would assume.
- **`hooks/ledger.py`'s `_normalize_existing()` gained a 4th recognized registry
  shape, `{"agents": [...]}`** (a LIST under `"agents"`, distinct from this
  script's own dict-under-`"agents"` canonical shape) — found live: a real
  post-campaign registry landed in exactly this shape, which the fold didn't
  recognize yet and fell through to the same empty-default clobber the original
  dual-shape bug (v1.1.0 entry below) was supposed to have closed for good.
  Fixed the same way as the other three tolerated shapes: merge onto existing
  entries by `agent_id`, round-trip in the same list-under-`"agents"` shape
  (never silently convert it to the dict shape or vice versa), preserve every
  judgment field the fold doesn't itself produce, and round-trip malformed/
  no-`agent_id` items untouched as passthrough. Fault-injected directly against
  the real `fold_registry()`: a hand-written entry's judgment fields (`purpose`,
  `handoff_file`) survived a fold that also correctly updated its mechanical
  fields (`status`, `last_summary`) from a matching ledger event, a brand-new
  agent_id from the ledger was added correctly, and a malformed passthrough
  item (no `agent_id`) round-tripped byte-for-byte — all in one registry,
  written back as a list, never converted to a dict. The canonical shape going
  forward is `{"version":1,"agents":{<agent_id>: {...}}}` (a dict, keyed by
  agent_id) — already the fold's native/default shape for a fresh or
  never-written registry; the other three shapes (including this new one) exist
  purely for backward-compatible tolerance with hand-written variations this
  hook doesn't control, not because any of them is preferred.
- **Unrecognized registry shapes now fail open as NO-WRITE, not fold-from-empty**:
  even with 4 shapes recognized, a registry could still show up in a 5th, truly
  alien structure this hook has never seen (e.g. a delegator variant writing
  `{"campaigns": {...}}`). The old fallback treated anything unrecognized as an
  empty dict — harmless for a genuinely fresh/never-written registry, but for an
  EXISTING alien-shaped file it meant a normal fold would silently discard
  whatever real content was there and replace it with a fresh
  `{"agents": {...}}` containing only that one event's data — the same clobber
  class as the two shape bugs above, just one level further out. `fold_registry()`
  now skips the fold entirely (file left completely untouched, no crash, no log
  line — stdout stays silent per the existing contract) whenever the existing
  file's structure matches none of the 4 known shapes. Extended the identical
  reasoning to a case not explicitly called out but sharing the same rationale:
  a pre-existing registry.json that fails to parse as JSON at all (a corrupt or
  partially-written file) is now ALSO a no-write skip rather than being treated
  as empty and silently overwritten. A genuinely fresh or never-written registry
  is unaffected — it's still recognized distinctly (an empty `{}`, or no file at
  all) and still gets created correctly on the first fold. Fault-injected all
  four cases directly against `fold_registry()`: the shape-4 case again (still
  clean), a `{"campaigns": {...}}` alien-shape file (byte-identical before/after,
  confirmed via sha256), a truncated/corrupt-JSON file (same, byte-identical),
  and a genuinely absent registry.json (still correctly created in the canonical
  dict shape) — all four in one pass, no regressions.

### `.claude-plugin/plugin.json`

- Version bumped to 1.2.0.

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
