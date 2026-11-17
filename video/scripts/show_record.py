"""Печать записи сессии целиком: python show_record.py <jsonl> <idx> [<idx>…]"""
import json, sys
path = sys.argv[1]; want = set(map(int, sys.argv[2:]))
with open(path, encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i in want:
            o = json.loads(line); c = o.get("message", {}).get("content", "")
            if isinstance(c, str): print(f"--- [{i}]", c); continue
            for b in c:
                if b.get("type") == "text": print(f"--- [{i}] text:", b["text"])
                elif b.get("type") == "tool_use": print(f"--- [{i}] tool_use:", json.dumps(b["input"], ensure_ascii=False, indent=1))
                elif b.get("type") == "tool_result":
                    r = b.get("content"); r = "\n".join(x.get("text", "") for x in r) if isinstance(r, list) else r
                    print(f"--- [{i}] result:", r)
