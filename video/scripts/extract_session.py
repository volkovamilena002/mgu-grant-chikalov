"""Экстрактор расшифровки сессии Claude Code (JSONL) -> читаемый текст.
python video/scripts/extract_session.py <файл.jsonl> [--max N]   (PYTHONIOENCODING=utf-8)
Печатает: [idx] USER / ASSISTANT / TOOL_USE / TOOL_RESULT, текст не переписывается, длинное режется с «…»."""
import json, sys

def clip(s, n):
    s = s.strip()
    return s if len(s) <= n else s[:n] + "…"

def blocks(content):
    if isinstance(content, str):
        yield ("text", content); return
    for b in content:
        t = b.get("type")
        if t == "text": yield ("text", b["text"])
        elif t == "tool_use": yield ("tool_use", b)
        elif t == "tool_result":
            c = b.get("content")
            if isinstance(c, list): c = "\n".join(x.get("text", "") for x in c if isinstance(x, dict))
            yield ("tool_result", {"id": b.get("tool_use_id"), "text": c or ""})

def main():
    path = sys.argv[1]
    mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 600
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            try: o = json.loads(line)
            except Exception: continue
            t = o.get("type")
            if t not in ("user", "assistant"): continue
            m = o.get("message", {})
            ts = (o.get("timestamp") or "")[11:19]
            for kind, b in blocks(m.get("content", "")):
                if kind == "text":
                    print(f"[{i} {ts}] {t.upper()}: {clip(b, mx)}\n")
                elif kind == "tool_use":
                    print(f"[{i} {ts}] TOOL_USE {b['name']} {clip(json.dumps(b['input'], ensure_ascii=False), mx)}\n")
                else:
                    print(f"[{i} {ts}] TOOL_RESULT: {clip(b['text'], mx)}\n")
main()
