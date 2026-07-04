#!/usr/bin/env python3
"""Focused self-test for LOOP_AGENT detection (github issue #4). Stdlib-only,
no network, no framework: `python3 hooks/test_watchdog_loop.py` -> PASS/FAIL.
Covers the core detector (detect_trailing_loop) + transcript locator
(find_agent_transcript). Deliberately small -- the mechanism, not exhaustive."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import watchdog  # noqa: E402


def _write_transcript(path, tool_calls):
    """tool_calls: list of (name, input_dict) -> one assistant tool_use per line."""
    with open(path, "w") as f:
        for name, inp in tool_calls:
            f.write(json.dumps({
                "message": {"role": "assistant", "content": [
                    {"type": "tool_use", "name": name, "input": inp}
                ]}
            }) + "\n")


def run():
    fails = []

    def check(label, cond):
        print(("PASS" if cond else "FAIL"), label)
        if not cond:
            fails.append(label)

    with tempfile.TemporaryDirectory() as d:
        # 1. Trailing run of identical calls >= threshold -> flagged.
        p = os.path.join(d, "loop.jsonl")
        _write_transcript(p, [("check-status-gate", {"action": "create"})] * 6)
        hit = watchdog.detect_trailing_loop(p, threshold=5)
        check("6 identical calls -> (tool, 6)", hit == ("check-status-gate", 6))

        # 2. Same tool, DIFFERENT args each time -> not a loop.
        p = os.path.join(d, "varied.jsonl")
        _write_transcript(p, [("Bash", {"command": "echo %d" % i}) for i in range(8)])
        check("8 varied-arg calls -> None", watchdog.detect_trailing_loop(p, threshold=5) is None)

        # 3. Below threshold -> None.
        p = os.path.join(d, "short.jsonl")
        _write_transcript(p, [("Read", {"file_path": "/x"})] * 3)
        check("3 identical (< threshold 5) -> None", watchdog.detect_trailing_loop(p, threshold=5) is None)

        # 4. Loop must be at the TAIL: identical block then a different call -> None.
        p = os.path.join(d, "recovered.jsonl")
        _write_transcript(
            p,
            [("check-status-gate", {"action": "create"})] * 6
            + [("check-status-gate", {"action": "plan"})],
        )
        check("loop then a different call -> None (recovered)", watchdog.detect_trailing_loop(p, threshold=5) is None)

        # 5. Transcript locator resolves <project>/<session>/subagents/agent-<id>.jsonl.
        proj = os.path.join(d, "proj")
        sub = os.path.join(proj, "sess-1", "subagents")
        os.makedirs(sub)
        open(os.path.join(sub, "agent-a123.jsonl"), "w").close()
        got = watchdog.find_agent_transcript(proj, "a123", "sess-1")
        check("find_agent_transcript direct path", got and got.endswith("agent-a123.jsonl"))
        check("find_agent_transcript missing -> None", watchdog.find_agent_transcript(proj, "nope", "sess-1") is None)

    print("\n%s (%d checks, %d failed)" % ("ALL PASS" if not fails else "FAILURES", 6, len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(run())
