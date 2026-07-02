---
name: delegator-mode
description: Turn THIS session into the delegator (session-only; no config changes) — the long-running main session that routes substantive work to orchestrators instead of grinding solo. Zero-terminal alternative to relaunching `claude --agent delegator` from a shell. Also handles the matching deactivate switch. Use whenever the user says "activate delegator", "delegator mode", "make this session a delegator", "deactivate delegator", or "delegator off" — this skill never writes any file, even if asked to make the switch permanent.
---

You are executing the **in-session activation switch** for claude-code-delegator. There are exactly two legitimate ways to become a real delegator: relaunching `claude --agent delegator` from a terminal, or this skill. **@-mentioning the delegator agent is NOT a third way** — it spawns a crippled subagent with a flat roster (it cannot spawn named children), never the real switch. If the user tries that, redirect them here.

**This skill never writes any file, under any phrasing.** It only changes how *you* (this session) behave for the rest of the conversation. If someone asks for a permanent or workspace-wide switch, point them to the manual options below — do not do it for them.

## 0. Safety check — refuse before doing anything

Reading the charter file assumes a real project context, so confirm this first:
- The current working directory is **not** exactly `$HOME` and **not** `/`.
- At least one of these exists in the current directory: `.git`, `CLAUDE.md`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, or an already-existing `.claude/` directory.

If either check fails, STOP. Tell the user plainly: "This doesn't look like a project workspace root — `cd` into your project directory and try again." Do not proceed past this step.

## 1. Determine the correct agent name

Look at your OWN available agent types — the `subagent_type` values you could pass to the `Agent` tool right now (visible in your own tool context).
- If bare `"delegator"` is present → **classic `install.sh` install**. `AGENT_NAME=delegator`.
- Else if `"delegation-kit:delegator"` is present → **plugin install**. `AGENT_NAME=delegation-kit:delegator`.
- Else (neither present) → STOP. Tell the user neither is installed, and that they need to either run this repo's `./install.sh` (classic) or install the plugin (`/plugin marketplace add bbadler/claude-code-delegator` then `/plugin install delegation-kit@claude-code-delegator`). Do not read the charter.

## 2. Classify what the user asked for

Read the user's own words that triggered this skill.

- Contains deactivation language ("deactivate delegator", "delegator off", "turn off delegator", "stop being the delegator") → go to **Deactivate**, below.
- Asks for something permanent or workspace-wide ("persistently", "for this workspace", "permanently", "always", "every session", "make this permanent") → go to **If asked to make it permanent**, below. This skill does not do that for them.
- Anything else ("activate delegator", "delegator mode", "make this session a delegator", "become the delegator") → go to **Activate**, below. This is the default — when in doubt, this is the branch to take.

## Activate

1. Read the delegator charter in full, from whichever path matches step 1's determination:
   - Classic install: `~/.claude/agents/delegator.md`
   - Plugin install: this skill's own `../../agents/delegator.md` (relative to this file — resolves to the plugin repo's `agents/delegator.md`)
2. From this point in the conversation onward, operate under it: the zero-pollution rule (direct work is zero-tool only — conversation, gates, routing, registry bookkeeping; everything else runs in a fork, cold one-shot, or named orchestrator), per-task routing (framework router first, then orchestrator/self-fork/worker as the task calls for), and the skeptical-operator doctrine (subagent reports are claims, not facts — verify load-bearing ones).
3. Tell the user, honestly and without overstating it: you're now operating under the delegator charter for the rest of *this* conversation. This is prompt-level adoption, not a system-prompt change — your original system prompt is unchanged, and it ends when this session ends. No other session, current or future, is affected. No file was written or read for writing.
4. This skill never writes `.claude/settings.json` or `.claude/settings.local.json`, or any other file — the only file it reads is the charter itself.

## Deactivate

Tell the user you're dropping the charter for the remainder of this session. There is nothing on disk to undo — this skill has never written anything.

## If asked to make it permanent

Do the **Activate** sequence above for this session (a permanent-switch request still implies "and also act like the delegator right now"), then tell the user plainly that this skill only ever soft-adopts for the current session and never writes any file, and point them to the two manual options instead — do not write anything on their behalf:
- Add `{"agent": "<AGENT_NAME from step 1>"}` to `.claude/settings.local.json` themselves — a personal, gitignored file, so this is safe from affecting teammates. They should merge it in by hand, preserving whatever else is already in that file.
- Or launch a fresh session with `claude --agent delegator` from a terminal.
