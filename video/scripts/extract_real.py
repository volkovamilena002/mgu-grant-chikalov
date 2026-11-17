"""Достаёт из расшифровок реальных сессий Claude Code нужные записи ДОСЛОВНО -> video/data/real.json.
Запуск: PYTHONIOENCODING=utf-8 python video/scripts/extract_real.py
Каждая запись: имя -> {file, idx (номер строки JSONL), kind, text}. Сценарий видео берёт только отсюда."""
import json, os, re, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
# Claude Code хранит расшифровки в ~/.claude/projects/<путь репозитория, где не-буквы и не-цифры заменены на «-»>
HOME = os.path.join(os.path.expanduser("~/.claude/projects"), re.sub(r"[^A-Za-z0-9]", "-", ROOT))
MAIN = os.path.join(HOME, "74f9e4dc-ddbb-4f93-99a7-4103b812ab7f.jsonl")
RESUME = os.path.join(HOME, "48f1a134-06c4-4cde-bfca-d27947e010c3.jsonl")
# имя: (файл, строка, вид блока: text|tool_use|tool_result|attachment, номер блока этого вида)
SPEC = {
 "kick_user":      (MAIN, 3, "text", 0),
 "init_cmd":       (MAIN, 59, "tool_use", 0),
 "init_res":       (MAIN, 60, "tool_result", 0),
 "ask_kick":       (MAIN, 100, "tool_use", 0),
 "ask_kick_res":   (MAIN, 107, "tool_result", 0),
 "validate_warn":  (MAIN, 142, "tool_result", 0),
 "validate_ok":    (MAIN, 165, "tool_result", 0),
 "brief_done":     (MAIN, 170, "text", 0),
 "ask_g1":         (MAIN, 173, "tool_use", 0),
 "gate_g1":        (MAIN, 178, "tool_use", 0),
 "gate_g1_res":    (MAIN, 185, "tool_result", 0),
 "steps_start":    (MAIN, 275, "tool_use", 0),
 "steps_start_res":(MAIN, 276, "tool_result", 0),
 "ag_r1": (MAIN, 290, "tool_use", 0), "ag_r2": (MAIN, 291, "tool_use", 0), "ag_r3": (MAIN, 292, "tool_use", 0),
 "ag_r45": (MAIN, 293, "tool_use", 0), "ag_r67": (MAIN, 294, "tool_use", 0),
 "collect_done":   (MAIN, 485, "text", 0),
 "err_note":       (MAIN, 420, "tool_use", 0),
 "sit_final":      (MAIN, 562, "text", 0),
 "ag_redteam1":    (MAIN, 620, "tool_use", 0),
 "redteam1_report":(MAIN, 636, "text", 0),
 "ask_g2":         (MAIN, 704, "tool_use", 0),
 "ask_g2_res":     (MAIN, 705, "tool_result", 0),
 "g2_text":        (MAIN, 723, "text", 0),
 "ag_redteam2":    (MAIN, 796, "tool_use", 0),
 "redteam2_report":(MAIN, 817, "text", 0),
 "claim_supersede":(MAIN, 828, "tool_use", 0),
 "ag_judge":       (MAIN, 948, "tool_use", 0),
 "judge_report":   (MAIN, 1006, "text", 0),
 "log_judge":      (MAIN, 1023, "tool_use", 0),
 "ask_g3":         (MAIN, 1055, "tool_use", 0),
 "ask_g3_res":     (MAIN, 1056, "tool_result", 0),
 "gate_g3":        (MAIN, 1058, "tool_use", 0),
 "gate_g3_res":    (MAIN, 1065, "tool_result", 0),
 "g3_text":        (MAIN, 1072, "text", 0),
 "gate_g2": (MAIN, 709, "tool_use", 0),
 "gate_g2_res": (MAIN, 710, "tool_result", -1),
 "strategy_text": (MAIN, 902, "text", 0),
 "validate_warn2": (MAIN, 782, "tool_result", 0),
 "claim_add_res": (MAIN, 835, "tool_result", -1),
 "hook":           (RESUME, 2, "attachment", 0),
 "next_user":      (RESUME, 3, "text", 0),
 "next_status_cmd":(RESUME, 43, "tool_use", 0),
 "next_status_res":(RESUME, 44, "tool_result", 0),
 "next_text":      (RESUME, 74, "text", 0),
 "next_ask":       (RESUME, 71, "tool_use", 0),
 "yes_check":      (RESUME, 83, "text", 0),
 "ag_law":         (RESUME, 97, "tool_use", 0),
 "ag_law_text":    (RESUME, 109, "text", 0),
 "law_handback":   (RESUME, 117, "text", 0),
 "claims_show_cmd":(RESUME, 129, "tool_use", 0),
 "claims_show_res":(RESUME, 130, "tool_result", 0),
 "law_log_cmd":    (RESUME, 145, "tool_use", 0),
 "law_log_res":    (RESUME, 146, "tool_result", 0),
 "law_final":      (RESUME, 153, "text", 0),
}
JOIN = chr(10)
out = {}
need = {}
for k, (f, i, kind, n) in SPEC.items(): need.setdefault(f, {})[i] = (k, kind, n)
for f, want in need.items():
    with open(f, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i not in want: continue
            k, kind, n = want[i]; o = json.loads(line); text = None
            if kind == "attachment":
                text = o.get("attachment", {}).get("content")
            else:
                c = o.get("message", {}).get("content", "")
                if isinstance(c, str): c = [{"type": "text", "text": c}]
                bl = [b for b in c if b.get("type") == kind]
                if n == -1 and kind == "tool_result":
                    parts = []
                    for b in bl:
                        r = b.get("content"); parts.append(JOIN.join(x.get("text", "") for x in r) if isinstance(r, list) else (r or ""))
                    text = JOIN.join(parts)
                elif len(bl) > n:
                    b = bl[n]
                    if kind == "text": text = b["text"]
                    elif kind == "tool_use": text = json.dumps({"name": b["name"], **b["input"]}, ensure_ascii=False)
                    else:
                        r = b.get("content"); text = "\n".join(x.get("text", "") for x in r) if isinstance(r, list) else (r or "")
            out[k] = {"file": os.path.basename(f), "idx": i, "kind": kind, "ts": o.get("timestamp"), "text": text}
miss = [k for k in SPEC if k not in out or out[k]["text"] is None]
os.makedirs(os.path.join(os.path.dirname(__file__), "..", "data"), exist_ok=True)
# Выгрузка лежит в репозитории: убираем путь до репозитория и домашнюю папку (имя пользователя)
_text = json.dumps(out, ensure_ascii=False, indent=1)
_sep = r"(?:\\+|/)"
_text = re.sub(_sep.join(re.escape(p) for p in re.split(r"[\\/]", ROOT)) + _sep + "?", "", _text, flags=re.I)
_text = re.sub(_sep.join(re.escape(p) for p in re.split(r"[\\/]", os.path.expanduser("~"))), "~", _text, flags=re.I)
_text = _text.replace(re.sub(r"[^A-Za-z0-9]", "-", os.path.expanduser("~")), "~")
with open(os.path.join(os.path.dirname(__file__), "..", "data", "real.json"), "w", encoding="utf-8") as fh:
    fh.write(_text)
print("saved", len(out), "missing:", miss)
