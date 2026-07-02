# hooks/ — opt-in event ledger, derived registry, dead-man watchdog

Everything here is **opt-in**. None of it is wired into `.claude-plugin/plugin.json`,
so installing the `delegation-kit` plugin does not enable it — you turn it on per
workspace or per user by loading `delegator-hooks.json` explicitly. This matches a
probe-confirmed gotcha (`docs/roadmap-v2.md` N1): bare *project*-level hooks were
observed to be silently skipped in at least one configuration, so both paths below
load the hooks at the **user** level (`~/.claude/settings.json`) or via `--settings`
— never assume a project-level `.claude/settings.json` alone is enough.

**Portability: stdlib-only Python, no shell dependencies.** `ledger.py` and
`watchdog.py` import only `datetime`/`fcntl`/`json`/`os`/`sys`/`time` — no `jq`, no
`flock(1)`, no GNU coreutils, no third-party packages. This is deliberate: the
operator deploys on macOS, where stock has none of `jq`/`flock(1)`/GNU `timeout`.
`fcntl` (used for the lock) is POSIX and ships in stock Python 3 on both macOS and
Linux — those are the two supported platforms. **The original `ledger.sh` +
`fold-registry.py` + `watchdog.sh` shell/jq versions have been removed** — the
Python files are a straight behavioral port (same fields, same 400-char truncation,
same ~5MB rotation, same anomaly types and output format), not a rewrite; see each
file's module docstring for the one deliberate fix made while porting (a lost-update
race in the registry fold, closed by moving the read inside the lock).

## What this proves (probe-verified, Claude Code 2.1.198)

A temporary catch-all dump hook was installed for 11 candidate event names around a
single named-subagent spawn (`Agent({subagent_type:"orchestrator", name:"probe-child", ...})`).
Observed to actually fire, with exact field names (nothing here is guessed):

| event | key fields present |
|---|---|
| `SessionStart` | `session_id`, `transcript_path`, `cwd`, `source` |
| `UserPromptSubmit` | + `prompt_id`, `permission_mode`, `prompt` |
| `PreToolUse` | + `tool_name`, `tool_input` (e.g. `{name, subagent_type, description, prompt, run_in_background}` for `Agent`), `tool_use_id` |
| `SubagentStart` | `agent_id`, `agent_type` (no name yet — see below) |
| `SubagentStop` | `agent_id`, `agent_type`, `agent_transcript_path`, `last_assistant_message`, `stop_hook_active` |
| `PostToolUse` | `tool_name`, `tool_input`, `tool_response` (`{agentId, agentType, content[], resolvedModel, totalTokens, ...}` for `Agent`), `duration_ms` |
| `Stop` | `last_assistant_message`, `stop_hook_active`, `background_tasks`, `session_crons` |
| `SessionEnd` | `reason` |

`TeammateIdle` was **accepted by the settings schema** (registering it produced no
validation error) but **did not fire** in this probe — expected, since a one-shot
`claude -p` process exits at completion and a named child never sits genuinely idle
mid-session. It's wired below defensively (the ledger only reads fields common to
every event; it never assumes a TeammateIdle-specific field that was never observed).
`Notification` and `PreCompact` also didn't fire (no permission prompt / no
compaction in a 2-turn run) — not wired here; add them the same way if a future
consumer needs them.

**Hook stdin carries no timestamp** — confirmed empty across all 8 payloads above;
`ledger.py` injects `ts` itself (`datetime.now(timezone.utc)`, formatted to match
`date -u +%Y-%m-%dT%H:%M:%SZ`).

**No timestamp needed for the workspace root either**: every payload carries `.cwd`,
and the hook's own environment carries a matching `CLAUDE_PROJECT_DIR` — both
verified identical to the shell's actual `$PWD` at hook-execution time. `ledger.py`
uses `.cwd` from stdin first, `$CLAUDE_PROJECT_DIR` as fallback.

**The `agent-<id>.meta.json` sidecar is real**, not hypothetical: for the probed
agent it contained exactly `{"agentType":"orchestrator","description":"...","name":"probe-child","toolUseId":"...","spawnDepth":1}`,
at `<session-transcript-path-minus-.jsonl>/subagents/agent-<agent_id>.meta.json`.
This is the authoritative source for `name` and `depth` — `SubagentStart`/`Stop`
never carry the human-readable name, only `PostToolUse` does (and only once the
child has already finished), so the sidecar is what lets the registry show a name
for an agent that's still running.

## Enable it

**Option A — user-level settings (persists across sessions):**

```bash
DELEGATOR_REPO=/path/to/claude-code-delegator   # your actual clone path
python3 - "$DELEGATOR_REPO" <<'PY'
import json, os, sys
repo = os.path.abspath(sys.argv[1])
frag_path = os.path.join(repo, "hooks", "delegator-hooks.json")
frag = json.load(open(frag_path))
# substitute the repo path placeholder in every command string
def sub(v):
    if isinstance(v, str):
        return v.replace("__DELEGATOR_REPO__", repo)
    if isinstance(v, list):
        return [sub(x) for x in v]
    if isinstance(v, dict):
        return {k: sub(x) for k, x in v.items()}
    return v
frag = sub(frag)

settings_path = os.path.expanduser("~/.claude/settings.json")
settings = {}
if os.path.isfile(settings_path):
    settings = json.load(open(settings_path))
settings.setdefault("hooks", {}).update(frag["hooks"])
json.dump(settings, open(settings_path, "w"), indent=2)
print("merged hooks into", settings_path)
PY
```

**Option B — per-invocation, no permanent change:**

```bash
DELEGATOR_REPO=/path/to/claude-code-delegator
sed "s#__DELEGATOR_REPO__#$DELEGATOR_REPO#g" "$DELEGATOR_REPO/hooks/delegator-hooks.json" > /tmp/delegator-hooks.resolved.json
claude --settings /tmp/delegator-hooks.resolved.json --agent delegator
```

`--settings <file-or-json>` loads *additional* settings on top of whatever
user/project settings already apply — it does not replace them (`claude --help`).

The cleanroom test harness (`testbed/cleanroom.sh`) resolves and installs this
automatically into the fake HOME it builds, so every cleanroom run exercises the
real ledger — see the "Prove it" run in `docs/testbed-results.md` / the N1 section
of `docs/roadmap-v2.md` for the reproduction command.

## What gets written

- `.delegator/events.jsonl` — one compact JSON line per observed event, in the
  **workspace** (the campaign's cwd), not this repo. Truncates any string field over
  400 chars, rotates the file to `events.jsonl.<UTC-timestamp>.bak` at ~5MB, appends
  under an `fcntl.flock` (2-second acquire timeout, polled — Python has no native
  blocking-with-timeout flock). Never blocks or fails the tool call it observes
  (`ledger.py` always exits 0, including on a lock-acquire timeout: it just skips
  that one event rather than wait indefinitely).
- `.delegator/registry.json` — re-folded from the ledger in the same process, right
  after the append (`ledger.py`'s `fold_registry()`), keyed by `agent_id`: `{name,
  agent_type, depth, description, status: active|stopped|unknown, first_seen,
  last_event, last_event_type, session_id, last_summary}`. `status` and liveness
  (`last_event`) come from the ledger; `name`/`agent_type`/`depth`/`description`
  prefer the harness's own `meta.json` sidecar when it's readable. The read-existing
  → merge → write of this file happens under one `fcntl.flock` acquisition (a fix
  made while porting from the original two-process shell/jq design, which read the
  existing registry *before* taking its write lock — letting two concurrent folds
  both merge onto the same stale snapshot and the second writer silently discard the
  first's update). The fold tolerates the registry being in ANY pre-existing shape —
  this script's own `{"agents": {...}}` dict, the delegator's hand-written
  `{"version":N,"orchestrators":[...]}` list, or a bare top-level list — merging by
  `agent_id` and always writing back in whichever shape was already on disk (never
  silently converting one to the other); a shape-naive earlier version of this fold
  was confirmed live to CLOBBER a list-shaped file outright (`existing.get("agents",
  {})` on a dict with no `"agents"` key returns the empty default, not an error, so
  the old fail-open contract alone didn't catch it) — see `_normalize_existing()`'s
  docstring in `ledger.py` for the full account.

### Open question this raises for `agents/delegator.md`

`agents/delegator.md`'s Registry section calls the delegator itself **"the ONLY
writer"** of `.delegator/registry.json`, holding hand-curated fields this hook never
produces (`purpose`, `cwd`, `handoff_file`, `staleness_flags`). `ledger.py`'s
`fold_registry()` is deliberately **merge-aware** — per `agent_id`, it only sets the
mechanical keys it derives and leaves every other key untouched — so a concurrent
delegator write and a hook-driven fold are additive rather than destructive. That's
a pragmatic compromise, not a full concurrency fix (the delegator's own write path
isn't itself lock-protected), and it means delegator.md's "ONLY writer" claim is no
longer strictly true once this hook is enabled. Whether delegator.md should be
updated to describe registry.json as hook-derived-plus-annotated (letting the
delegator only ever *patch* judgment fields onto existing rows) is a decision for
whoever owns that charter — flagged here rather than decided unilaterally.

## Dead-man watchdog (N2)

`watchdog.py` (stdlib `json`/`datetime`, no `jq`) reads `.delegator/events.jsonl`
and prints one line per anomaly:

```
WATCHDOG: <type> <agent> <evidence>
```

It does not integrate with `Monitor` yet (that's future work) — for now, the
delegator arms it itself as a background `Bash` job at session start:

```bash
DELEGATOR_REPO=/path/to/claude-code-delegator
nohup python3 "$DELEGATOR_REPO/hooks/watchdog.py" "$PWD" >> .delegator/watchdog.log 2>&1 &
```

Run it in the foreground for a one-off check instead:

```bash
python3 "$DELEGATOR_REPO/hooks/watchdog.py" "$PWD"
```

Anomaly types it currently detects — both read straight from `.delegator/events.jsonl`,
so they only ever fire once the ledger above is enabled:

- `STALE_AGENT` — an agent whose `last_event_type` is `SubagentStart` (i.e. it never
  reached `SubagentStop`/`PostToolUse`) with no ledger row in the last `$STALE_MIN`
  minutes (default 20, matching the render-threshold figure in the roadmap).
- `UNANSWERED_GATE` — a `last_summary` containing a gate marker (`gate`/`GATE`/`SendMessage me`)
  with no later event for that `session_id` afterward.

Backoff/re-fire scheduling and a `Monitor`-native version are out of scope for this
pass (see roadmap N2 "why now" — the current script is intentionally ~40 lines).
