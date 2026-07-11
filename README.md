<div align="center">

# claude-code-delegator

**Three agent definitions that turn Claude Code into a long-running delegation session** — a main "delegator" that routes work to subagents instead of grinding solo, with skeptical verification, ask-don't-interpret, research-first, and a no-lazy-shortcuts quality bar baked into the agent instructions themselves.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-%E2%89%A5%202.1.172-8A2BE2)](https://code.claude.com/docs/en/sub-agents)
[![Plugin](https://img.shields.io/badge/plugin-delegation--kit-blue)](#-quick-start)

</div>

## What this is

The whole concept lives in **three Markdown files** in [`agents/`](agents/):

- **`delegator.md`** — the main session. Routes every task to a subagent, keeps its own context clean, answers gates, owns commits. Launch it with `claude --agent delegator`.
- **`orchestrator.md`** — the workhorse type. Runs a substantive multi-step task the way a good main session would: delegates aggressively, invokes skills for real, verifies before "done".
- **`worker.md`** — a lean leaf for bounded mechanical jobs.

That's the product. Install those (or the plugin), and Claude Code delegates properly — no other moving parts, nothing to break, no token cost beyond the prompt itself.

## ⚡ Quick start

**As a plugin:**

```
/plugin marketplace add bbadler/claude-code-delegator
/plugin install delegation-kit@claude-code-delegator
```

**Or classic install:**

```bash
git clone https://github.com/bbadler/claude-code-delegator && cd claude-code-delegator
./install.sh          # copies agents/*.md into ~/.claude/agents/ + the delegator-mode skill
```

**Then, in a workspace:**

```bash
claude --agent delegator
```

It asks you **interactive vs autonomous** once (sticky for the campaign), then routes your work to **unnamed orchestrator-type subagents** — which have stock completion semantics, so they report back reliably and can't silently stall.

**No terminal (desktop / VS Code)?** Say `activate delegator` in any chat — the bundled `delegator-mode` skill adopts the charter for that session only (zero config writes).

## How it works

- **Zero-pollution.** The delegator does only zero-tool work directly — conversation, routing, gates, commits. Every tool-touching job runs in a subagent (or a self-fork) that absorbs the output, so the main context stays clean across a long campaign.
- **The mandate lives in the agent type**, not in each prompt — so a subagent can't "forget" to delegate. `orchestrator.md`'s own system prompt makes it fan out.
- **Unnamed-first.** Substantive work runs in unnamed `subagent_type: "orchestrator"` agents. They finish with a completion notification (no silent idle), gate mid-task via `SendMessage(to:"main")`, and revive from their transcript via `SendMessage(agentId)` — all native Claude Code mechanics.
- **Skeptical-operator doctrine.** Subagent reports are *claims*, not facts: load-bearing ones get spot-checked, irreversible actions require independent verification, and lazy resolutions (stubs, error-swallowing, silent scope cuts) are named and forbidden.
- **Amendments ride the native task board.** Changing an in-flight task = `TaskUpdate` its description/metadata; the agent re-reads via `TaskGet` at phase boundaries. No custom machinery.

## 🧩 The problems it solves

| pain | what the charter does |
|---|---|
| Subagents that won't delegate — you hand one the Agent tool and a big task; it grinds solo until it's lost | the delegation mandate lives in the *type's* system prompt ([`orchestrator.md`](agents/orchestrator.md)) — no per-prompt briefing can forget it |
| One session drowning over a long project | the hands rule: the delegator keeps conversation + judgment + small bounded probes; everything exploratory or bulky runs in subagents |
| Agents that confidently do the wrong thing | ask-don't-interpret + fork escalation + a research-first ladder; genuine forks go up with options, not silent guesses |
| Unattended runs that bulldoze with shortcuts | a quality bar that forbids lazy resolutions, plus audited *Judgment calls* in autonomous mode |

## 🧪 Optional: advanced enforcement hooks

Everything in [`optional/`](optional/) is **not needed for the core** — it's mechanical insurance for long, unattended runs (an event ledger, a stall/loop watchdog, force-continue gates, and a cleanroom test suite). Most of it existed to babysit *named* teammates, which the default no longer uses. The one piece native signals genuinely can't cover — detecting a child stuck in a silent tool-call loop — lives there too. See [`optional/README.md`](optional/README.md).

## 🗃️ Repo map

| path | what it is |
|---|---|
| [`agents/`](agents/) | **the product** — `delegator.md` · `orchestrator.md` · `worker.md` |
| [`skills/`](skills/) | `delegator-mode` — the zero-terminal "activate delegator" switch |
| [`docs/`](docs/) | design notes (TH), roadmap, BMAD adapter |
| [`optional/`](optional/) | advanced enforcement hooks + test harness (not needed for the core) |
| [`install.sh`](install.sh) | classic installer (`--verify` / `--uninstall` / `--skill-only`) |

## 🤝 Prior art

[gruckion/nested-subagent](https://github.com/gruckion/nested-subagent) · the swarm-orchestration SKILL gist by kieranklaassen · [claudefa.st's nested subagents guide](https://claudefa.st/blog/guide/agents/nested-subagents). This repo's contribution is the mandate-in-the-type fix, the skeptical-operator doctrine, and unnamed-first routing that leans on native completion semantics instead of bolted-on stall machinery.

## License

MIT — see [LICENSE](LICENSE).
</content>
