"""Stop / SubagentStop: считает токены и стоимость сессии по транскриптам Claude Code
и дописывает приращение в costs.jsonl активного проекта с текущей стадией.

Транскрипт — JSONL, где у сообщений ассистента есть message.id, message.model, message.usage.
Одно сообщение может встречаться в нескольких строках — дедупликация по message.id.
Субагенты пишут свои транскрипты в <transcript без .jsonl>/subagents/*.jsonl.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ROOT, active_project, load_state, read_event  # noqa: E402

# cache_write — 5-минутный кэш (1.25× входа), cache_write_1h — часовой (2× входа), web_search — $10 за 1000 запросов.
KEYS = ["input", "output", "cache_read", "cache_write", "cache_write_1h", "web_search"]
WEB_SEARCH_USD = 0.01


def load_prices() -> tuple[dict, dict]:
    cfg = json.loads((ROOT / "config" / "pricing.json").read_text(encoding="utf-8"))
    return cfg["models"], cfg["default"]


def price_for(model: str, table: dict, default: dict) -> dict:
    best = ""
    for key in table:
        if key in model and len(key) > len(best):
            best = key
    return table[best] if best else default


def transcript_files(ev: dict) -> list[Path]:
    files = []
    for k in ("transcript_path", "agent_transcript_path"):
        if ev.get(k):
            files.append(Path(ev[k]))
    main = Path(ev["transcript_path"]) if ev.get("transcript_path") else None
    if main:
        sub = main.with_suffix("")
        if sub.is_dir():
            files += sorted(sub.rglob("*.jsonl"))
    seen, out = set(), []
    for f in files:
        if f.exists() and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def session_totals(files: list[Path], since: datetime | None = None) -> dict:
    msgs: dict[str, tuple[str, dict]] = {}
    for f in files:
        try:
            for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                m = r.get("message") or {}
                u = m.get("usage")
                model = m.get("model") or ""
                if not u or not model or model.startswith("<"):
                    continue
                if since and r.get("timestamp") and _ts(r["timestamp"]) < since:
                    continue  # до создания проекта — не относится к нему
                mid = m.get("id") or r.get("requestId") or r.get("uuid")
                msgs[mid] = (model, u)  # последняя строка сообщения несёт итоговый usage
        except Exception:
            continue
    tot: dict[str, dict] = {}
    for model, u in msgs.values():
        t = tot.setdefault(model, {v: 0 for v in KEYS})
        t["input"] += int(u.get("input_tokens") or 0)
        t["output"] += int(u.get("output_tokens") or 0)
        t["cache_read"] += int(u.get("cache_read_input_tokens") or 0)
        cw = int(u.get("cache_creation_input_tokens") or 0)
        h1 = int((u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0)
        t["cache_write_1h"] += min(h1, cw)
        t["cache_write"] += cw - min(h1, cw)  # 5-минутный кэш
        t["web_search"] += int((u.get("server_tool_use") or {}).get("web_search_requests") or 0)
    return tot


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def cost_usd(d: dict, pr: dict) -> float:
    per_m = (d["input"] * pr["input"] + d["output"] * pr["output"] + d["cache_read"] * pr["cache_read"]
             + d["cache_write"] * pr["cache_write"] + d["cache_write_1h"] * pr["input"] * 2)
    return per_m / 1_000_000 + d["web_search"] * WEB_SEARCH_USD


def main():
    ev = read_event()
    proj = active_project()
    if not proj or not ev.get("transcript_path"):
        return
    sid = ev.get("session_id") or Path(ev["transcript_path"]).stem
    created = load_state(proj).get("created")
    totals = session_totals(transcript_files(ev), _ts(created) if created else None)
    if not totals:
        return
    state_path = proj / ".cost_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    prev = state.get(sid, {})
    table, default = load_prices()
    stage = load_state(proj).get("stage", "?")
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    rows = []
    for model, t in totals.items():
        p = prev.get(model, {})
        delta = {k: max(0, t[k] - int(p.get(k, 0))) for k in t}
        if not any(delta.values()):
            continue
        usd = cost_usd(delta, price_for(model, table, default))
        row = {**delta, "cache_write": delta["cache_write"] + delta["cache_write_1h"]}  # для сводки strat cost
        row.pop("cache_write_1h")
        rows.append({"ts": ts, "stage": stage, "source": "claude-code", "session": sid[:8], "model": model,
                     **row, "usd": round(usd, 6)})
        prev[model] = {k: max(t[k], int(p.get(k, 0))) for k in t}
    if rows:
        with (proj / "costs.jsonl").open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    state[sid] = prev
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    tmp.replace(state_path)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print(f"cost_tracker: {e}", file=sys.stderr)
    sys.exit(0)
