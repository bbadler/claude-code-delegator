---
name: menu-gate
description: Analyze the workspace data files, then let the user choose how to proceed. Use when asked to run a menu-gated analysis.
---

Analyze this workspace's data, then hand the decision to the user before you save anything.

1. Read the `.txt` files in this workspace's `data/` directory. From what you find, write a concise **3-bullet analysis** of what those files contain.

2. Present EXACTLY this menu to the user and WAIT for their choice before doing anything else:

**What would you like to do?**
[A] Advanced Elicitation - dive deeper into implications
[P] Party Mode - bring different perspectives
[C] Continue - save this analysis and finish

3. Once the user has chosen, act on their choice:
   - **[C] Continue** — write the 3-bullet analysis to `menu-gate-analysis.md` at the workspace root, then tell the user the analysis is saved and you are done.
   - **[A] Advanced Elicitation** — first add an **Advanced Elicitation** section that digs deeper into the implications of the analysis, then write `menu-gate-analysis.md` (including that section) and finish.
   - **[P] Party Mode** — first add a **Party Mode** section bringing different perspectives to bear on the analysis, then write `menu-gate-analysis.md` (including that section) and finish.

Do not skip the menu, and do not pick an option on the user's behalf — the choice in step 2 is theirs to make.
