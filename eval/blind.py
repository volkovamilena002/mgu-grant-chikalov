#!/usr/bin/env python3
"""Готовит обезличенные документы для слепой оценки по рубрике.

python eval/blind.py --run eval/runs/<run> --project <slug> [--seed 7]
Создаёт <run>/blind/doc-1.md и doc-2.md (порядок случайный, фиксированный seed) и <run>/blind/key.json.
Агентский комплект = outputs 03–07 подряд; базовый = baseline.md. Слова, выдающие способ, заменяются.
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DOCS = ["03-situation.md", "04-options.md", "05-strategy-product.md", "06-strategy-comms.md", "07-validation-plan.md"]
REPLACE = [(r"red-team", "критик"), (r"[Аа]гент(а|ом|у|е)?\b", "автор"), (r"`[^`]*\.md`", "соседний раздел"),
           (r"\(`0\d`\)", ""), (r"`0\d`", "соседний раздел")]


def scrub(t: str) -> str:
    for a, b in REPLACE:
        t = re.sub(a, b, t)
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    run = Path(a.run)
    agent = "\n\n---\n\n".join((ROOT / "projects" / a.project / "outputs" / d).read_text(encoding="utf-8") for d in DOCS)
    base = (run / "baseline.md").read_text(encoding="utf-8")
    pair = [("agent", scrub(agent)), ("baseline", scrub(base))]
    random.Random(a.seed).shuffle(pair)
    out = run / "blind"
    out.mkdir(exist_ok=True)
    key = {}
    for i, (name, text) in enumerate(pair, 1):
        (out / f"doc-{i}.md").write_text(text, encoding="utf-8")
        key[f"doc-{i}"] = name
    (out / "key.json").write_text(json.dumps(key, ensure_ascii=False), encoding="utf-8")
    print("готово:", ", ".join(f"doc-{i}" for i in range(1, len(pair) + 1)), "(ключ в key.json — не показывать оценщикам)")


if __name__ == "__main__":
    main()
