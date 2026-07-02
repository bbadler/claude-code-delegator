---
name: deep-audit
description: Audit data/facts.md for factual errors with independently verified findings and an approval gate. Use for any "fact-check / audit / find the errors in the facts file" task in this workspace.
---

Produce `audit-report.md` at the workspace root. This skill exercises a TWO-LEVEL nested spawn chain plus an approval gate — follow it exactly; do not flatten the chain.

1. Spawn ONE unnamed subagent, the **auditor**, briefed to:
   a. Read `<workspace>/data/facts.md` and list every claim it suspects is factually false.
   b. For EACH suspect claim spawn ONE unnamed **verifier** subagent (one level deeper) briefed to check that claim against `<workspace>/data/ground-truth.md` and end with the single line: `RESULT: VERDICT={"claim": "...", "false": true|false, "correction": "..."}`
   c. Verifier children launch ASYNC — collect them in-turn (poll each output_file for its `RESULT:` sentinel with a bounded wait), then end with the single line: `RESULT: AUDIT=[<only the confirmed-false claims, each with its correction>]`
2. Collect the auditor in-turn the same way (its work includes its own children, so allow a generous bounded wait, e.g. 240s).
3. **GATE (mandatory):** before writing the report, ask your spawner for approval to publish the findings — SendMessage to your spawner and wait for the reply. If you ARE the top session, decide yourself and record the decision.
4. On approval, write `audit-report.md`: each confirmed-false claim, its correction, and the verifier evidence.
5. End your own report with the line: `RESULT: AUDIT-DONE false_claims=<n>`
