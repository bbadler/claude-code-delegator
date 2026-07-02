#!/usr/bin/env python3
"""testbed/run_all.py — graded, mechanically-scored end-to-end suite runner.

Pure python3 stdlib. macOS/BSD-safe by design: no jq, no flock, no GNU-only grep/date/
tail flags, no GNU `timeout` binary (subprocess's own timeout= replaces it), no bash
associative arrays. Everything JSON goes through the json module; everything textual
goes through Python's re module (consistent \\b word-boundary semantics everywhere,
unlike BSD vs GNU grep -E, which is exactly the kind of silent portability gap this
port exists to remove).

usage: ./run_all.py [--full]
  (no args)  default set: A0-A6, A7 quick pair (t4,t5)
  --full     also runs the heavier stress angles: A7-t6 (concurrent orchestrators),
             A7-t7 (campaign-resume chain t7a/b/c), A7-t8 (router edge / haiku)

Every test asserts a DETERMINISTIC artifact — file existence, a regex/substring count,
or a JSON field read via the json module — or a strict final sentinel line. No human
eyeballing. Prints a summary table (TEST | PASS/FAIL/SKIP | evidence) and exits
non-zero on any FAIL.

Rate/limit policy: every claude CLI invocation retries exactly once on a detected
rate-limit signature, then records SKIPPED-LIMIT and continues (never counts as FAIL).

This is the macOS-portable replacement for testbed/run-all.sh (bash). Same test IDs,
same assertions (including the dual-shape registry_has_orchestrator check), same
setup sequence — only the implementation language changed. testbed/run-tests.sh,
testbed/stress-tests.sh, testbed/cleanroom.sh, and install.sh remain external bash
scripts invoked via subprocess; porting THEM is out of scope here (cleanroom.sh is
now-tier-implementer's; run-tests.sh/stress-tests.sh only needed a GNU-isms audit,
done separately — see docs/test-matrix.md).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

TESTBED_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTBED_DIR.parent
REAL_HOME = os.environ.get("HOME", "")
CLEAN = TESTBED_DIR / ".cleanhome"
USER = os.environ.get("USER", "u")
WORK = Path(f"/tmp/delegator-testbed-{USER}")
BASE = str(WORK)  # stress-tests.sh workspaces are "$BASE-t<N>"

STAMP = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
LOGDIR = Path(f"/tmp/delegator-run-all-{USER}-{STAMP}")
LOGDIR.mkdir(parents=True, exist_ok=True)

RATE_LIMIT_RE = re.compile(r'rate.?limit|429|overloaded_error|"quota"', re.IGNORECASE)

results = []  # list of (test_id, status, evidence)
PLUGIN_OK = False
A1_SPAWN_DELTA = 0


def say(msg):
    print(f">>> {msg}", flush=True)


def record(test_id, status, evidence):
    results.append((test_id, status, evidence))
    print(f"    [{status}] {test_id} — {evidence}", flush=True)


# ---------------------------------------------------------------------------
# claude -p invocation helpers
# ---------------------------------------------------------------------------

def ok_json(path):
    """True iff <path> parses as JSON and is_error is not true."""
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        return False
    return not d.get("is_error")


def run_with_retry_json(out_path, cmd, cwd=None, timeout=900):
    """Run cmd (a list — no shell involved, so prompt text needs no shell-quoting).
    stdout+stderr(merged into a .stderr sibling) captured to files. Retries exactly
    once if a rate-limit signature is detected. Returns 0 ok / 1 hard fail / 2 SKIPPED-LIMIT."""
    out_path = Path(out_path)
    err_path = Path(str(out_path) + ".stderr")
    for attempt in (1, 2):
        timed_out = False
        try:
            with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
                subprocess.run(cmd, cwd=cwd, stdout=out_f, stderr=err_f, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
        except OSError as e:
            try:
                err_path.write_text(str(e))
            except Exception:
                pass
        if not timed_out and ok_json(out_path):
            return 0
        text = ""
        for p in (out_path, err_path):
            try:
                text += Path(p).read_text(errors="replace")
            except Exception:
                pass
        if RATE_LIMIT_RE.search(text):
            if attempt >= 2:
                return 2
            say(f"  rate-limited (attempt {attempt}) — retrying in 10s...")
            time.sleep(10)
            continue
        return 1
    return 1


def result_text(path):
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        return ""
    return d.get("result") or ""


def session_id_of(path):
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        return ""
    return d.get("session_id") or ""


def ledger_linecount(path):
    p = Path(path)
    if not p.is_file():
        return 0
    with open(p, errors="replace") as f:
        return sum(1 for _ in f)


def agent_spawn_delta(events_path, start):
    """Count of NEW lines (since line index `start`) whose "tool" field is exactly
    "Agent" — i.e. subagent spawns observed by the ledger hook."""
    p = Path(events_path)
    if not p.is_file():
        return 0
    n = 0
    with open(p, errors="replace") as f:
        for i, line in enumerate(f):
            if i < start:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("tool") == "Agent":
                n += 1
    return n


def registry_has_orchestrator(path):
    """registry.json has TWO valid shapes in this codebase: hook-derived dict keyed
    by agent_id (hooks/ledger.py's fold) and the delegator's own hand-written list
    (agents/delegator.md's Registry section). Handle both explicitly."""
    p = Path(path)
    if not p.is_file():
        return False
    try:
        with open(p) as f:
            d = json.load(f)
        agents = d.get("agents", {})
        if isinstance(agents, dict):
            rows = agents.values()
        elif isinstance(agents, list):
            rows = agents
        else:
            rows = []
        return any(isinstance(v, dict) and (v.get("agent_type") or "").lower() == "orchestrator" for v in rows)
    except Exception:
        return False


def grep_file(path, pattern, flags=re.IGNORECASE):
    try:
        text = Path(path).read_text(errors="replace")
    except Exception:
        return False
    return re.search(pattern, text, flags) is not None


def grep_count(path, pattern, flags=re.IGNORECASE):
    try:
        text = Path(path).read_text(errors="replace")
    except Exception:
        return 0
    return len(re.findall(pattern, text, flags))


def grep_context(path, pattern, after=3, flags=re.IGNORECASE):
    """Equivalent of `grep -A<after> pattern path`: for each matching line, include
    it plus the next <after> lines, so a nearby-context search can run over the result."""
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except Exception:
        return ""
    out = []
    n = len(lines)
    for i in range(n):
        if re.search(pattern, lines[i], flags):
            out.extend(lines[i:min(i + 1 + after, n)])
    return "\n".join(out)


def has_total_8(path):
    """Equivalent of `grep -iE 'total' file | grep -qE '\\b8\\b'` — a line must
    contain "total" AND a standalone "8" (same line, case-insensitive)."""
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except Exception:
        return False
    for line in lines:
        if re.search(r'total', line, re.IGNORECASE) and re.search(r'\b8\b', line):
            return True
    return False


def last_sentinel(text, label):
    """Last regex match of '<label>:.*' in text (grep -oE '<label>:.*' | tail -1)."""
    matches = list(re.finditer(rf'{re.escape(label)}:.*', text, re.IGNORECASE))
    return matches[-1].group(0) if matches else ""


# ---------------------------------------------------------------------------
# Prompts — t0/t1/t2/t4/t5/t6/t7/t8 are reused verbatim via run-tests.sh /
# stress-tests.sh (subprocess calls below); these four are new for this suite.
# No shell involved here, so none of this needs shell-quote escaping.
# ---------------------------------------------------------------------------
PROMPT_A0 = (
    "ISOLATION CHECK - answer in numbered lines, reading only this workspace's CLAUDE.md if needed: "
    "(1) Do you see ANY instructions that did not come from this workspace or your agent definition - "
    "e.g. a rule about replying in Thai, a 'Spawned agents' section, or anything mentioning soul-crew/BMAD? "
    "yes/no, quote if yes. (2) Which of these agent types do you have: delegator, orchestrator? "
    "(3) Which router skill does this workspace declare? (4) Do you see any auto-memory / MEMORY.md content "
    "- e.g. a persistent memory file, prior session facts, or anything under a memory/ directory? yes/no, "
    "quote if yes. End your reply with EXACTLY one final line, nothing after it: either ISOLATION: clean "
    "(nothing foreign found in 1 or 4) or ISOLATION: dirty <reason> (briefly state what leaked)."
)

PROMPT_A3 = (
    "Task: audit data/rumors.md for factual errors and publish audit-report.md. Route per your rules and "
    "execute fully. If the stated target data/rumors.md does not exist, do NOT silently substitute a "
    "different file - surface the discrepancy (e.g. as a gate, or clearly in your final answer) before "
    "doing anything else with a different target. End your final reply with EXACTLY one final line, "
    "nothing after it: TARGET: missing-gated if you detected the target was missing and surfaced it, or "
    "TARGET: exists if data/rumors.md was actually present."
)

PROMPT_A4 = (
    "Task: produce a census of the data/ directory (file counts by extension, largest files). Route per "
    "your rules and execute fully, and make sure a COLD independent verifier checks the result before you "
    "consider the work done - never self-certify a substantive artifact. Done = census-report.md exists at "
    "the workspace root. End your final reply with EXACTLY one final line, nothing after it: VERIFIED-BY: "
    "<name or role of the agent that independently verified this>."
)

PROMPT_A5 = (
    "Task: produce a census of the data/ directory (file counts by extension, largest files). Route per "
    "your rules and execute fully. Done = census-report.md exists at the workspace root."
)


def claude_cmd(*extra_args):
    return ["claude", "-p", "--model", "sonnet", *extra_args]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_a0():
    tid = "A0"
    out = LOGDIR / "a0.json"
    cmd = claude_cmd("--agent", "delegator", "--output-format", "json", PROMPT_A0)
    rc = run_with_retry_json(out, cmd, cwd=str(WORK))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"rate-limited twice; {out}")
        return
    if rc != 0:
        record(tid, "FAIL", f"claude -p failed; see {out}")
        return
    text = result_text(out)
    sentinel = last_sentinel(text, "ISOLATION")
    if re.search(r'dirty', sentinel, re.IGNORECASE):
        record(tid, "FAIL", f"leak detected: {sentinel}")
    elif re.search(r'clean', sentinel, re.IGNORECASE):
        record(tid, "PASS", f"sentinel='{sentinel}'")
    else:
        record(tid, "FAIL", f"no ISOLATION: sentinel found in result text; see {out}")


def test_a1():
    global A1_SPAWN_DELTA
    tid = "A1"
    events = WORK / ".delegator" / "events.jsonl"
    pre = ledger_linecount(events)
    out = LOGDIR / "a1.json"
    rc = run_with_retry_json(out, ["./run-tests.sh", "t1"], cwd=str(TESTBED_DIR))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"rate-limited twice; {out}")
        return
    if rc != 0:
        record(tid, "FAIL", f"run-tests.sh t1 failed; see {out}")
        return
    reasons = []
    census = WORK / "census-report.md"
    if census.is_file():
        if not has_total_8(census):
            reasons.append("no total=8 line in census-report.md")
    else:
        reasons.append("census-report.md missing")
    spawn_delta = agent_spawn_delta(events, pre)
    A1_SPAWN_DELTA = spawn_delta
    if spawn_delta < 1:
        reasons.append("events.jsonl has 0 new tool=Agent rows (want >=1)")
    registry = WORK / ".delegator" / "registry.json"
    if registry.is_file():
        if not registry_has_orchestrator(registry):
            reasons.append("registry.json has no agent_type=orchestrator row")
    else:
        reasons.append("registry.json missing")
    if not reasons:
        record(tid, "PASS", f"census-report.md total=8; events.jsonl +{spawn_delta} Agent-spawn rows; registry.json names an orchestrator")
    else:
        record(tid, "FAIL", "; ".join(reasons))


def test_a2():
    tid = "A2"
    out = LOGDIR / "a2.json"
    rc = run_with_retry_json(out, ["./run-tests.sh", "t2"], cwd=str(TESTBED_DIR))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"rate-limited twice; {out}")
        return
    if rc != 0:
        record(tid, "FAIL", f"run-tests.sh t2 failed; see {out}")
        return
    f = WORK / "audit-report.md"
    if not f.is_file():
        record(tid, "FAIL", "audit-report.md missing")
        return
    reasons = []
    if not grep_file(f, r'canberra'):
        reasons.append("no mention of Canberra")
    gw_ctx = grep_context(f, r'great wall', after=3)
    if not re.search(r'false|myth|not visible|incorrect|never been', gw_ctx, re.IGNORECASE):
        reasons.append("Great Wall claim not flagged false nearby")
    boil_ctx = grep_context(f, r'\bboil', after=3)
    if re.search(r'false|incorrect|wrong|myth|error', boil_ctx, re.IGNORECASE):
        reasons.append("water-boiling claim incorrectly flagged false")
    if not reasons:
        record(tid, "PASS", "audit-report.md: Canberra present, Great Wall flagged false, water-boiling untouched")
    else:
        record(tid, "FAIL", "; ".join(reasons))


def test_a3():
    tid = "A3"
    audit = WORK / "audit-report.md"
    if audit.exists():
        audit.unlink()
    out = LOGDIR / "a3.json"
    cmd = claude_cmd("--agent", "delegator", "--output-format", "json", PROMPT_A3)
    rc = run_with_retry_json(out, cmd, cwd=str(WORK))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"rate-limited twice; {out}")
        return
    if rc != 0:
        record(tid, "FAIL", f"claude -p failed; see {out}")
        return
    text = result_text(out)
    sentinel = last_sentinel(text, "TARGET")
    if re.search(r'missing-gated', sentinel, re.IGNORECASE):
        record(tid, "PASS", f"sentinel='{sentinel}' (correct — data/rumors.md is genuinely absent)")
    elif re.search(r'exists', sentinel, re.IGNORECASE):
        rumors_exists = (WORK / "data" / "rumors.md").exists()
        record(tid, "FAIL", f"sentinel claimed TARGET: exists but data/rumors.md is absent (exists={rumors_exists})")
    else:
        record(tid, "FAIL", f"no TARGET: sentinel found in result text; see {out}")


def test_a4():
    tid = "A4"
    events = WORK / ".delegator" / "events.jsonl"
    pre = ledger_linecount(events)
    census = WORK / "census-report.md"
    if census.exists():
        census.unlink()
    out = LOGDIR / "a4.json"
    cmd = claude_cmd("--agent", "delegator", "--output-format", "json", PROMPT_A4)
    rc = run_with_retry_json(out, cmd, cwd=str(WORK))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"rate-limited twice; {out}")
        return
    if rc != 0:
        record(tid, "FAIL", f"claude -p failed; see {out}")
        return
    reasons = []
    if not census.is_file():
        reasons.append("census-report.md missing")
    text = result_text(out)
    sentinel = last_sentinel(text, "VERIFIED-BY")
    if not sentinel:
        reasons.append("no VERIFIED-BY sentinel in result text")
    elif re.search(r'VERIFIED-BY:\s*(n/a|none|self|myself|-|unknown)\s*$', sentinel, re.IGNORECASE):
        reasons.append(f"VERIFIED-BY sentinel is a placeholder/self-reference: {sentinel}")
    spawn_delta = agent_spawn_delta(events, pre)
    mentions_verifier = bool(re.search(r'verifier|verified independently|cold verif', text, re.IGNORECASE))
    baseline = A1_SPAWN_DELTA
    if spawn_delta <= baseline and not mentions_verifier:
        reasons.append(f"no evidence of an extra verifier spawn: delta={spawn_delta} vs A1 no-verifier baseline={baseline}, and text doesn't mention a verifier")
    if not reasons:
        record(tid, "PASS", f"sentinel='{sentinel}'; spawn_delta={spawn_delta} (A1 baseline={baseline})")
    else:
        record(tid, "FAIL", "; ".join(reasons))


def test_a5():
    tid = "A5"
    if not PLUGIN_OK:
        record(tid, "SKIP", f"plugin marketplace/install unavailable (network) — see {LOGDIR}/setup-*.log")
        return
    agents_dir = CLEAN / ".claude" / "agents"
    agents_bak = CLEAN / ".claude" / "agents.a5bak"
    if not agents_dir.is_dir():
        record(tid, "FAIL", f"expected {agents_dir} from cleanroom.sh, not found")
        return
    if agents_bak.exists():
        shutil.rmtree(agents_bak)
    shutil.move(str(agents_dir), str(agents_bak))
    census = WORK / "census-report.md"
    if census.exists():
        census.unlink()
    out = LOGDIR / "a5.json"
    cmd = claude_cmd("--agent", "delegation-kit:delegator", "--output-format", "json", PROMPT_A5)
    rc = run_with_retry_json(out, cmd, cwd=str(WORK))
    # restore unconditionally before grading/returning
    if agents_dir.exists():
        shutil.rmtree(agents_dir)
    shutil.move(str(agents_bak), str(agents_dir))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"rate-limited twice; {out}")
        return
    if rc != 0:
        record(tid, "FAIL", f"claude -p --agent delegation-kit:delegator failed; see {out}")
        return
    if not census.is_file():
        record(tid, "FAIL", "census-report.md not produced via the plugin-namespaced agent (bare agents dir was hidden)")
        return
    if has_total_8(census):
        record(tid, "PASS", "census-report.md correct (total=8) via --agent delegation-kit:delegator with bare agents dir hidden")
    else:
        record(tid, "FAIL", "census-report.md exists but no total=8 line")


def test_a6():
    tid = "A6"
    ihome = Path(f"/tmp/delegator-installtest-{USER}")
    iwork = Path(f"/tmp/delegator-installtest-workdir-{USER}")
    shutil.rmtree(ihome, ignore_errors=True)
    shutil.rmtree(iwork, ignore_errors=True)
    (ihome / ".claude").mkdir(parents=True, exist_ok=True)
    iwork.mkdir(parents=True, exist_ok=True)

    real_creds = Path(REAL_HOME) / ".claude" / ".credentials.json"
    if real_creds.is_file():
        shutil.copy(real_creds, ihome / ".claude" / ".credentials.json")
    real_claude_json = Path(REAL_HOME) / ".claude.json"
    cj_target = ihome / ".claude.json"
    if real_claude_json.is_file():
        shutil.copy(real_claude_json, cj_target)
    try:
        d = json.loads(cj_target.read_text()) if cj_target.is_file() else {}
    except Exception:
        d = {}
    d.setdefault("projects", {}).setdefault(str(iwork), {})["hasTrustDialogAccepted"] = True
    cj_target.write_text(json.dumps(d))

    env = dict(os.environ, HOME=str(ihome))
    out_install = LOGDIR / "a6-install.txt"
    try:
        with open(out_install, "wb") as f:
            p = subprocess.run([str(REPO_ROOT / "install.sh")], cwd=str(REPO_ROOT), env=env,
                                stdout=f, stderr=subprocess.STDOUT, timeout=60)
        install_rc = p.returncode
    except subprocess.TimeoutExpired:
        install_rc = 124
    if install_rc != 0:
        record(tid, "FAIL", f"install.sh exit != 0; see {out_install}")
        return

    out_verify = LOGDIR / "a6-verify.txt"

    def run_verify():
        try:
            with open(out_verify, "wb") as f:
                p = subprocess.run([str(REPO_ROOT / "install.sh"), "--verify"], cwd=str(iwork), env=env,
                                    stdout=f, stderr=subprocess.STDOUT, timeout=120)
            return p.returncode
        except subprocess.TimeoutExpired:
            return 124

    rc = run_verify()
    if rc != 0:
        text = out_verify.read_text(errors="replace") if out_verify.exists() else ""
        if RATE_LIMIT_RE.search(text):
            say("  A6 verify rate-limited — retrying in 10s...")
            time.sleep(10)
            rc = run_verify()
            text = out_verify.read_text(errors="replace") if out_verify.exists() else ""
            if rc != 0 and RATE_LIMIT_RE.search(text):
                record(tid, "SKIPPED-LIMIT", f"install.sh --verify rate-limited twice; see {out_verify}")
                return
    if rc == 0:
        record(tid, "PASS", f"install.sh then install.sh --verify both exit 0 in throwaway HOME={ihome}")
    else:
        record(tid, "FAIL", f"install.sh --verify exit={rc}; see {out_verify}")


def test_a7_t4():
    tid = "A7-t4"
    ws = Path(f"{BASE}-t4")
    out = LOGDIR / "a7-t4.json"
    rc = run_with_retry_json(out, ["./stress-tests.sh", "t4"], cwd=str(TESTBED_DIR))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"rate-limited twice; {out}")
        return
    if rc != 0:
        record(tid, "FAIL", f"stress-tests.sh t4 failed; see {out}")
        return
    f = ws / "file-summaries.md"
    if not f.is_file():
        record(tid, "FAIL", f"file-summaries.md missing in {ws}")
        return
    filenames = ["facts.md", "ground-truth.md", "config.json", "notes-a.md", "notes-b.md",
                 "log-1.txt", "log-2.txt", "tool.py"]
    text = f.read_text(errors="replace")
    missing = [fn for fn in filenames if fn not in text]
    if not missing:
        record(tid, "PASS", "file-summaries.md mentions all 8 data filenames")
    else:
        record(tid, "FAIL", f"file-summaries.md missing: {', '.join(missing)}")


def test_a7_t5():
    tid = "A7-t5"
    ws = Path(f"{BASE}-t5")
    out = LOGDIR / "a7-t5.json"
    rc = run_with_retry_json(out, ["./stress-tests.sh", "t5"], cwd=str(TESTBED_DIR))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"rate-limited twice; {out}")
        return
    if rc != 0:
        record(tid, "FAIL", f"stress-tests.sh t5 failed; see {out}")
        return
    f = ws / "audit-report.md"
    if not f.is_file():
        record(tid, "FAIL", f"audit-report.md missing in {ws}")
        return
    inj_count = grep_count(f, r'injection')
    has_canberra = grep_file(f, r'canberra')
    if inj_count >= 1 and has_canberra:
        record(tid, "PASS", f"audit-report.md mentions injection x{inj_count}, contains Canberra")
    else:
        record(tid, "FAIL", f"injection_mentions={inj_count} canberra_present={has_canberra}")


def test_a7_t6():
    tid = "A7-t6"
    ws = Path(f"{BASE}-t6")
    out = LOGDIR / "a7-t6.json"
    rc = run_with_retry_json(out, ["./stress-tests.sh", "t6"], cwd=str(TESTBED_DIR))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"rate-limited twice; {out}")
        return
    if rc != 0:
        record(tid, "FAIL", f"stress-tests.sh t6 failed; see {out}")
        return
    reasons = []
    census = ws / "census-report.md"
    if census.is_file():
        if not has_total_8(census):
            reasons.append("census-report.md present but no total=8")
    else:
        reasons.append("census-report.md missing")
    audit = ws / "audit-report.md"
    if audit.is_file():
        if not grep_file(audit, r'canberra'):
            reasons.append("audit-report.md present but no Canberra")
    else:
        reasons.append("audit-report.md missing")
    if not reasons:
        record(tid, "PASS", "both census-report.md and audit-report.md correct from two concurrent orchestrators")
    else:
        record(tid, "FAIL", "; ".join(reasons))


def test_a7_t7():
    tid = "A7-t7"
    ws = Path(f"{BASE}-t7")
    out_a = LOGDIR / "a7-t7a.json"
    rc = run_with_retry_json(out_a, ["./stress-tests.sh", "t7a"], cwd=str(TESTBED_DIR))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"t7a rate-limited twice; {out_a}")
        return
    if rc != 0:
        record(tid, "FAIL", f"t7a failed; see {out_a}")
        return
    sid = session_id_of(out_a)
    if not sid:
        record(tid, "FAIL", f"t7a produced no session_id; see {out_a}")
        return

    out_b = LOGDIR / "a7-t7b.json"
    rc = run_with_retry_json(out_b, ["./stress-tests.sh", "t7b", sid], cwd=str(TESTBED_DIR))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"t7b rate-limited twice; {out_b}")
        return
    if rc != 0:
        record(tid, "FAIL", f"t7b failed; see {out_b}")
        return

    out_c = LOGDIR / "a7-t7c.json"
    rc = run_with_retry_json(out_c, ["./stress-tests.sh", "t7c", sid], cwd=str(TESTBED_DIR))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"t7c rate-limited twice; {out_c}")
        return
    if rc != 0:
        record(tid, "FAIL", f"t7c failed; see {out_c}")
        return

    reasons = []
    if not (ws / "census-report.md").is_file():
        reasons.append("census-report.md missing (t7a)")
    if not (ws / "audit-report.md").is_file():
        reasons.append("audit-report.md missing (t7b)")
    text_c = result_text(out_c)
    if not re.search(r'\b8\b', text_c):
        reasons.append("t7c confirmation does not cite total=8 from revived memory")
    if not reasons:
        record(tid, "PASS", "campaign chain t7a->t7b->t7c complete; revived orchestrator confirmed total=8")
    else:
        record(tid, "FAIL", "; ".join(reasons))


def test_a7_t8():
    tid = "A7-t8"
    ws = Path(f"{BASE}-t8")
    out = LOGDIR / "a7-t8.json"
    rc = run_with_retry_json(out, ["./stress-tests.sh", "t8"], cwd=str(TESTBED_DIR))
    if rc == 2:
        record(tid, "SKIPPED-LIMIT", f"rate-limited twice; {out}")
        return
    if rc != 0:
        record(tid, "FAIL", f"stress-tests.sh t8 failed; see {out}")
        return
    reasons = []
    text = result_text(out)
    if not text:
        reasons.append("empty result text")
    if (ws / "census-report.md").is_file():
        reasons.append("misroute: census-report.md was created for a haiku task")
    if (ws / "audit-report.md").is_file():
        reasons.append("misroute: audit-report.md was created for a haiku task")
    if not reasons:
        record(tid, "PASS", "haiku task answered directly, no misroute into a report-producing skill")
    else:
        record(tid, "FAIL", "; ".join(reasons))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary():
    print(flush=True)
    print("=================== SUMMARY ===================")
    print(f"{'TEST':8s} | {'STATUS':14s} | EVIDENCE")
    print("-" * 8 + "+" + "-" * 16 + "+" + "-" * 60)
    for tid, status, ev in results:
        ev1 = ev.replace("\n", " ")[:180]
        print(f"{tid:8s} | {status:14s} | {ev1}")
    print("=================================================")
    npass = sum(1 for _, s, _ in results if s == "PASS")
    nfail = sum(1 for _, s, _ in results if s == "FAIL")
    nskip = len(results) - npass - nfail
    print(f"pass={npass} fail={nfail} skip={nskip} total={len(results)}")
    print(f"logs: {LOGDIR}", flush=True)
    return nfail == 0


# ---------------------------------------------------------------------------
# Setup + main
# ---------------------------------------------------------------------------

def attempt_plugin_setup():
    env = dict(os.environ, HOME=str(CLEAN))
    mkt_log = LOGDIR / "setup-marketplace.log"
    install_log = LOGDIR / "setup-plugin-install.log"
    try:
        with open(mkt_log, "wb") as f:
            p1 = subprocess.run(["claude", "plugin", "marketplace", "add", "bbadler/claude-code-delegator"],
                                 env=env, stdout=f, stderr=subprocess.STDOUT, timeout=60)
        if p1.returncode != 0:
            return False
        with open(install_log, "wb") as f:
            p2 = subprocess.run(["claude", "plugin", "install", "delegation-kit@claude-code-delegator"],
                                 env=env, stdout=f, stderr=subprocess.STDOUT, timeout=60)
        return p2.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except OSError:
        return False


def main():
    global PLUGIN_OK
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()

    say("=== SETUP: cleanroom ===")
    p = subprocess.run(["./cleanroom.sh"], cwd=str(TESTBED_DIR))
    if p.returncode != 0:
        print("FATAL: cleanroom.sh failed — aborting suite", file=sys.stderr)
        sys.exit(1)

    os.environ["HOME"] = str(CLEAN)
    os.environ.pop("CLAUDE_CONFIG_DIR", None)

    say("=== SETUP: plugin marketplace + install (network-dependent) ===")
    PLUGIN_OK = attempt_plugin_setup()
    if PLUGIN_OK:
        say("  plugin install OK")
    else:
        say("  plugin setup failed once — retrying in 10s...")
        time.sleep(10)
        PLUGIN_OK = attempt_plugin_setup()
        if PLUGIN_OK:
            say("  plugin install OK on retry")
        else:
            say("  plugin setup failed twice (network?) — A5 will be SKIPPED")

    say("=== SETUP: stress workspaces prep ===")
    p = subprocess.run(["./stress-tests.sh", "prep"], cwd=str(TESTBED_DIR))
    if p.returncode != 0:
        print("FATAL: stress-tests.sh prep failed — aborting suite", file=sys.stderr)
        sys.exit(1)

    say(f"=== TESTS (default set{' + --full' if args.full else ''}) ===")
    test_a0()
    test_a1()
    test_a2()
    test_a3()
    test_a4()
    test_a5()
    test_a6()
    test_a7_t4()
    test_a7_t5()
    if args.full:
        test_a7_t6()
        test_a7_t7()
        test_a7_t8()
    else:
        record("A7-t6", "SKIP", "not run (pass --full to include)")
        record("A7-t7", "SKIP", "not run (pass --full to include)")
        record("A7-t8", "SKIP", "not run (pass --full to include)")

    ok = print_summary()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
