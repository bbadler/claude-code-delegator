# optional/ — advanced enforcement layer (NOT needed for the core)

**You do not need anything in this directory to use claude-code-delegator.**

The product is the three agent definitions in [`../agents/`](../agents/) — that is
the whole concept: a delegator main session that routes work to unnamed
orchestrator-type subagents, with skeptical verification, ask-don't-interpret,
research-first, and a quality bar. Install those (or the plugin) and you have a
working delegation system with zero moving parts.

Everything here is **optional insurance for long, unattended runs** — mechanical
enforcement for failure modes that the charter alone can only advise against. Most
of it exists to babysit *named* teammates, which the default routing no longer uses
(unnamed agents have stock completion semantics and cannot silently stall), so for
the default unnamed-first flow this layer is largely redundant.

| path | what it is | when you'd want it |
|---|---|---|
| `hooks/ledger.py` | event ledger → derived per-campaign registry | multi-hour campaigns where you want a durable roster across compaction/crash |
| `hooks/watchdog.py` | STALE_AGENT + **LOOP_AGENT** detection | the one genuinely-native-blind case: a child stuck in a silent tool-call loop (github #4) — the only piece here native signals truly can't cover |
| `hooks/stop_gate.py`, `hooks/idle_gate.py` | force-continue busy-presence gates | only meaningful if you go back to *named* teammates and need mechanical stall prevention |
| `testbed/` | cleanroom + graded probe suite | developing/validating the above |

To wire the hooks manually, see `hooks/README.md`. The plugin does **not** auto-wire
them from this location by design — the clean default ships the charter only.
