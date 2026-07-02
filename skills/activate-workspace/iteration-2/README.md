## iteration-2 — operator cut: persistent mode removed entirely

Supersedes `iteration-1`. The operator's final call: the skill must NEVER write any
settings file, under any phrasing, including "permanently"/"for this workspace"
requests — those get a spoken pointer to the two manual alternatives instead. This
removed `scripts/manage_settings.py` and shrank the eval set from 4 scenarios to 3
(`evals/evals.json`, current version). `iteration-1`'s recorded runs describe the
now-removed persistent-write behavior and are kept only as a historical record of the
design's evolution (see `CHANGELOG.md`'s v1.1.0 entry) — they are not a regression
baseline for the current skill.

All 3 current evals were run live via `--plugin-dir` + `--add-dir` against this repo,
no `Bash`-permission workaround needed this time (the skill no longer shells out to
anything — it only reads the charter file and replies). See each `eval-*/grading.json`
for the graded assertions with verbatim evidence.
