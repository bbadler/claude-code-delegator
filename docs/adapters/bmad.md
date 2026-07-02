# Adapter: BMAD workspace

Drop this into the `CLAUDE.md` of a BMAD-method workspace to wire the delegator into the framework:

```markdown
Router skill: /bmad-help

Delegator policy for this workspace:
- Route every NEW work item through /bmad-help (fresh unnamed router agent); skip only for explicit-skill requests or direct continuations of an already-routed item.
- The executor orchestrator must invoke the EXACT bmad-* skill the router recommended — for real, via the Skill tool, executing every step including the skill's own nested subagent spawns.
- BMAD artifact policy: update existing artifacts before creating new ones; never fork parallel copies of PRD/architecture/story files.
- Gate policy: BMAD HALT/[C]/A-P-C gates are answered by the delegator as user-proxy when the operator's prior decisions cover them; target substitutions always surface.
```

Notes:
- `bmad-help` natively behaves as a router (probe-verified: one-shot `{skill, args, why, confidence}` at ~48k tokens): it reads the skill catalog and recommends the next `bmad-*` skill.
- BMAD skills direct their own nested spawning (reviewers, verifiers, party-mode agents). Per the depth budget contract, the orchestrator invokes the skill at depth 1 and leaves depths 2–4 to the skill.
- Suggested orchestrator naming: `orch-bmad-<scope>-<shortid>` (e.g. `orch-bmad-login-0702`) — remember the harness does not tell agents their own name; the brief must open with "You are <name>".
