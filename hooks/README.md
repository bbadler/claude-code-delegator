# hooks/ — event ledger, derived registry, dead-man watchdog

**Plugin installs get this automatically.** `hooks/hooks.json` auto-registers with
Claude Code the moment the `delegation-kit` plugin is enabled (confirmed live via
`--plugin-dir`, Claude Code 2.1.199 — see the v1.2.0 CHANGELOG entry for the probe
evidence). No separate step, no settings edit. **Classic `install.sh` users still
need the manual step under "Enable it manually" below** — `install.sh` only places
`agents/*.md` and the `delegator-mode` skill; it has never touched hook registration.

**Storage lives OUTSIDE the workspace entirely, per delegator session** — not a
`.delegator/` directory in your project (that was a v1.2.0-in-progress design,
superseded before release; see the CHANGELOG's migration note if you have one
from an even older v1.1.x flat layout). See "What gets written" below for the
exact layout. This is deliberate: auto-registered hooks now fire in *every*
project you touch, and the only way to guarantee zero repo pollution — nothing to
gitignore, nothing to ever accidentally commit — is to never write inside the
workspace tree at all.

**Why it's safe to run unconditionally in every project once the plugin is
installed**: both `ledger.py` and `watchdog.py` only ever write for a session that
is *explicitly registered* by a real delegator campaign (see "What gets written").
An ordinary chat, or any project that has never run a delegator campaign, resolves
to "not registered" and the hook returns having written and created nothing.
Neither script ever calls `os.makedirs`/`os.mkdir`, under any circumstance,
including a freshly-registered campaign's own first event — directory creation is
entirely the delegator charter's job, not the hooks'; a hook write that ever races
ahead of its directory existing just fails open (the event is silently dropped)
rather than create anything. This was live-probed, not just asserted: a registered
session's events land only in its own directory; an unregistered session in the
same workspace, run concurrently, contributes zero writes anywhere; the workspace
tree itself stays byte-identical before and after, in every scenario tested.

This matches a probe-confirmed gotcha (`docs/roadmap-v2.md` N1) that still applies to
the classic manual path: bare *project*-level hooks were observed to be silently
skipped in at least one configuration, so both options below load the hooks at the
**user** level (`~/.claude/settings.json`) or via `--settings` — never assume a
project-level `.claude/settings.json` alone is enough. Plugin-registered hooks are a
different activation mechanism (Claude Code wires them in directly once the plugin
is enabled) and this gotcha does not apply to them.

**Portability: stdlib-only Python, no shell dependencies.** `ledger.py` and
`watchdog.py` import only `datetime`/`fcntl`/`json`/`os`/`re`/`sys`/`time` — no `jq`,
no `flock(1)`, no GNU coreutils, no third-party packages. This is deliberate: the
operator deploys on macOS, where stock has none of `jq`/`flock(1)`/GNU `timeout`.
`fcntl` (used for the lock) is POSIX and ships in stock Python 3 on both macOS and
Linux — those are the two supported platforms. **The original `ledger.sh` +
`fold-registry.py` + `watchdog.sh` shell/jq versions have been removed** — the
Python files are a straight behavioral port (same fields, same 400-char truncation,
same ~5MB rotation, same anomaly types and output format), not a rewrite; see each
file's module docstring for the one deliberate fix made while porting (a lost-update
race in the registry fold, closed by moving the read inside the lock).

**Stdout silence** (matters now that hooks auto-fire on every tool call in every
project): `ledger.py` never prints anything, on any path, success or fail-open —
zero `print()` calls exist in the file, confirmed live by capturing real hook
telemetry (`--include-hook-events`) around it: every firing shows empty stdout.
`watchdog.py` is different by design — it is **not** registered in `hooks/hooks.json`
or `hooks/delegator-hooks.json` at all, so it never auto-fires; it's armed directly
by a running delegator as a background process, and its alert lines are the
entire point of running it. That output is a deliberate, scoped context injection
(confined to campaigns that are actually registered — see "Dead-man watchdog"
below), not a standing token cost like an auto-firing hook's stdout would be.

## What this proves (probe-verified, Claude Code 2.1.198 — original N1 probe)

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

**The `agent-<id>.meta.json` sidecar is real**, not hypothetical: for the probed
agent it contained exactly `{"agentType":"orchestrator","description":"...","name":"probe-child","toolUseId":"...","spawnDepth":1}`,
at `<session-transcript-path-minus-.jsonl>/subagents/agent-<agent_id>.meta.json`.
This is the authoritative source for `name` and `depth` — `SubagentStart`/`Stop`
never carry the human-readable name, only `PostToolUse` does (and only once the
child has already finished), so the sidecar is what lets the registry show a name
for an agent that's still running.

### v1.2.0 follow-up probe (Claude Code 2.1.199 — depth-2 nesting + storage addressing)

Run to settle exactly what the per-session storage design (below) could rely on,
using a real depth-2 spawn (top session → orchestrator → a further general-purpose
grandchild):

- **`session_id` is identical at every nesting depth.** The depth-2 grandchild's
  own `SubagentStart`/`SubagentStop` events carry the exact same `session_id` as
  the top-level session — confirmed by cross-referencing each event's `agent_id`
  against its `agent-<id>.meta.json` sidecar's `spawnDepth` (`1` and `2` both
  directly observed). One `sessions.json` entry correctly covers an entire
  campaign tree, no matter how deep it nests.
- **`transcript_path` is present on every event type observed** — SessionStart,
  UserPromptSubmit, PreToolUse, SubagentStart, SubagentStop, PostToolUse, Stop,
  SessionEnd — always pointing at the top-level session's own `.jsonl`, regardless
  of depth. `agent_transcript_path` (a *different* field) appears only on
  `SubagentStop`, giving the just-stopped agent's own per-agent transcript at
  `<top-level-transcript-dir>/subagents/agent-<agent_id>.jsonl` — real, and useful
  for other purposes, but not what the storage-addressing design below uses.
- **Project-dir slug encoding**: every `/`, `.`, and `_` in the absolute workspace
  path becomes `-`; every other character (including a literal `-` already
  present) is left alone. Triangulated from three sources: two real pre-existing
  `~/.claude/projects/` entries (cross-checked against their own transcripts'
  `cwd` field) plus a deliberately constructed workdir containing both `.` and
  `_`, run live and observed directly in its own `transcript_path`. **Not
  injective** — distinct paths differing only in those four characters at the
  same position can collide onto an identical slug; this is why `resolve_project_dir()`
  in both scripts prefers `transcript_path` (Claude Code's own resolved path)
  whenever it's available, and only falls back to recomputing the slug from `cwd`
  if it's ever absent.
- **`claude --resume <session-id>` does NOT get a new session id by default** —
  the resumed session keeps the exact same id; only the separate, non-default
  `--fork-session` flag produces a new one. See "Open question this raises for
  agents/delegator.md" below for what this means for the charter's resume-handling
  logic.

## Enable it manually (classic `install.sh` installs only)

Skip this whole section if you installed via the plugin — see the top of this file.

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
real ledger.

## What gets written

Nothing lives in the workspace. Everything is under Claude Code's own per-project
storage, one directory per delegator session:

```
~/.claude/projects/<workspace-slug>/delegator/
  |-- sessions.json          {session_id: home_session_id} routing map
  +-- <home-session-id>/     one dir per campaign, named by the session id that
      |-- registry.json      started it (persists across resume/crash, same
      +-- events.jsonl        lifetime as Claude Code's own <session-id>.jsonl)
```

- **`sessions.json`** is written ONLY by a real delegator — its own charter
  writes `{its-current-session-id: its-home-session-id}` at campaign start (a
  fresh campaign maps to itself), and would re-upsert on `--fork-session` (the
  one path that actually changes a session's id — see the resume finding above;
  plain `--resume` doesn't need a new entry since the id never changes). The hook
  scripts only ever *read* this file, never write it.
- **`<home-session-id>/events.jsonl`** — one compact JSON line per observed
  event, for a session that resolved to this campaign via the routing above.
  Truncates any string field over 400 chars, rotates the file to
  `events.jsonl.<UTC-timestamp>.bak` at ~5MB, appends under an `fcntl.flock`
  (2-second acquire timeout, polled — Python has no native blocking-with-timeout
  flock). Never blocks or fails the tool call it observes (`ledger.py` always
  exits 0, including on a lock-acquire timeout or a missing directory: it just
  skips that one event rather than wait indefinitely or create anything).
- **`<home-session-id>/registry.json`** — re-folded from that campaign's own
  ledger in the same process, right after the append (`ledger.py`'s
  `fold_registry()`), keyed by `agent_id`: `{name, agent_type, depth, description,
  status: active|stopped|unknown, first_seen, last_event, last_event_type,
  session_id, last_summary}`. `status` and liveness (`last_event`) come from the
  ledger; `name`/`agent_type`/`depth`/`description` prefer the harness's own
  `meta.json` sidecar when it's readable. The read-existing → merge → write of
  this file happens under one `fcntl.flock` acquisition (closing a lost-update
  race the original two-process shell/jq design had). The fold recognizes 4
  pre-existing shapes and merges by `agent_id`, always writing back in whichever
  shape was already on disk (never silently converting one to another):
  - `{"version":N,"agents":{<agent_id>: {...}}}` — the **canonical** shape
    (dict keyed by agent_id), also the default for a fresh/never-written
    registry. The delegator charter is being standardized on this one.
  - `{"version":N,"orchestrators":[...]}` — the delegator's original
    hand-written list shape.
  - a bare top-level list (no wrapper object at all).
  - `{"agents": [...]}` — a LIST under `"agents"`, distinct from the canonical
    dict-under-`"agents"` shape above; found live in a real post-campaign
    registry a delegator improvised.

  The last three exist purely for backward-compatible tolerance with
  hand-written variations this hook doesn't control, not because any of them
  is preferred. **Anything that doesn't match one of these 4 shapes — or a
  pre-existing file that fails to parse as JSON at all — is a NO-WRITE skip**:
  `fold_registry()` leaves the file completely untouched and returns, rather
  than treating unrecognized content as empty and silently overwriting it.
  Two real clobber bugs got fixed this way, at two different points: a
  shape-naive early version of this fold was confirmed live to CLOBBER a
  list-shaped file outright (`existing.get("agents", {})` on a dict with no
  `"agents"` key returns the empty default, not an error), and later the same
  class of bug reappeared for the 4th (`agents`-as-list) shape before it was
  explicitly recognized — both are exactly why unrecognized-but-real content
  now gets a no-write skip instead of a 5th blind spot. See
  `_normalize_existing()`'s docstring in `ledger.py` for the full account,
  including why a genuinely fresh/absent registry is NOT treated the same way
  (it's the one case where starting from empty is actually correct).
- **Routing** (`resolve_project_dir` + `resolve_home_session_id` in `ledger.py`;
  see each function's docstring): the project dir is read from `transcript_path`
  on hook stdin (present on every observed event type, its parent dir *is* the
  project dir — see the v1.2.0 probe above), falling back to slug-encoding `cwd`
  only if that's ever absent. The event's `session_id` is then looked up in
  `<project-dir>/delegator/sessions.json`; unmapped, or no `delegator/` for this
  project, or an unreadable map, all mean the same thing — return immediately,
  write and create nothing.

### Open question this raises for `agents/delegator.md`

`agents/delegator.md`'s Registry section calls the delegator itself **"the ONLY
writer"** of its `registry.json`, holding hand-curated fields this hook never
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

Separately, and specific to v1.2.0's storage move: the charter needs to (1) write
its own `sessions.json` entry and create its own `<home-session-id>/` directory
eagerly at campaign start (the hooks never create either — see "Storage lives
OUTSIDE the workspace" above), and (2) decide how much resume-handling logic is
actually worth building given the empirical finding above that plain `--resume`
never changes the session id — the "re-upsert on every resume" step this design
originally anticipated is only load-bearing for the separate, non-default
`--fork-session` path.

## Dead-man watchdog (N2)

`watchdog.py` (stdlib `json`/`datetime`/`re`, no `jq`) reads one campaign's
`events.jsonl` (or every campaign under a project, if you don't name one — see
below) and prints one line per anomaly:

```
WATCHDOG: <type> <agent> <evidence>                        (single campaign)
WATCHDOG: [<home-session-id>] <type> <agent> <evidence>     (scanning more than one)
```

It is not registered as a hook anywhere (see "Stdout silence" above) and does not
integrate with `Monitor` yet (that's future work) — for now, the delegator arms it
itself as a background `Bash` job at session start, passing its own workspace and
(recommended) its own home session id so it only ever watches its own campaign:

```bash
DELEGATOR_REPO=/path/to/claude-code-delegator
nohup python3 "$DELEGATOR_REPO/hooks/watchdog.py" "$PWD" 20 "$HOME_SESSION_ID" \
  >> /tmp/delegator-watchdog-"$HOME_SESSION_ID".log 2>&1 &
```

Run it in the foreground for a one-off check instead — omit the third argument to
scan every campaign that has ever run in this workspace:

```bash
python3 "$DELEGATOR_REPO/hooks/watchdog.py" "$PWD"                    # every campaign here
python3 "$DELEGATOR_REPO/hooks/watchdog.py" "$PWD" 20 "$HOME_SESSION_ID"  # just this one
```

Anomaly types it currently detects — both read straight from a campaign's
`events.jsonl`, so they only ever fire once that campaign has real ledger activity:

- `STALE_AGENT` — an agent whose `last_event_type` is `SubagentStart` (i.e. it never
  reached `SubagentStop`/`PostToolUse`) with no ledger row in the last `$STALE_MIN`
  minutes (default 20, matching the render-threshold figure in the roadmap).
- `UNANSWERED_GATE` — a `last_summary` containing a gate marker (`gate`/`GATE`/`SendMessage me`)
  with no later event for that `session_id` afterward.

Backoff/re-fire scheduling and a `Monitor`-native version are out of scope for this
pass (see roadmap N2 "why now" — the current script is intentionally small).
