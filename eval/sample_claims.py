#!/usr/bin/env python3
"""Выборка утверждений для проверки по источникам и автоматические метрики покрытия ссылками.

python eval/sample_claims.py agent    --project esim-travel        --out eval/runs/<run>/sample-agent.jsonl
python eval/sample_claims.py baseline --file eval/runs/<run>/baseline.md --out eval/runs/<run>/sample-baseline.jsonl

Единица проверки — строка документа с хотя бы одной ссылкой (агент: [C#], базовый способ: URL).
Выборка случайная с фиксированным seed (воспроизводима). Также печатает метрики:
строк с числами, из них со ссылкой — одинаковым правилом для обоих способов.
"""
import argparse
import importlib.util
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("strat", ROOT / "tools" / "strat.py")
strat = importlib.util.module_from_spec(spec)
sys.argv, _argv = sys.argv[:1], sys.argv
spec.loader.exec_module(strat)
sys.argv = _argv

URL_RE = re.compile(r"\]\((https?://[^)\s]+)\)|(?<![(\[])(https?://[^\s)\]]+)")
AGENT_DOCS = ["03-situation.md", "04-options.md", "05-strategy-product.md", "06-strategy-comms.md", "07-validation-plan.md"]


def content_lines(text: str):
    in_code = False
    for i, line in enumerate(text.splitlines(), 1):
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not s or s.startswith(("#", ">", "<!--", "|---", "| ---")):
            continue
        yield i, s


def urls_in(line: str) -> list[str]:
    return [a or b for a, b in URL_RE.findall(line)]


def coverage(lines) -> dict:
    num = [l for l in lines if strat.NUMERIC_RE.search(l["text"])]
    num_ref = [l for l in num if l["refs"]]
    return {"lines": len(lines), "lines_with_ref": sum(1 for l in lines if l["refs"]),
            "numeric_lines": len(num), "numeric_with_ref": len(num_ref),
            "numeric_ref_share": round(len(num_ref) / len(num), 3) if num else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["agent", "baseline"])
    ap.add_argument("--project")
    ap.add_argument("--file")
    ap.add_argument("--out", required=True)
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    lines = []
    if a.mode == "agent":
        pdir = ROOT / "projects" / a.project
        claims = {c["id"]: c for c in strat.read_jsonl(pdir / "claims.jsonl")}
        sources = {s["id"]: s for s in strat.read_jsonl(pdir / "sources.jsonl")}
        for doc in AGENT_DOCS:
            for i, s in content_lines((pdir / "outputs" / doc).read_text(encoding="utf-8")):
                ids = sorted(x for x in strat._refs_in_text(s) if x.startswith("C"))
                refs = []
                for cid in ids:
                    c = claims.get(cid, {})
                    refs.append({"id": cid, "type": c.get("type"), "status": c.get("status"), "text": c.get("text"),
                                 "sources": [{"id": sid, "url": sources.get(sid, {}).get("ref"),
                                              "reliability": sources.get(sid, {}).get("reliability")}
                                             for sid in c.get("sources", [])],
                                 "depends_on": c.get("depends_on", [])})
                lines.append({"doc": doc, "line": i, "text": s, "refs": refs})
    else:
        f = Path(a.file)
        for i, s in content_lines(f.read_text(encoding="utf-8")):
            lines.append({"doc": f.name, "line": i, "text": s, "refs": [{"url": u} for u in urls_in(s)]})
    cov = coverage(lines)
    pool = [l for l in lines if l["refs"]]
    random.Random(a.seed).shuffle(pool)
    sample = pool[: a.n]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for k, l in enumerate(sample, 1):
            fh.write(json.dumps({"item": f"{a.mode[0].upper()}{k}", **l}, ensure_ascii=False) + "\n")
    (out.with_name(out.stem + "-coverage.json")).write_text(json.dumps(cov, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"sampled": len(sample), **cov}, ensure_ascii=False))


if __name__ == "__main__":
    main()
