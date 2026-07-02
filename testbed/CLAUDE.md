# Delegation testbed workspace

Router skill: /advisor

This workspace is a self-contained demo framework for the delegation architecture in this repo. The skills here are TEST FIXTURES: they deliberately mandate nested subagent spawning (fan-out, a two-level chain, and an approval gate) so the architecture can be exercised and measured end-to-end.

Gate policy for tests: the top session answers skill gates itself as user-proxy — approve unless the findings look fabricated. Agents running skills must still ASK per the skill; never skip a gate.

Run artifacts (census-report.md, audit-report.md, .delegator/, .cleanhome/) are outputs — gitignored.
