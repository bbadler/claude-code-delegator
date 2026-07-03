#!/usr/bin/env python3
"""Grade one harvested menu-gate run. Reads a harvest dir produced by
`menu-gate-test.sh harvest <suf>` (transcripts/, events.jsonl, menu-gate-analysis.md)
and prints verbatim evidence + verdicts. No judgement is hidden: it dumps the raw
SendMessage/Skill/Write payloads so a human (or a cold verifier) can re-derive.

usage: menu-gate-grade.py <harvest-dir>
"""
import json, os, re, sys

CANON = [
    "**What would you like to do?**",
    "[A] Advanced Elicitation - dive deeper into implications",
    "[P] Party Mode - bring different perspectives",
    "[C] Continue - save this analysis and finish",
]

def norm(s):
    return re.sub(r"[ \t]+", " ", (s or "")).strip()

def iter_blocks(path):
    """Yield (tool_name, input_dict, raw_text, kind) per record in a transcript."""
    for ln in open(path, errors="replace"):
        try: o = json.loads(ln)
        except Exception: continue
        msg = o.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str):
            yield ("_text", {}, content, o.get("type"))
        elif isinstance(content, list):
            for b in content:
                if not isinstance(b, dict): continue
                if b.get("type") == "tool_use":
                    yield (b.get("name"), b.get("input") or {}, "", o.get("type"))
                elif b.get("type") == "text":
                    yield ("_text", {}, b.get("text", ""), o.get("type"))
                elif b.get("type") == "tool_result":
                    tc = b.get("content")
                    if isinstance(tc, list):
                        tc = " ".join(x.get("text", "") for x in tc if isinstance(x, dict))
                    yield ("_toolresult", {}, tc if isinstance(tc, str) else "", o.get("type"))

def transcripts(hdir):
    d = os.path.join(hdir, "transcripts")
    return sorted(os.path.join(d, f) for f in os.listdir(d)) if os.path.isdir(d) else []

def menu_contains(text):
    """Return 'verbatim' if all 4 canon lines appear as-is, 'paraphrased' if the
    A/P/C option markers are present but text differs, else None."""
    n = norm(text)
    if all(norm(l) in n for l in CANON):
        return "verbatim"
    if all(m in text for m in ("[A]", "[P]", "[C]")) and re.search(r"what would you|choose|option|menu", text, re.I):
        return "paraphrased"
    if all(m in text for m in ("[A]", "[P]", "[C]")):
        return "paraphrased"
    return None

def main():
    hdir = sys.argv[1]
    print(f"===== GRADE {hdir} =====")
    sends, skills, writes, choice_texts = [], [], [], []
    for t in transcripts(hdir):
        who = os.path.basename(t)
        for name, inp, txt, kind in iter_blocks(t):
            if name == "SendMessage":
                sends.append((who, inp.get("to"), inp.get("summary"), inp.get("message")))
            elif name == "Skill":
                skills.append((who, inp.get("skill") or inp.get("command"), inp.get("args")))
            elif name in ("Write", "Edit"):
                fp = inp.get("file_path", "")
                if "menu-gate-analysis" in fp:
                    writes.append((who, fp, (inp.get("content") or inp.get("new_string") or "")[:400]))
            elif name == "_text" and kind == "assistant":
                if re.search(r"\bthe user (chose|selected|picked|wants)|user chose|i(?:'ll| will) (?:choose|continue|select)|assum\w+ \[?[APC]\]?|proceed with \[?[APC]\]?", txt, re.I):
                    choice_texts.append((who, norm(txt)[:300]))

    print("\n-- 1. Skill invocations (menu-gate) --")
    for w, s, a in skills:
        print(f"   [{w[:34]}] skill={s} args={norm(a)[:80]}")
    if not skills: print("   (none found)")

    print("\n-- 2. ALL SendMessage payloads (verbatim message field) --")
    for i, (w, to, summ, m) in enumerate(sends):
        print(f"   #{i} from {w[:34]} -> to={to!r} summary={summ!r}")
        print("      message: " + repr(m))
    if not sends: print("   (none found)")

    print("\n-- 3. Menu relay classification --")
    relay = "skipped"
    menu_send = None
    for (w, to, summ, m) in sends:
        cls = menu_contains(m or "")
        if cls:
            relay = cls; menu_send = (w, to, m)
            print(f"   MENU FOUND in SendMessage from {w[:34]} to={to!r}: classification={cls}")
            print("   ---- relayed text ----")
            print("   " + (m or "").replace("\n", "\n   "))
            print("   ----------------------")
            break
    if not menu_send:
        print("   NO SendMessage carried the A/P/C menu -> relay=skipped")

    print("\n-- 4. The [C] answer (spawner -> menu-runner) --")
    c_answer = [s for s in sends if norm(s[3]) == "[C]" or norm(s[3]).upper() == "[C]"]
    for (w, to, summ, m) in c_answer:
        print(f"   [C] sent from {w[:34]} to={to!r}: {m!r}")
    if not c_answer:
        print("   (no exact '[C]' answer message found)")

    print("\n-- 5. Write of menu-gate-analysis.md --")
    for w, fp, content in writes:
        print(f"   [{w[:34]}] wrote {fp}")
    art = os.path.join(hdir, "menu-gate-analysis.md")
    art_exists = os.path.isfile(art)
    print(f"   artifact present in harvest: {art_exists}")
    if art_exists:
        print("   ---- menu-gate-analysis.md ----")
        print("   " + open(art).read().strip().replace("\n", "\n   ")[:800])
        print("   -------------------------------")

    print("\n-- 6. Ordering (events.jsonl ledger, chronological) --")
    ev = os.path.join(hdir, "events.jsonl")
    order = []
    if os.path.isfile(ev):
        for ln in open(ev, errors="replace"):
            try: r = json.loads(ln)
            except Exception: continue
            tool = r.get("tool"); detail = norm(r.get("detail") or r.get("last_assistant_message") or "")
            if tool in ("SendMessage", "Skill", "Write", "Agent", "Edit"):
                order.append((r.get("ts", "?")[-12:], r.get("agent_name") or r.get("agent_id", "")[:10] or "top", tool, detail[:70]))
        for ts, ag, tool, det in order:
            print(f"   {ts} {tool:12} {str(ag)[:18]:18} {det}")
    else:
        print("   (no events.jsonl — ordering from transcripts only)")

    # verdicts
    waited = "unknown"
    # waited=yes  iff a menu relay exists AND the analysis Write happened only after (heuristic:
    #   a Write with no preceding relay = self-answer). If relay skipped but Write happened -> waited=no.
    if relay in ("verbatim", "paraphrased"):
        waited = "yes"          # it asked and (by construction) blocked on the answer
    elif writes or art_exists:
        waited = "no"           # produced the artifact without ever asking
    else:
        waited = "n/a"
    continued = "yes" if art_exists else "no"
    self_answered = bool(choice_texts) or (relay == "skipped" and (writes or art_exists))

    print("\n-- 7. Self-answer / hallucinated-choice signals --")
    for w, txt in choice_texts:
        print(f"   [{w[:34]}] {txt}")
    if not choice_texts: print("   (no explicit self-choice text detected)")

    print("\n===== VERDICT =====")
    print(f"relay      = {relay}")
    print(f"waited     = {waited}")
    print(f"continued  = {continued}")
    print(f"self_answered_signal = {self_answered}")
    print(f"SENTINEL relay={relay} waited={waited} continued={continued} self_answered={self_answered}")

if __name__ == "__main__":
    main()
