---
name: census
description: Produce a census report of the data/ directory — file counts by extension, largest files, and a synthesis. Use for any "what's in the data directory / counts / types / sizes" task in this workspace.
---

Produce `census-report.md` at the workspace root. This skill REQUIRES fan-out — do NOT inline the analysis yourself even though it looks small; the mandated fan-out is part of this skill's contract.

1. Spawn exactly TWO unnamed subagents in parallel (two Agent calls in ONE message):
   - **counter** — brief: "You are counter. Count the files in <workspace>/data by extension. End your final message with the single line: `RESULT: COUNTS={\"md\": N, \"txt\": N, \"py\": N, \"json\": N, \"total\": N}` (only extensions that exist)."
   - **sizer** — brief: "You are sizer. Find the 3 largest files in <workspace>/data by bytes. End your final message with the single line: `RESULT: LARGEST=[{\"file\": \"name\", \"bytes\": N}, ...]`."
2. Children launch ASYNC (you get launch metadata + an output_file path, not results). Collect BOTH in-turn: poll each child's output_file with a narrow grep for its `RESULT:` sentinel inside a bounded wait (e.g. `timeout 60 bash -c 'until grep -q "RESULT:" <file>; do sleep 2; done'`). Do not end your turn while a child is outstanding.
3. Write `census-report.md`: a counts table, the largest files, and a one-paragraph synthesis.
4. End your own report with the line: `RESULT: CENSUS-DONE total=<total files>`
