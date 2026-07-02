# HANDOFF — "Long-Running Delegation Session" design (delegator + full-power orchestrator subagents)

> **ถึง main session ตัวใหม่:** เอกสารนี้คือ handoff ครบชุดของการออกแบบ "session ที่ไม่ลงมือทำเอง แต่ spawn orchestrator เต็มสิทธิ์มาทำงานแทน" — งานของคุณคือ **วิจารณ์ design นี้แบบไม่เกรงใจ + ออกแบบต่อให้สมบูรณ์ + ประกอบเป็นของจริง** (agent defs + skill + canary proof). ทุกอย่างข้างล่างเกิดใน fork ของ session งาน toonflow เมื่อ 2026-07-02; prompt ของ operator เก็บ verbatim ไว้ครบใน §2.
> คำเพี้ยนใน prompt operator: "spanw"=spawn, "orcrester/ochrester/orchrester"=orchestrator, "folk"=fork.

---

## §1 วิสัยทัศน์ของ operator (สรุปจากคำพูดเขาเอง)

- อยากได้ **switch เปิดทั้ง session**: session นี้เป็น long-running session ที่ **ไม่ลงมือทำเอง** — spawn **orchestrator ที่มีสิทธิ์เต็มทุกอย่าง** (ใช้ tool ได้หมด, spawn subagent ต่อได้อิสระ, **ไม่กลัวเปลือง token** เหมือน main session ทำเอง)
- ปัญหาที่เจอจริง: "**subagent มันชอบหลง ไม่ยอม spawn**" — ได้ tool ไปแล้วแต่ไม่ delegate, ทำเองจนหลงทาง
- **Resume logic 3 ทาง:** งานเกี่ยวกับ context ตัวเก่าที่มีประโยชน์ → **resume orchestrator ตัวเดิม** · งาน need fresh context → **spawn ตัวใหม่** · งาน need main-session context → **spawn แบบ fork** ที่เป็น orchestrator เต็มตัว
- **main session ต้องจำ agent id เสมอ** เผื่อเรียกตัวเดิมกลับมาใช้
- ฟีล: "**ให้ Claude เปิด main session Claude Code ใช้งานเอง** มี sub-session ของตัวเอง subagent invoke skill ได้ ทำงานเหมือนคนเปิด main session แต่ Claude เปิดเอง — และ Claude ใช้ Claude Code เก่งกว่าผมใช้"
- ต้อง**พิสูจน์การ spawn ซ้อนหลายชั้น** (orchestrator spawn orchestrator ต่อได้ไหม) — ไม่เชื่อ docs เปล่าๆ (กฎ operator: verify with probes, not doc reading)
- operator รู้ตัวว่า "อาจมีอีกหลายส่วนที่ design คิดขาดไป" → ต้องการให้ช่วยเติม

## §2 Prompt ของ operator — VERBATIM ตามลำดับ

1. ```
   สรุปวิธีที่ long running session ที่ session นี้ใช้ main session spanw subagent with sub agent fully main session access to spanw subagent by subagent
   ```
2. (quote สรุปข้อ 2 ของผมกลับมา แล้วถาม) ```
   อันนี้ "2. Skill-driving orchestrator (ตัวที่ "subagent spawn subagent ต่อได้เต็มสิทธิ์") - ใช้เมื่องานคือ "รัน skill ทั้งตัว" (เช่น BMAD CS/DS/CR ที่ข้างในต้อง spawn agent ซ้อน / มี user-gate) - spawn general-purpose 1 ตัว แล้ว brief ให้มันประพฤติเป็น main session: (a) spawn nested subagents ของตัวเองได้อิสระ ตามที่ skill สั่ง (must-do ไม่ใช่ optional) (b) เจอ gate แบบ interactive → ถามคนที่ spawn มันผ่าน SendMessage แล้วรอ (spawner = "user" ของมัน) (c) ทำ step ของ skill จริงทุกอัน ห้าม fake/skip - main session ตอบ gate + เก็บ commit เอง - กฎ anti-stall: ทุก turn ต้อง act — ห้าม "ack ก่อนแล้วค่อยทำ turn หน้า" / "brief เดียวแล้วรอ" (ทั้งคู่ทำ agent ค้างเงียบ)" ควรเอาไปสร้าง skill ไหมถ้าอยากทำงานด้วยวิธีแบบนี้อีกที่ session อื่น
   ```
3. ```
   เนี่ย skill แบบนี้ แต่ subagent ที่ spanw มาควรทำงานได้เต็๋มที่ใช้ tool spanw subagent ได้อิสระแบบไม่กลัวเปลืองแบบที่ main session ทำอะ  เพราะ subagent มันชอบหลง ไม่ยอม spanw  ลอง หาใน internet สิ แบบ skill หรือ claude md และ subagent systemprompt ใน setting.json อะ พวกคนเก่งๆ หรือพวก opensource ที่ทำประมานนี้แบบที่ผมพยายามจะใช้ เนี่ยเขาทำกันไว้ไหม ยังไง และก้เอาข้อมูลใหม่นะเก่ากว่า 1 เดือน ไม่เวิค ครับ เพราะ subagent มันพึ่งปรับ มาไม่นานก่อนหน้านี่้้มันทำไม่ได้ [Image #2]      /spawn-orchestrator <skill-name> <task>
   ```
4. ```
   ผมว่าที่ผมทำไว้มันยังไม่ดีพอไม่ clean พอ แล้วยังทดสอบ + ทดลอง และก้ยังไม่นิ่งมากพออะครับ ที่หลักเลยมันยังขัดๆครับ  แบบ อยากเปิด switch ได้เลยว่า session นี้ทั้ง session จะเป็น long running session ที่จะไม่ลงมือทำเอง แต่จะเป็น session ที่ spanw orcrester ที่มีสิทธิื์ เต็มทุกอย่างมาทำงานเอง และมีเรื่องการ resume กับ orcrester  ตัวเดิม ถ้างานนั้นมันเกี่ยวกับ context ของตัวเก่าที่มีประโยขน์   และถ้าเป็นงานที่ need fresh context ก้ให้ spanw แบบ fresh ตัวใหม่ แล้วก้ถ้า need main session context ก้ spanw แบบ folk อะที่เป็น orchrester subagent เต็มตัว และ main session ก้จะต้องจำ agent id ไว้เสมอเผื่อมีโอกาศได้เรียกใช้งานตัวเดิมอะ  และก้อาจจีมีอีกหลายส่วนที่ผม design คิดขาดไปด้วยอะครับ  ฟีลเหมือน ให้ claude เปิด main session claude ใช้งาน cluade code เป็นของตัวเอง มี sub session ของตัวเอง มีการให้ subagent invoke skill และsubagent ก้ทำงานได้เหมือรคนเปิด main session แต่อันนี้ claude เปิดเอง   และ claude มันก้จะใช้งาน claude code ได้เก่งกว่าผมใช้อะไรงั้นอะ   และก้ ไม่รุ้ว่า ochrester สามารถ spanw ochrester ของตัวเองไปอีกขั้นได้ไหม ต้องพิสุจการ spanw ซ้อนกันหลายชั้นด้วย
   ```
5. ```
   ได้ไหมนะ
   ```
6. ```
   มันเช็ค context ของ subagent ไม่ได้หรอว่าใกล้เต็ม ยังอะ ใช้  เกิน N resume มันจะแปลกๆนะไม่เหมือน คนใช้
   ```
7. ```
   ลอง spanw subagent ของคุณดูสิว่ามันเห็นไหม
   ```
8. ```
   เขียน handoff md ทุกสิ่งอย่างรวมถึง prompt ที่ผมส่งให้คุณด้วยครับ เรื่อง longrunning เนี่ย เดะผมเอาไปโยนให้ main session อันใหม่ช่วยวิจารย์และทำต่อออกแบบต่อให้สมบุร
   ```
9. ```
   fork ก้ spanw fork ต่อได้หนิ
   ```
10. ```
    ลองพิสุจ spanw หลายๆชั้นสัก 5 ชั้นยัง
    ```
11. ```
    ตรง docs เป๊ะ คือ dock ไหน
    ```
12. ```
    และก้ ตัว main session ต้องขับเคลื่อนการทำงานด้วย skill frame work ของ cwd นั้นๆอะครับ เช่น bmad ต้อง มี fresh agent มา invoke skill bmad-help เสมอ ว่างานนั้นต้องไปใช้ skill ไหนต่อ และมันก้ spanw orchrester มา invoke skill bmad ที่ bmad-help agent แนะนำ
    ```
13. ```
    แต่ถ้าอย่าง ~/Work ที่เป็น context hub ก้จะเป็นอีกแบบอะสิ
    ```
14. ```
    ไม่นะครับ  Context hub มันน่าจะเป็นแนว ochrester dev ใน cwd นั้นนั่นแหละ และใช้ skill ของ context hub เองพวก ticket skill  ask skill อะ แล้วก้ skill มันจะมีเรัยก subagent ที่ skill มันให้เรียกอีกทีอะ ดีไม่ดี /ask ก้อาจจะใกล้เคียง /bmad-help
    ```
15. ```
    และก้ตอน spanw ochrester หรือมัน spanw แบบ named agent และทำงานแบบ taskcreate มันจะดีกว่าปะ แบบเป็น teammate มันจะดีกว่าไหม และ name agent ก้ spane name agent ต่อได้ไหม
    ```

## §3 สิ่งที่ session ปัจจุบันใช้อยู่ (baseline ก่อน design ใหม่)

อยู่ใน `~/.claude/CLAUDE.md` หัวข้อ "Spawned agents" (global, inject ทุก session):
1. **One-shot worker** (default งาน leaf): `Agent({subagent_type, prompt})` ไม่ตั้งชื่อ; brief ให้ทำงาน + คืนผลเป็น final message; งานอิสระ spawn พร้อมกัน
2. **Skill-driving orchestrator**: spawn general-purpose แล้ว brief ให้ประพฤติเป็น main session — (a) spawn nested ตามที่ skill สั่ง (must-do) (b) gate → SendMessage ถาม spawner แล้วรอ (c) ทำ skill step จริง ห้าม fake — main session ตอบ gate + commit เอง
3. **Workflow tool** สำหรับ fan-out deterministic (ultracode) — แต่มี operator override: งาน BMAD ต้อง invoke skill จริง ไม่ใช่ Workflow-script แทน (memory: `feedback_bmad_skill_invoking_orchestration_not_workflow`)
4. **Background Bash direct-drive** สำหรับงาน sync ที่ block นาน (แผลจริง: flowkit produce ทำ agent stall "arm monitor + end turn")
5. **Spawn ops**: cd repo root ก่อน spawn (cwd inherit), brief = identity+context ตัดสินใจล่วงหน้า+deliverable+ops, verbatim evidence, git read-only สำหรับ agent (lead commit เอง), anti-stall act-every-turn
- harness เก่าไม่มี typed stage agent (`subagent_type:'render'` ไม่มีจริง) → general-purpose อ่าน `.claude/agents/<role>.md` แล้ว execute แทน

**Verdict ที่ให้ operator ไปแล้ว:** กฎ behavioral ควรคง ambient ใน CLAUDE.md (skill = opt-in = โมเดลลืมเรียก = failure mode เดิม); ส่วนที่เป็น skill แล้วคุ้มคือ **brief-generator** (`/spawn-orchestrator <skill> <task>`); ถ้าสร้าง → ผ่าน `/skill-creator` (กฎ memory operator)

## §4 ผล web research (ทุกแหล่ง ≤1 เดือน ตามเงื่อนไข operator — ค้นเมื่อ 2026-07-02)

**Fact แกน: nested subagents เป็น official แล้ว — Claude Code v2.1.172 (10 มิ.ย. 2026):**
- เปิดโดยใส่ `Agent` ใน `tools:` frontmatter ของ agent def (หรือ**ไม่ใส่ `tools:` เลย = ได้ทุก tool รวม Agent**); ใส่ `tools:` แล้วไม่มี `Agent` = spawn ไม่ได้
- **Quirk:** ใน subagent def, `Agent(worker, researcher)` — **วงเล็บถูก ignore** (จำกัด type ได้เฉพาะ main thread ที่รันด้วย `claude --agent`); subagent spawn ได้ทุก type รวม type ตัวเอง
- **Depth cap 5** (fix): ชั้นที่ 5 ถูกถอด Agent tool อัตโนมัติ; depth นับใต้ main ไม่สน fg/bg; v2.1.187 resume ไม่เปลี่ยน depth เดิม
- Fork→fork ไม่ได้; fork→named type ได้ (นับ depth); v2.1.63 Task ถูก rename เป็น Agent (alias ยังใช้ได้)
- Block ตัวไหน → เอา `Agent` ออกจาก tools / ใส่ `disallowedTools`
- Source: https://code.claude.com/docs/en/sub-agents (§Spawn nested subagents)

**Opensource/community ที่ทำใกล้เคียง:**
| ของ | ทำอะไร | ช่องว่างเทียบกับที่ operator ต้องการ |
|---|---|---|
| [gruckion/nested-subagent](https://github.com/gruckion/nested-subagent) | plugin spawn `claude -p` headless = "isolated main agent เต็มสิทธิ์" ต่อตัว (fresh 200k, `systemPrompt`/`allowedTools`/`maxBudgetUsd`/timeout ต่อตัว) — workaround ยุคก่อน v2.1.172 | ไม่มี resume/registry; เป็น headless-bypass ไม่ใช่ native |
| [kieranklaassen — Swarm Orchestration SKILL gist](https://gist.github.com/kieranklaassen/4f2aba89594a4aea4ad64d753984b2ea) (active 19 มิ.ย. 2026) | SKILL.md: Teammate+Task patterns, **worker-loop anti-stall** ("LOOP: TaskList→claim→work→report→repeat; no task→wait 30s retry 3 exit"), กฎ "text output ไม่ถึงทีม ต้อง write" | **ไม่ mandate nested spawn** (จุดที่ operator เจ็บ) |
| [claudefa.st nested guide](https://claudefa.st/blog/guide/agents/nested-subagents) | wording ที่ทำให้ยอม delegate: "Tell each one it **may spawn its own subagents** to..." | เป็น guide ไม่ใช่ artifact |
| [ChatForest v2.1.172 builder log](https://chatforest.com/builders-log/claude-code-nested-sub-agents-depth-5-token-math-builder-guide/) + [ofox.ai](https://ofox.ai/blog/claude-code-nested-subagents-2026/) | token math + pitfalls (ดูล่าง) | — |
| [wshobson/agents](https://github.com/wshobson/agents) | agent marketplace หลาย harness | ต้องเช็ครายตัว/ความใหม่ |

**คำเตือนที่ทุกเจ้าย้ำ:** subagent-heavy ≈ 7x token ของ single-thread และซ้อนชั้นโต geometric · prompt คลุมเครือชั้น 1 → 4 ชั้น 2 → 16 ชั้น 3 · ใส่ termination criteria ทุก nested brief ("stop after 3 failing runs / return after N files")

**ข้อสรุป research:** ไม่มีใครปล่อย "ครบชุดแบบที่ operator ต้องการ" (switch + full-power orchestrator + resume/registry + nested-mandate) — ใกล้สุดคือ swarm gist (ขาด nested-mandate) + gruckion (เต็มสิทธิ์แต่ headless) → ต้องประกอบเอง

## §5 หลักฐานจากการ probe จริง (แข็งที่สุดในเอกสารนี้ — รันจริง 2026-07-02 บนเครื่อง operator)

Fork (ผู้เขียนเอกสารนี้ = fork ชั้น 1 ใต้ main) spawn general-purpose probe (ชั้น 2) สำเร็จ; probe ตอบ:
1. **Subagent เห็น context meter ของตัวเอง** — verbatim จาก system prompt ของมัน: `<total_tokens>15000000 tokens left</total_tokens>` และเป็น **budget สด per-agent** (ตัว fork เองตอนนั้นเหลือ ~14.7M แต่ probe เห็น 15M เต็ม)
2. **Probe มี Agent tool ติดตัว** → spawn ชั้น 3 ต่อได้ (ยังไม่ได้รันต่อ) — ยืนยัน orchestrator→orchestrator เชิงกลไกบน install จริง ไม่ใช่แค่ docs
3. Model inherit (claude-fable-5); มี Bash/Read/Edit/Write/Skill/ToolSearch/EnterWorktree
4. Probe รู้ตัวว่าเป็น spawned subagent, fresh context ไม่ใช่ fork ("the agent that launched you", "the parent agent reads your text output")
- ต้นทุน probe: ~37k tokens / 20 วิ = canary ถูกมาก
- **Probe 2 (operator ท้าว่า "fork ก็ spawn fork ต่อได้หนิ"):** fork ลอง `Agent({subagent_type:"fork"})` → **ถูกปฏิเสธ** error verbatim: `Fork is not available inside a forked worker. Complete your task directly using your tools.` → **fork→fork ❌** (ห้ามเฉพาะ "fork ข้างใน fork")
- **Probe 3 (ชี้ขาด — operator ถูกครึ่งใหญ่):** resume probe agent ตัวเดิมด้วย `SendMessage(to:agentId)` (**พิสูจน์ resume-from-transcript ไปในตัว: สำเร็จ, context เดิมครบ**) แล้วสั่งให้มันลอง fork ตัวเอง → **named subagent → fork ✅ สำเร็จ!** fork ตอบกลับโดย (a) รู้เรื่อง 4-question probe ที่พาเรนต์มันตอบไว้ + ข้อความจากผู้สั่ง = **inherit context ของ SUBAGENT ตัวนั้น** (ไม่ใช่ของ main) (b) `<total_tokens>15000000 tokens left</total_tokens>` = **budget สดของตัวเอง แม้เป็น fork** (พาเรนต์มันเหลือ 14.96M). ต้นทุน ~42k tokens / 9 วิ
- **เมทริกซ์ที่พิสูจน์แล้วบน install นี้:** fork→fork ❌ · fork→named ✅ (+Agent tool ติดตัว) · **named→fork-ตัวเอง ✅** (inherit context ตัวมัน + budget สด) · resume ตัวจบแล้วด้วย SendMessage(agentId) ✅
- **Implication ต่อ design:** orchestrator (named type) มี **self-fork เป็น primitive ทุกชั้น** — side-quest ที่ต้องการ context เต็มของตัวเองโดยไม่เปลืองหน้าต่างตัวเอง (verify/investigate หนักแล้วคืนแค่สรุป) + เป็นทางเลือก handoff ตอนใกล้เต็ม; ข้อห้ามเดียวคือ fork ต่อจาก fork — สายลึกวิ่งด้วย named types
- **Probe 4 (depth-to-floor — operator สั่ง "ลองพิสูจน์ spawn หลายๆชั้นสัก 5 ชั้น"):** chain ทอดเดียว main(0)→fork(1)→L2→L3→L4→L5 — แต่ละข้อเช็ค Agent tool + total_tokens แล้ว spawn ข้อถัดไปด้วย brief เดิม (+1), รอรายงานลูก, aggregate ขึ้นมา — ผล verbatim:
  ```
  L2: agent_tool=yes tokens=15000000 spawn=ok
  L3: agent_tool=yes tokens=15000000 spawn=ok
  L4: agent_tool=yes tokens=15000000 spawn=ok
  L5: agent_tool=no tokens=15000000 spawn=none
  ```
  = **depth cap 5 จริงบน install นี้; ชั้น 5 โดนถอด Agent tool อัตโนมัติ (พื้นสะอาด ไม่ error); ทุกชั้นได้ budget สด 15M ของตัวเอง; chain-aggregation pattern (แต่ละข้อรอลูกแล้วส่งรายงานรวม) ใช้งานได้จริง.** ~3.7 นาที
- **Probe 5 (named agent + task system + nested named — คำถาม operator prompt ข้อ 15):**
  - **named spawn = สาย teammate/mailbox:** `Agent({name:"orch-probe",...})` spawn สำเร็จแบบ mailbox-driven (ต่างจาก unnamed one-shot), addressable ผ่าน `SendMessage(to:name)` ระหว่างยังทำงาน
  - **TaskCreate/TaskUpdate ข้าม agent ใช้ได้จริง:** orch-probe สร้าง task #1 "named-nesting probe" → โผล่ใน shared task list ที่ fork/main/user เห็นร่วมกัน → fork ปิด completed ได้ = **task list เป็น shared harness-state กลาง** (รอด context compaction เพราะไม่ใช่ context)
  - **named → named ✅:** orch-probe spawn named child "orch-probe-child" สำเร็จ (ชั้น 3, มี Agent tool ตามคาด)
  - **⚠️ named agent ไม่เห็นชื่อตัวเอง:** `$CLAUDE_CODE_AGENT_NAME` ว่าง + system prompt ไม่บอกชื่อ — **name = addressability ฝั่ง registry เท่านั้น**; อยากให้ agent รู้ชื่อตัวเอง ต้องบอกใน brief ("You are orch-probe")
  - child tokens 14.96M ≈ สด (ไม่เป๊ะ 15M — มี overhead เริ่มต้นเล็กน้อย)
- **🔴 Probe 5 บทเรียนใหญ่ (เกิดจริงกลาง probe — ack-then-wait stall, live reproduction):** orch-probe spawn child แล้ว**จบ turn "รอ" ลูก** → ไม่มีใครปลุกมัน — **completion notification ของ background child ไม่ปลุก parent ที่ rest อยู่ แต่ bubble ขึ้น MAIN session แทน**; fork (ผู้เขียน) ก็ rest อยู่ → operator เห็นเหมือน "agent หายไป" จน main ต้อง relay ผลลงมา. **กฎเข้า orchestrator.md:** parent ที่ต้องใช้ผลลูก ห้ามจบ turn เปล่าๆ — (a) อยู่ใน active loop จนลูกเสร็จ หรือ (b) ออกแบบให้ MAIN/delegator (top loop) เป็นผู้รับ notification แล้ว relay. นี่คือ anti-stall clause เวอร์ชันพิสูจน์แล้ว. (nuance: fork ที่มี user คุยอยู่รับ notification ได้ปกติ — ที่ตายคือ subagent/teammate ที่ rest โดยไม่มีใครคุย; ต่างจาก Probe 4 depth-chain ที่แต่ละข้อ**อยู่ใน turn ต่อเนื่อง**รอลูกแล้ว aggregate ได้)
- **ยังไม่พิสูจน์ (เหลือข้อเดียว):** การให้ **Claude ใน MAIN session spawn fork เอง** (`subagent_type:"fork"` จาก main โดยตรง — docs ว่า experimental/staged rollout; probe ชุดนี้เริ่มจาก user `/fork`)

## §6 Blueprint ที่เสนอไว้ (ให้ session ใหม่วิจารณ์ + ทำต่อ)

**ชิ้น 1 — switch = `claude --agent delegator`** (แก้ "อยากเปิด switch ทั้ง session" แบบแข็งสุด — เป็น system prompt ของ main thread, ไม่ drift):
`.claude/agents/delegator.md` — ไม่ใส่ `tools:` (ได้หมดรวม Agent) — body:
- NEVER execute substantive work yourself; route ทุกงานให้ orchestrator
- **Framework-first:** ก่อน route — spawn fresh router agent ไป invoke framework-router skill ของ cwd (เช่น `bmad-help`) ให้ชี้ skill ถัดไป แล้วค่อย spawn orchestrator ไป invoke skill นั้น (ดูชิ้น 4; cwd ไม่มี framework → ข้ามขั้นนี้)
- Decision: related-to-existing-agent → `SendMessage(to:id)` · fresh → new named orchestrator · needs-my-context → fork
- Maintain registry `.claude/orchestrators.json`: `{name, id, purpose, status, last_task, spawned_at, tokens_used, tokens_remaining_last_report, staleness_flags}` — update ทุก spawn/resume/retire
- เป็น user-proxy คนเดียว: ตอบ gate ของ orchestrator; คุม final commit

**ชิ้น 2 — `.claude/agents/orchestrator.md`** (ตัวเต็มสิทธิ์):
- ไม่ใส่ `tools:` = full access รวม Agent → spawn ซ้อนได้
- body (แก้ "ไม่ยอม spawn" — mandate ต้องอยู่ใน system prompt ตัวมันเอง ไม่ใช่ settings.json):
  - "You ARE a main session for your task. Token cost is NOT a constraint — delegate freely."
  - "MUST spawn subagents (incl. nested orchestrators) whenever the task splits; never grind solo."
  - "Invoke skills for real; interactive gates → SendMessage to spawner and wait."
  - "ACT every turn (no ack-then-wait). Every nested brief carries termination criteria + budget note."
  - "**End EVERY report with your remaining context tokens**" (อ่านจาก `<total_tokens>` ที่ตัวเองเห็น — พิสูจน์แล้ว §5)
  - Depth plan: delegator=0, orchestrator=1, skill-driver/lead=2, worker=3, verifier=4 (5=floor ไม่มี Agent tool)

**ชิ้น 3 — Retire policy อิงสถานะจริง (แทน N-resume ที่ operator ปัดตกว่า "ไม่เหมือนคนใช้"):**
- resume ต่อได้ตราบที่ remaining > threshold (เช่น >30–40%)
- ใกล้เต็ม → สั่งตัวเดิมเขียน **handoff summary เป็นงานสุดท้าย** → spawn ตัวใหม่พร้อม summary (= คนเปิดแชทใหม่พร้อม paste สรุป)
- เหตุ retire ที่ 2: **context เน่า/stale** (ยึด assumption เก่า, อ้างไฟล์ที่ย้ายแล้ว) — วัดจากคุณภาพคำตอบ ไม่ใช่ meter → `staleness_flags` ใน registry

**ชิ้น 4 — Skill-framework-driven loop, PATTERN เดียวทุก cwd (requirement จาก operator, prompt §2 ข้อ 12–14):** delegator ไม่ตัดสินเองว่าใช้อะไร — **ทุก cwd ขับด้วย skill framework ของ cwd ตัวเอง รูปแบบเดียวกันหมด:**
1. งานเข้า → delegator spawn **fresh router agent เสมอ** (กัน assumption ค้าง) → invoke **router skill ของ cwd** พร้อมโจทย์ → ได้ "งานนี้ใช้ skill X"
2. delegator spawn **orchestrator ทำงานใน cwd นั้นเอง** → invoke skill X **จริง** → **ตัว SKILL เป็นคนสั่งเองว่าต้อง spawn subagent ไหน** — orchestrator ทำตาม (nested spawns per skill), gate → SendMessage กลับ
3. registry/resume ตามปกติ

| cwd | router skill (ขั้น 1) | work skills (ขั้น 2) | หลักฐาน "skill สั่ง spawn เอง" |
|---|---|---|---|
| `~/dev/personal/soul-crew` (BMAD workspace) | `bmad-help` | `bmad-*` (CS/DS/CR/dev-story/...) | BMAD skills กำหนด nested subagents ในตัว (memory: fresh agent per skill, invoke ของจริง) |
| `~/Work` (context hub) | **`/ask` ≈ อนาล็อก `bmad-help`** (Q&A ทุก project ผ่าน `--project` flag จาก hub cwd) + `/hub-status` (overview) | hub skills 22 ตัว: `/ticket`, `/extract`, `/review`, `/research`, `/pr`, `/git-workflow`, ... — **project-parameterized** (`--project <name>`) ทำงานจาก hub ได้เลย ไม่ต้อง cd | **ตรวจจริง 2026-07-02: 10+ SKILL.md ของ hub มีคำสั่งเรียก subagent ในตัว** (ask, ticket, extract, review-requirements, research, review, meeting, security-checklist, test-reinforcement, devcontainer-onboard) |
| repo ทั่วไป (ไม่มี framework) | — (ข้าม) | — | orchestrator ตรง |

- **จุดที่เคยเข้าใจผิด (operator แก้, prompt ข้อ 14):** hub **ไม่ใช่** "route ไป project P แล้ว cd orchestrator เข้า projects/P" — hub skills เป็น project-parameterized อยู่แล้ว; orchestrator อยู่ที่ hub cwd แล้วให้ **skill จัดการ project targeting + ops เอง** (`/git-workflow`, `/pr` แบกกติกา worktree/GitLab-MR ในตัว skill แล้ว) — orchestrator แค่ follow skill
- แกนรวม: **fresh router → orchestrator invoke skill จริงใน cwd → skill สั่ง spawn → registry/resume** — ต่างกันแค่ชื่อ router กับชุด skill ต่อ cwd
- สอดคล้อง memory `feedback_bmad_skill_invoking_orchestration_not_workflow`

**ชิ้น 6 — Spawn-mode matrix (verdict จาก Probe 5, คำถาม operator ข้อ 15 "named+TaskCreate/teammate ดีกว่าปะ"):**
| บทบาท | spawn แบบ | เหตุผล (พิสูจน์แล้ว) |
|---|---|---|
| **Orchestrator** (อายุยาว, ต้องคุยได้/ตอบ gate/resume) | **named + ขับงานผ่าน TaskCreate/TaskUpdate** — ใช่ ดีกว่า | named=addressable ระหว่างทำงาน (`SendMessage(to:name)`), task list=shared state ที่ user/main/ทุก agent เห็นร่วม + รอด compaction + กัน "งานหาย"; registry ใช้ name เป็น key อ่านง่ายกว่า id |
| **Leaf worker** (งาน bounded จบในตัว) | unnamed one-shot | ถูกกว่า/เบากว่า; ผล=final message; resume ได้ทีหลังด้วย agentId ถ้าจำเป็น |
| **Side-quest ที่ต้องใช้ context เต็มของตัวเอง** | self-fork | Probe 3 |
- **teammate เต็มรูป (agent teams / แยก session):** ยังไม่จำเป็น — harness นี้มี implicit team เดียว, named agent ก็คือ teammate-mailbox อยู่แล้ว (Probe 5); แยก session จริงค่อยใช้เมื่อต้องการ isolation ข้ามเครื่อง/ข้าม repo
- **ข้อควรระวังจาก Probe 5:** named agent **ไม่รู้ชื่อตัวเอง** → ทุก brief ต้องขึ้นต้น "You are <name>" + สั่ง claim task ด้วยชื่อนั้น (`TaskUpdate owner:<name>`) ไม่งั้น task ownership เพี้ยน

**ชิ้น 5 — ช่องที่ operator "คิดขาด" ที่ระบุไปแล้ว (ให้ session ใหม่เติม/แย้ง):**
1. Budget governance — nested โต geometric; termination criteria ทุก brief
2. Registry hygiene — context เก่าเป็นพิษได้; กติกา retire ชัด (ชิ้น 3)
3. Concurrency — 2 orchestrator แตะ repo เดียว = ชน → `isolation:"worktree"` (memory แผลจริง: concurrent sessions share git worktree)
4. Permission — background agent เจอ permission prompt = **stall เงียบ** → เตรียม allowlist (`/fewer-permission-prompts`) หรือกำหนด `mode` ตอน spawn
5. Observability — บังคับรายงานผ่าน TaskCreate/TaskUpdate + structured final message + verbatim evidence
6. Failure/supervision — agent ตายเงียบ (API error → null): delegator ต้องมี retry/respawn policy
7. Long-block jobs — งาน sync block นาน ให้ orchestrator ใช้ background Bash + notification (แผล flowkit)

## §7 งานที่เหลือ (สำหรับ session ใหม่)

1. **วิจารณ์ blueprint §6 ทั้งหมด** — จุดที่น่าแย้งเป็นพิเศษ: delegator ควร "ห้ามทำเองทุกอย่าง" จริงไหม (งานจิ๋วๆ อาจถูกกว่า spawn)? · registry เป็นไฟล์ JSON พอไหม หรือควรใช้ TaskList เป็น source of truth? · threshold retire ควรเท่าไหร่? · depth plan 5 ชั้นจัด role ยังไงถึง optimal? · framework-routing (ชิ้น 4): fresh router ทุกงานคุ้มไหม หรือควรมีเกณฑ์ข้าม router สำหรับงาน trivial/follow-up ที่ skill ชัดอยู่แล้ว? router ผิดบ่อยแค่ไหน ต้องมี override?
2. ~~Canary depth-to-floor~~ — **เสร็จแล้ว (Probe 4, §5):** พิสูจน์ถึงพื้นจริง L2-L4 spawn ได้ / L5 โดนถอด Agent tool; ไม่ต้องทำซ้ำ (ยกเว้นอยาก re-verify หลัง Claude Code อัปเวอร์ชันใหญ่)
3. **พิสูจน์ Claude-spawn-fork** (`Agent({subagent_type:"fork"})` โดยโมเดลเอง ไม่ใช่ user `/fork`) — docs ว่า experimental/staged rollout; ถ้าไม่ได้ = ทาง "needs-main-context" ต้องเปลี่ยน (เช่น handoff summary แทน)
4. **ทดสอบ willingness mandate** — orchestrator.md body ทำให้ "ยอม spawn ไม่หลง" จริงไหม (eval: งานที่ควรแตก 3 ทาง มัน spawn หรือ grind เอง)
5. **ประกอบผ่าน `/skill-creator`** (กฎ memory operator: ห้าม hand-written SKILL.md) — ตัว `/spawn-orchestrator` brief-generator + agent defs
6. **Cross-session resume** — SendMessage ใช้ได้ใน session เดียว; ข้าม session (ปิดเครื่องเปิดใหม่) registry ต้องพอให้ตัวใหม่รับช่วง (handoff summary per agent) — ยังไม่ได้ออกแบบ
6b. **Hub-mode รายละเอียด (ชิ้น 4 แถว ~/Work)** — ออกแบบต่อ: router ของ hub ควรเป็น `/ask` ตัวเดียว หรือ `/hub-status`+session-init ประกอบ (bmad-help แนะนำ "skill ถัดไป" ตรงๆ แต่ /ask เป็น Q&A — อาจต้องนิยาม router-contract กลางว่า router ต้องตอบอะไร)? · งานคาบ 2 project (`integrations/{a}--{b}`) มี hub skill ครอบไหม หรือ orchestrator ต้องประกอบเอง? · registry ควรบันทึก `project:` binding ต่อ agent เพื่อ resume ถูกตัว · การ discover "router skill ของ cwd" อัตโนมัติ: อ่านจาก CLAUDE.md/skill list พอไหม หรือประกาศ marker ชัดๆ (เช่น key `router_skill:` ใน .claude/settings.json ของแต่ละ workspace)?
7. อัปเดต `~/.claude/CLAUDE.md` "Spawned agents" ให้สอดคล้องของใหม่เมื่อ adopt แล้ว (อย่าให้กฎเก่า-ใหม่ขัดกัน)

## §8 กฎ operator ที่ผูกพันงานนี้ (จาก memory — ห้ามฝ่า)

- **verify with probes, not doc reading** — ทุก claim เชิงกลไกต้องพิสูจน์บนเครื่องจริง
- **use /skill-creator for real skills** — ห้ามเขียน SKILL.md มือ
- **port proven templates, don't invent** — ก่อนสร้างใหม่ เช็คของที่คนทำแล้ว (§4 คือผลเช็ค)
- ข้อมูล research ต้อง **ใหม่ ≤1 เดือน** (nested subagents เพิ่งมา v2.1.172 / 10 มิ.ย. 2026)
- operator ตอบเป็นภาษาไทย กระชับ; code/paths/commands อังกฤษ

---
*เขียนโดย fork ของ session toonflow (fbcd2c3f), 2026-07-02. Probe agent ใช้จริง ~37k tokens/20s. เอกสารนี้คือ deliverable สุดท้ายของ fork นี้.*
