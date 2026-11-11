#!/usr/bin/env python3
"""Стоимость по транскриптам Claude Code (основная сессия или субагент) — по тем же ценам, что хук.

python eval/transcript_cost.py <transcript.jsonl> [ещё файлы…] [--since ISO] [--until ISO]
Печатает токены и $ по моделям и итог (JSON с флагом --json).
"""
import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("cost_tracker", ROOT / ".claude" / "hooks" / "cost_tracker.py")
ct = importlib.util.module_from_spec(spec)
sys.argv, _argv = sys.argv[:1], sys.argv  # модуль хука не должен видеть наши аргументы
spec.loader.exec_module(ct)
sys.argv = _argv
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    since = ct._ts(a.since) if a.since else None
    msgs = ct.session_messages([Path(f) for f in a.files], since)
    if a.until:
        until = ct._ts(a.until)
        keep = {}
        for f in a.files:
            for line in Path(f).read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                mid = (r.get("message") or {}).get("id")
                if mid in msgs and r.get("timestamp") and ct._ts(r["timestamp"]) <= until:
                    keep[mid] = msgs[mid]
        msgs = keep
    table, default = ct.load_prices()
    out = {"models": {}, "usd": 0.0, "messages": len(msgs)}
    for model, d in ct.aggregate(msgs.values()).items():
        usd = ct.cost_usd(d, ct.price_for(model, table, default))
        out["models"][model] = {**d, "usd": round(usd, 4)}
        out["usd"] += usd
    out["usd"] = round(out["usd"], 4)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    for m, d in out["models"].items():
        print(f"{m:<22} ${d['usd']:.3f}  out {d['output']:,}  cache_read {d['cache_read']:,}  web_search {d['web_search']}".replace(",", " "))
    print(f"Итого: ${out['usd']:.3f} ({out['messages']} сообщений)")


if __name__ == "__main__":
    main()
