# Long-Running Delegation Session — design v1 (critiqued + assembled + canary-proven)

> สถานะ 2026-07-02: **ประกอบเป็นของจริงแล้ว + พิสูจน์ด้วย probe ครบ** — รอ operator adopt (แล้วค่อยอัปเดต `~/.claude/CLAUDE.md` ตาม §7)
> ต่อยอดจาก `longrunning-delegator-design-handoff.md` (fork ของ session toonflow, 2026-07-02) — เอกสารนี้คือคำวิจารณ์ + design ฉบับจบ + หลักฐาน probe รอบสอง
> ของจริงที่ ship แล้ว: `~/.claude/agents/delegator.md` + `~/.claude/agents/orchestrator.md` (user-level → ใช้ได้ทุก workspace)

---

## §1 Verdict สั้น

Blueprint ใน handoff §6 **แกนถูก** (switch = agent def, mandate ในตัว orchestrator, registry+resume, framework-router) แต่มีจุดที่ผมแย้ง/แก้ 5 จุดใหญ่ (ดู §3) และ physics ลูกของ teammate ที่ต้องแก้ใน design ไม่ใช่แค่เตือนใน brief (collect-in-turn — ดู §4.1) หลังประกอบเสร็จ operator เถียงกลับ 3 รอบ — **probe ตัดสินให้ operator ถูกทั้ง 3** (§3 ข้อ 1, 2, 7) และ design ถูกแก้ตามแล้ว ทุกอย่างประกอบ + พิสูจน์แล้ว:

- switch เปิดทั้ง session: `claude --agent delegator` — flag มีจริง, def โหลดเป็น system prompt ของ main thread จริง (P-E)
- orchestrator เป็น **agent type จดทะเบียน** (`subagent_type:"orchestrator"`) — mandate อยู่ใน system prompt ของ type เอง ไม่ต้องพึ่ง brief; def เขียนปุ๊บ **hot-register เข้า session ที่รันอยู่ด้วย** (เห็นสดใน session นี้)
- willingness eval ผ่าน: orchestrator ถือ charter แตกงาน 3 ทางจริง, ไม่ over-spawn ของจิ๋ว, รายงานตาม protocol ครบ (P-C)
- main session (โมเดลเอง ไม่ใช่ user `/fork`) spawn fork ได้จริง (P-B) — ปิดข้อค้างสุดท้ายของ handoff §5
- router step ของชิ้น 4 ใช้ได้จริง: fresh agent invoke `bmad-help` คืน `{skill,args,why,confidence}` one-shot (P-F)

## §2 Probe ledger (รันจริงบนเครื่องนี้ 2026-07-02, Claude Code 2.1.198)

| # | คำถาม | ผล verbatim / หลักฐาน | ต้นทุน |
|---|---|---|---|
| P-A | flag `--agent` มีจริง? ของเก่าชนไหม? | `--agent <agent>  Agent for the current session. Overrides…`; `~/.claude/agents/` ว่าง; `bmad-help` อยู่ใน repo skills; **ไม่พบ /skill-creator บนเครื่อง** | ~0 |
| P-B | main session (โมเดลเอง) spawn fork ได้? | `MAIN-FORK-OK tokens=15000000 agent=yes s2_prompts=15` — fork ได้ budget สด 15M + Agent tool + inherit context จริง | 64k / 8s |
| P-E | def โหลดจริง + type จดทะเบียน? | headless `claude --agent delegator -p` ตอบ: `1. yes` (Agent tool) · `2. yes — "Full-power orchestrator — runs a substantive multi-step task"` · `3.` quote body delegator.md verbatim · `4. Claude Fable 5` | 1 คำสั่ง |
| — | hot-registration | หลัง Write defs, types `delegator`/`orchestrator` โผล่ใน Agent tool ของ session ที่รันอยู่ทันที (system event เห็นสด) | 0 |
| P-F | bmad-help เป็น router ได้? | `{"skill":"bmad-quick-dev","confidence":"high", …}` + friction: "instruction-driven (อ่าน catalog CSV เอง 1 tool call) ไม่ใช่ computed router — deterministic" | 48k / 44s |
| P-C | mandate ทำให้ "ยอม spawn" จริง? | PASS: spawn 3 lane-mappers (unnamed foreground) + delegation log; git branch ทำเอง (ไม่ over-spawn); snapshot + `14933725 tokens left` verbatim; เจอ Task tools หายก็รายงานตรง; จับ concurrent-worktree mutation ได้เอง | 66k+workers / 6.4m |
| P-G | งานจิ๋ว 1-2 tool calls ควร fork แทนทำเอง? (operator เถียงข้อ 3.1) | fork ทำ `git status`+Read จบตาม brief 1 บรรทัด; ราคา ≈ context ผู้ fork (cache-warm — baseline P-B 64k/8s); งานไม่หายแม้ process ตายกลางคัน (ดู P-H) | ~ctx |
| P-H | agent_id ตายพร้อม session? (operator เถียง: ไม่ตาย) | **operator ถูก**: process exit จริงกลาง P-G → resume เป็น session id ใหม่ → `SendMessage(agentId)` → harness `resumed from transcript`; agent ตอบ `P-H-REVIVED=yes brief_remembered=yes` + ส่งผล P-G ครบโดยไม่ต้องเล่า brief ใหม่ | 167k / 12s |
| P-I | teammate มีลูก named/background ได้ไหม? (operator เถียงข้อ foreground-only) | named child จาก named teammate โดน API ปฏิเสธ verbatim: `Teammates cannot spawn other teammates — the team roster is flat. To spawn a subagent instead, omit the name parameter.` — ขัดกับ Probe 5 ที่ผ่านวันเดียวกัน = **variance จริง** (memory 2026-06-19 flag ไว้แล้ว) → design ยึดฝั่ง blocked; orch-bgtest ไม่ rest บน premise ที่พัง — รายงานทันที (charter ทำงาน) | ~40k |
| P-I-b | named teammate → unnamed child: blocking ไหม? | **ASYNC ไม่ใช่ blocking**: `Async agent launched successfully… working in the background` + agentId; เก็บผลสำเร็จโดย poll output_file ของลูกในเทิร์นด้วย `grep -ao 'SCHEMAS=[0-9]+'` → `SCHEMAS=8` ตรง ground-truth; parent ไม่ rest เลย | 35k / 6s |
| P-K | ลูก SendMessage ปลุกพ่อ (teammate) ที่ rest ได้ไหม? (ไอเดีย operator จาก session ที่ 2) | **PASS สองฝั่ง**: พ่อ rest จริง (ไม่ poll) → ลูกหน่วง 25s แล้วยิง `SendMessage(to:"orch-bgtest")` สำเร็จ (`RESULT: P-K-SENT`) → พ่อตื่นด้วย message ของลูก (`P-K-WOKEN via=child-message got="P-K-WAKE hello parent"` — waker คือลูก ไม่ใช่ spawner) → refinement: "rest แล้วไม่มีใครปลุก" จริงเฉพาะ bare completion; explicit message ปลุกได้ → pattern ที่ 2 **rest-with-ping** | ~75k รวม |
| P-J | gate จากชั้นลึกได้ไหม? (operator เถียงข้อ depth: skill อนาคตอาจ gate หลายชั้น) | **PASS ครบ loop ยืนยันสองฝั่ง**: ลูก depth-2 `SendMessage(to:"main")` ถึง top session จริง → เด็ก rest (`P-J-CHILD-WAITING`) → top ตอบผ่าน agentId → เด็กฟื้นจาก transcript ปิดงาน `RESULT: P-J-ANSWERED=B`; parent (orch-bgtest) เก็บ sentinel ได้ในเทิร์นตลอด round-trip → กฎ "gate เฉพาะ depth 1" ถูกถอน; flat roster ห้ามแค่ SPAWN teammate ไม่ได้ห้าม message main; ของแถม: สูตรรอในเทิร์น `timeout N bash -c '<grep/sleep loop>'` (sleep ใต้ timeout ไม่โดน block) | ~70k รวม |

รวมกับ Probe 1-5 ใน handoff §5 (depth cap 5, L5 โดนถอด Agent tool, fork→fork ❌, named→self-fork ✅, notification bubbling, budget สด 15M/ตัว) = เมทริกซ์กลไกครบ ไม่มีข้อค้าง

## §3 คำตอบ 6 คำถามใน handoff §7.1 (วิจารณ์แบบไม่เกรงใจ)

1. **"delegator ห้ามทำเองทุกอย่าง" — ผมเสนอ size-gate (>2 tool calls/>5k tokens ค่อย delegate) แล้ว operator เถียงกลับ: งานจิ๋วก็ fork — OPERATOR ถูก (P-G/P-H) กติกาที่ ship คือ ZERO-POLLUTION** เหตุผลที่ heuristic ผมแพ้: (a) fork inherit context → brief 1 บรรทัด ไม่มี misunderstanding cost; (b) ราคาจริง ≈ อ่าน context ตัวเอง (prompt-cache warm = ถูก) + ~10s = "ถูกพอกัน" จริง; (c) tool output ถูก fork ดูดแทน — context delegator สะอาดสะสมทั้ง campaign ซึ่งคือสิ่งที่ผมประกาศเองว่าต้องปกป้อง แต่ heuristic ผมกลับยอมให้เปื้อน; (d) โบนัสที่ไม่มีใครเสนอไว้: งานใน agent รอด main-process crash (P-H พิสูจน์สดจากอุบัติเหตุจริง) งาน inline ตายพร้อมเทิร์น → กติกาสุดท้าย: delegator ทำ DIRECT เฉพาะ zero-tool (คุย/ตอบ gate/route/SendMessage) + registry/handoff bookkeeping (single-writer correctness) + final commit ของงานที่ review แล้ว; tool work อื่น**ทั้งหมด** → fork (ต้องใช้ context ตัวเอง) / cold one-shot (context-independent — ถูกกว่า fork เมื่อ context ใหญ่) / orchestrator (substantive)
2. **Registry JSON พอไหม vs TaskList — ใช้คู่ แยกหน้าที่** TaskList = สถานะงานสด (shared, รอด compaction, user เห็น — Probe 5); registry ไฟล์ = roster + วิธีชุบชีวิต; delegator เป็น **ผู้เขียนคนเดียว** (orchestrator ไม่รู้ชื่อตัวเองด้วยซ้ำ) **[แก้ตาม P-H — ผมเคลมผิดว่า agent_id ตายพร้อม session; operator เถียงและถูก]**: `SendMessage(agentId)` ชุบ agent จาก transcript บนดิสก์ได้แม้ process ตายไปแล้ว + resume เป็น session id ใหม่ พร้อม context ครบ → ลำดับชุบชีวิต: SendMessage(agentId) ก่อนเสมอ; handoff file = fallback (คนละ lineage / transcript หาย / งานที่ยังไม่ได้รายงาน) + staleness audit; registry เก็บ `session_id` ไว้แยกเคส
3. **Retire threshold 30-40% — ไม่เอาแบบ % ตายตัว** แก้เป็น 2 กลไก: (a) **continuous handoff** — ทุก report จบด้วย STATE SNAPSHOT → append ลง `.delegator/handoffs/<name>.md` ⇒ crash/retire/ตายเงียบ กู้จาก snapshot ล่าสุดได้เสมอ retirement เลิกเป็นพิธีพิเศษ; (b) retire เมื่อ remaining < ~2× งานถัดไป หรือ staleness (ยึด assumption เก่า/อ้างไฟล์ที่ย้าย → `staleness_flags`) หมายเหตุ: budget จริง 15M/ตัว ⇒ retirement จะ **เกิดน้อยมาก** — อย่า over-build กลไกนี้
4. **Depth plan — [แก้รอบ 2 หลัง operator เถียง] จาก "fix บทบาท 5 ชั้น" → DEPTH BUDGET CONTRACT** ผมตีตก fixed plan ว่า over-engineered; operator แย้ง: "เดี๋ยวอาจมี skill ที่ออกแบบให้ spawn หลายชั้นมาทีหลัง" — **มีประเด็นจริง**: depth เป็นทรัพยากรจำกัดที่ architecture แชร์กับดีไซน์ภายในของ skill ซึ่งเราคุมไม่ได้ (BMAD spawn ชั้นตัวเองอยู่แล้ว) และสิ่งที่ fixed plan ให้จริงๆ คือการจอง budget ไม่ใช่พิธี → สัญญาที่ ship: **architecture กินได้มากสุด 2 ชั้น** (0=delegator, 1=orchestrator ผู้ invoke skill) — **ชั้น 2-4 = budget ภายในของ skill ล้วนๆ (3 ชั้น)**; nested orchestrator (depth 2) ใช้เฉพาะงานที่ไม่ invoke deep skill ต่อ (ไปเบียด budget ของ skill); "ตื้นสุดเสมอ" คง default behavior ของชั้น architecture แต่ไม่ใช่เพดานของ skill; skill ที่ต้องการ >3 internal layers ชน harness cap (L5 ไม่มี Agent tool) → orchestrator ต้อง surface ไม่ปล่อยพังเงียบ; **gate จากชั้นลึก: ทำได้จริง (P-J PASS)** — deep child `SendMessage(to:"main")` + top session ตอบผ่าน agentId (revive) → skill อนาคตที่ออกแบบ gate หลายชั้นมีทางเดินแล้ว, depth-1 mailbox ยังเป็น default ที่เบากว่า
5. **Fresh router ทุกงานคุ้มไหม — softened** ข้าม router ได้ 2 กรณี: user ระบุ skill เอง หรือ direct continuation ของ work item เดิม; ที่เหลือ route (ต้นทุนจริง ~48k ถูกกว่าเลือก skill หนักผิดตัว) Router contract: คืน `{skill, args, why, confidence}`; การประกาศ router ของ cwd ใช้บรรทัดเดียวใน CLAUDE.md ของ workspace: `Router skill: /bmad-help` — ไม่ต้องสร้าง mechanism ใหม่
6. **named + TaskCreate ดีกว่าปะ (คำถามข้อ 15) — ใช่ ยืนยัน + มี nuance ใหม่** orchestrator = named (mailbox, SendMessage ได้, resume ได้); leaf = unnamed one-shot; side-quest ที่ต้องใช้ context ตัวเอง = self-fork; **แต่** P-C พบ unnamed subagent อาจไม่มี Task tools เลย (ToolSearch ยืนยันว่าง) ↔ named มี (Probe 5) → def ใส่ graceful-degradation แล้ว; teammate เต็มรูป/แยก session ยังไม่จำเป็น
7. **[เถียงรอบ 3] "orchestrator ห้ามมีลูก background — FOREGROUND ONLY" — operator ไม่เชื่อ ("มันต้อง chain spawn ลูกหลายชั้นได้จริงสิ") — OPERATOR ถูกในสาระ กฎผมผิดสองชั้น (P-I / P-I-b)** (a) named children จาก teammate: harness ปฏิเสธ**เอง**ที่ API (flat roster) — เป็นกำแพง harness ไม่ใช่ design choice ของผม และขัด Probe 5 วันเดียวกัน = variance → ยึด blocked; (b) unnamed children จาก teammate = **ASYNC** ไม่ใช่ blocking → **ลูกวิ่งขนานระหว่าง parent ทำงานต่อได้จริง** ตามที่ operator ต้องการ และ chain หลายชั้นได้จริง (Probe 4 ถึง L5, P-C fan-out ×3, P-I-b เก็บผลสำเร็จ) กฎที่ถูกจึงไม่ใช่ "foreground-only" แต่คือ **COLLECT-IN-TURN** (default): launch ลูกอิสระทั้งหมดก่อน → ทำงานอื่นต่อในเทิร์น → poll output_file ของลูกด้วย sentinel grep จนครบ — ห้ามจบเทิร์นรอ *bare completion* (เด้งถึง top เท่านั้น — stall ของ Probe 5)
8. **[ต่อยอดจาก session ที่ 2 ของ operator: "ทำไงให้ agent ใช้ SendMessage หากันเอง ไม่ใช่ตอบมาหา main" — OPERATOR ถูกอีกข้อ (P-K)]** explicit child→parent SendMessage **ปลุกพ่อ named ที่ rest จริงได้** (พิสูจน์สองฝั่ง: พ่อไม่ poll เลย, waker = ลูกไม่ใช่ spawner; ลูกต้องยิงก่อนจบงาน — จบเฉยๆ ไม่ปลุก) → pattern ที่ 2 **REST-WITH-PING** สำหรับลูกงานยาว: พ่อ rest ประหยัด turn/context, ลูก ping ปลุก; orphan risk (ลูกตายก่อน ping) → delegator WATCHDOG-NUDGE (ใส่ใน delegator.md แล้ว: เห็น grandchild จบแต่พ่อเงียบเกินคาด → nudge agentId ของพ่อ ไม่ relay ผล); nested parent (unnamed, ไม่รู้ id ตัวเอง) ใช้ไม่ได้ — collect-in-turn เท่านั้น; caveat: harness นี้มี same-day variance — proven-this-run

## §4 สถาปัตยกรรมฉบับจบ (ที่ ship)

### §4.1 Spawn physics (พิสูจน์แล้วบน install นี้ — กติกาออกแบบทั้งหมดตามนี้)
| ประเภท spawn | พฤติกรรม | ใครใช้ |
|---|---|---|
| named จาก main (`name:` ระบุ) | **background mailbox** — SendMessage(to:name) ระหว่างรัน / agentId หลังพัก; completion-notification เด้งไปหา **main เท่านั้น** | delegator spawn orchestrator |
| named จาก teammate | **โดน API ปฏิเสธ** (P-I): `Teammates cannot spawn other teammates — the team roster is flat.` (Probe 5 เคยผ่านวันเดียวกัน = variance → ยึด blocked) | — ห้ามพึ่ง |
| unnamed จาก main | background + auto-notification กลับ main | delegator ใช้กับ router/leaf ได้ |
| unnamed จาก teammate | **ASYNC เหมือนกัน ไม่ใช่ blocking** (P-I-b) — ได้ launch metadata + agentId + output_file path; เก็บผลด้วย poll ในเทิร์น (sentinel grep) | orchestrator spawn ลูกทุกตัว (nested orchestrator = unnamed + subagent_type) |
| fork | background; inherit context ของ *ผู้ fork*; budget สด; fork→fork ❌ | delegator (micro-jobs + needs-my-context) + orchestrator self-fork (poll ในเทิร์น) |

**กฎเหล็กที่ได้จาก physics:** named/mailbox มีได้เฉพาะระดับ main (harness enforce flat roster เอง); ลูกของ teammate ทุกตัว = unnamed **ASYNC** → **COLLECT-IN-TURN**: launch ลูกอิสระทั้งหมดก่อน (วิ่งขนาน) → ทำงานอื่นต่อได้ → poll output_file ของแต่ละลูกด้วย sentinel grep แบบแคบจนครบ — **default: ห้ามจบเทิร์นทั้งที่ลูกยังค้าง** เพราะ bare completion notification เด้งถึง top session เท่านั้น (stall ของ Probe 5 = จบเทิร์นรอ notification ที่ไม่มีวันมา) — **ยกเว้น pattern ที่ 2 REST-WITH-PING (P-K)**: พ่อที่เป็น named agent rest ได้ ถ้าลูกทุกตัวถูก brief ให้ยิง explicit `SendMessage(to:"<ชื่อพ่อ>")` ก่อนจบงาน (message ปลุกพ่อได้จริง; จบเฉยๆ ไม่ปลุก) — เหมาะกับลูกงานยาว; orphan risk ถ้าลูกตายก่อน ping → delegator watchdog-nudge; agent ทุกตัวชุบชีวิตได้จาก transcript ด้วย SendMessage(agentId) แม้ข้าม process restart (P-H)

### §4.2 ชิ้นส่วน
- **`~/.claude/agents/delegator.md`** — switch ทั้ง session (`claude --agent delegator`): direct-vs-delegate gate (ข้อ 3.1) · routing (router → resume ตัวเดิม / named orchestrator ใหม่ / fork) · brief template · registry single-writer · lifecycle (resume/retire/respawn-on-death ×1) · user-proxy (ตอบ gate เอง, relay รายงานแบบ near-verbatim ห้ามย่อยจนเละ) · เขียน `.delegator/delegator-handoff.md` ก่อน context ตัวเองเต็ม
- **`~/.claude/agents/orchestrator.md`** — mandate ฝังใน type: delegate-by-default (เกณฑ์: ≥2 independent substantive parts หรือ output หนักเข้า context; ของจิ๋วทำเอง; when in doubt → spawn) · invoke skill จริง · gate ที่ระดับตัวเอง ลูกต้อง gateless · ลูก unnamed ASYNC + collect-in-turn (sentinel grep บน output_file; ห้ามจบเทิร์นทั้งที่ลูกค้าง) · child brief 3 องค์ประกอบ (จบด้วย sentinel line) · reporting protocol 4 ข้อ (evidence / delegation log / SNAPSHOT / remaining tokens) · Task tools ผ่าน ToolSearch + degrade gracefully · git read-only เว้น brief มอบสิทธิ์
- **Registry `.delegator/registry.json`** (per workspace):
  ```json
  {"version":1,"orchestrators":[{"name":"toonflow-lead","agent_id":"<SendMessage-revivable — survives process restarts (P-H)>","session_id":"…","cwd":"…","purpose":"…","status":"active|resting|retired|died","spawned_at":"…","last_report_at":"…","tokens_remaining_last_report":14200000,"handoff_file":".delegator/handoffs/toonflow-lead.md","staleness_flags":[]}]}
  ```
- **Router convention:** บรรทัด `Router skill: /<name>` ใน CLAUDE.md ของ workspace (soul-crew → `/bmad-help`; ~/Work → กำหนดภายหลัง ดู §6)
- **Ops ต่อ spawn:** cd repo root ก่อน · `mode: acceptEdits` งานแก้โค้ด / default งาน research · `isolation:"worktree"` เมื่อ mutator ตัวที่สองแตะ repo เดียวกัน (แผล concurrent-worktree โผล่จริงระหว่าง P-C!) · commits เป็นของ delegator

### §4.3 Flow ต่อ 1 งาน
```
user → delegator
  → (มี router?) fresh unnamed agent invoke router skill → {skill,args,why,confidence}
  → เลือก: SendMessage หา orchestrator เดิม | spawn named orchestrator ใหม่ | self-fork
  → orchestrator: TaskCreate → invoke skill จริง → launch ลูก unnamed (async, วิ่งขนาน) → ทำงานต่อ + poll เก็บผลในเทิร์น → gate → SendMessage ↔ delegator
  → report (evidence + delegation log + SNAPSHOT + tokens) → delegator: append handoff file + update registry → relay ให้ user
```

## §5 การใช้งาน (operator quickstart)
```bash
cd <workspace>
claude --agent delegator          # เปิด switch ทั้ง session
# ใน session ปกติก็ spawn ได้: Agent({subagent_type:"orchestrator", name:"…", prompt:"You are <name>. …"})
```

## §6 งานที่เหลือ (เรียงตามลำดับ)
1. **Operator adopt** → แปะ §7 ทับหัวข้อ "Spawned agents" ใน `~/.claude/CLAUDE.md` (กันกฎเก่า-ใหม่ขัด)
2. **Live run แรกของจริง**: `claude --agent delegator` ใน soul-crew + งาน BMAD จริง 1 ชิ้น end-to-end (canary ที่ผ่านคือ synthetic)
3. **Hub (~/Work)**: เติม `Router skill:` ใน CLAUDE.md ของ hub + ทดสอบว่า `/ask` ตอบ router contract ได้ไหม (ถ้าไม่ → nominate skill อื่น/เขียน router-note); registry เพิ่ม field `project:` ต่อ agent
4. ~~Cross-session probe~~ — **เสร็จแล้ว (P-H, จากอุบัติเหตุจริง)**: operator เผลอปิด session กลาง probe → resume → `SendMessage(agentId)` ชุบจาก transcript สำเร็จ, context ครบ, ส่งงานเดิมจบ; unknown ที่เหลือข้อเดียว: address ข้าม LINEAGE (fresh `claude` คนละ conversation ใน cwd เดียวกัน) ยังไม่ได้ลอง
4b. **Residual: notification noise (anti-stall tax ที่เหลือครึ่งเดียว)** — "relay tax" ตายแล้ว (collect-in-turn ทำให้ parent เก็บลูกเอง — P-I-b ผมเห็น notification ลูกของ orch-bgtest แต่ไม่ต้อง relay; P-J gate ตอบตรงไม่มี hop) แต่ทุก descendant ที่จบยัง**ปลุก delegator 1 wake** (สังเกตจริง) — เหลือเป็น wake-and-ignore ต้นทุน ≈ เทิร์นสั้น cache-warm/ตัว; กฎ NO-RELAY ใส่ใน delegator.md แล้วกันถอยกลับพฤติกรรมเก่า; ถ้า fan-out ใหญ่จน noise หนักจริง escape hatch = orchestrator จ้างงานผ่าน background Bash `claude -p` (headless, ไม่ใช่ harness agent → ไม่ bubble เลย; แลกกับไม่มี transcript/agentId integration) — ยังไม่จำเป็นตอนนี้; และ P-K เพิ่มทางที่สาม: rest-with-ping ทำให้ orchestrator งานยาว rest ได้จริง (delegator ตื่นเฉพาะ noise สั้นๆ + watchdog)
5. **Negative-control eval** (over-spawn บนงานจิ๋วล้วน) — สัญญาณบางส่วนผ่านแล้วใน P-C (branch check ไม่ spawn); control เฉพาะกิจถูกมากถ้าอยากชัวร์
6. **`/delegate` skill (in-session switch)** — DEFERRED: failure mode ที่มันเคยแก้ (ลืม mandate/brief เพี้ยน) ถูกแก้ที่ตัว type แล้ว; ถ้าภายหลังอยากได้ → สร้างผ่าน `/skill-creator` (หมายเหตุ: P-A ไม่พบ /skill-creator บนเครื่อง — ต้องหา/ติดตั้งก่อน)

## §7 Draft แทนหัวข้อ "Spawned agents" ใน ~/.claude/CLAUDE.md (แปะเมื่อ adopt)
```markdown
## Spawned agents
**Delegation architecture (2026-07-02, canary-proven):** long-running sessions launch `claude --agent delegator`; substantive work runs in NAMED `subagent_type:"orchestrator"` agents (defs in ~/.claude/agents/ carry the full mandate — no per-brief behavioral rules needed). Design + evidence: soul-crew `_bmad-output/planning-artifacts/longrunning-delegator-design-v1.md`.
- **One-shot worker** — default for bounded leaf tasks: unnamed `Agent({subagent_type, prompt})`; result = final message; parallelize independents in one message.
- **Orchestrator** — any multi-step/skill-driven task: spawn named `orchestrator`; brief = "You are <name>" + task + termination criteria + gates pre-answered (else SendMessage me) + skill to invoke. Registry `.delegator/registry.json` per workspace; snapshots → `.delegator/handoffs/<name>.md`; revive rested/orphaned agents via SendMessage(agentId) FIRST — transcripts survive process restarts; handoff file = fallback seed + audit.
- **Framework routing** — workspace CLAUDE.md may declare `Router skill: /<name>` (soul-crew: /bmad-help): fresh unnamed agent invokes it → {skill,args,why,confidence} → orchestrator invokes that skill for real. Skip only on explicit-skill or direct continuation.
- **Hard physics (proven 2.1.198):** ALL child-completion notifications reach ONLY the main session; teammates cannot spawn NAMED children ("team roster is flat") and their unnamed children launch ASYNC → non-main agents COLLECT-IN-TURN (poll child output_file via narrow sentinel grep; NEVER end a turn with children outstanding); depth cap 5 (L5 loses Agent tool; architecture occupies 0-1, depths 2-4 belong to the skill); gates: depth-1 mailbox by default, deep agents gate via SendMessage(to:"main") + revival-by-agentId (P-J-proven); named agents don't know their own name; fork→fork ❌, self-fork from named ✅.
- **Spawn ops:** cd repo root first; mode acceptEdits for code / default for research; isolation:"worktree" for a second concurrent mutator of the same repo; git read-only for agents (delegator/lead commits); verbatim evidence always.
```

## §8 กฎ operator ที่งานนี้ปฏิบัติตาม
- verify with probes, not doc reading → ทุก claim กลไกใน §2/§4.1 รันจริงบนเครื่องนี้
- port proven templates → nested-official v2.1.172 + swarm-gist anti-stall + gruckion full-power ถูกหลอมเข้า def (ไม่ invent กลไกใหม่นอก harness)
- use /skill-creator for real skills → ไม่มี SKILL.md เขียนมือ ship (skill ถูก defer พร้อมเหตุผล)
- research ≤1 เดือน → อ้างเฉพาะ facts จาก handoff §4 (ค้น 2026-07-02) + probe สดวันนี้

---
*เขียนโดย main session รับช่วง handoff, 2026-07-02. Defs: `~/.claude/agents/delegator.md`, `~/.claude/agents/orchestrator.md`. Probe agents: P-B fork 64k/8s · P-F router 48k/44s · P-C eval 66k+3 workers/6.4m.*
