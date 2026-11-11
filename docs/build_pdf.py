#!/usr/bin/env python3
"""Собирает docs/description.md → docs/description.pdf через HTML и печать в headless Chrome/Edge.

python docs/build_pdf.py [--md docs/description.md] [--out docs/description.pdf] [--html-only]
Нужно: pip install markdown; Chrome или Edge (путь можно задать переменной CHROME).
Картинки ![подпись](img/…) берутся из docs/img/; если файла нет — на его месте рамка «Скриншот: подпись».
"""
import argparse
import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DOCS = Path(__file__).resolve().parent
CSS = """
@page { size: A4; margin: 16mm 15mm 16mm 15mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1d1d1f; }
h1 { font-size: 22pt; margin: 0 0 4pt; color: #12305f; }
h2 { font-size: 15pt; color: #12305f; border-bottom: 2px solid #d7e2f5; padding-bottom: 3pt; margin-top: 18pt; break-after: avoid; }
h3 { font-size: 12pt; color: #24456f; margin-top: 12pt; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9.5pt; break-inside: auto; }
tr { break-inside: avoid; }
th, td { border: 1px solid #cfd6e0; padding: 4pt 6pt; vertical-align: top; text-align: left; }
th { background: #eef3fa; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9pt; background: #f3f4f6; padding: 0 2pt; border-radius: 2pt; }
blockquote { margin: 6pt 0; padding: 4pt 10pt; border-left: 3px solid #8aa8d8; background: #f6f9fe; color: #33415c; }
.diagram { margin: 8pt 0 12pt; break-inside: avoid; }
.diagram svg { width: 100%; height: auto; }
figure { margin: 8pt 0; break-inside: avoid; text-align: center; }
figure img { max-width: 100%; border: 1px solid #ccd; }
figcaption { font-size: 9pt; color: #555; margin-top: 3pt; }
.shot { border: 2px dashed #c0392b; color: #c0392b; background: #fff6f5; padding: 26pt 10pt; text-align: center;
        font-size: 10pt; margin: 8pt 0; break-inside: avoid; }
em { color: #8a5a00; }
"""


def find_browser() -> str | None:
    cands = [os.environ.get("CHROME"), shutil.which("chrome"), shutil.which("google-chrome"), shutil.which("chromium"),
             shutil.which("msedge"), r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    return next((c for c in cands if c and Path(c).exists()), None)


def figures(body: str, base: Path) -> str:
    def repl(m):
        alt, src = html.unescape(m.group("alt")), m.group("src")
        if (base / src).exists():
            return f'<figure><img src="{src}" alt="{html.escape(alt)}"><figcaption>{html.escape(alt)}</figcaption></figure>'
        return f'<div class="shot">Скриншот: {html.escape(alt)}<br><small>(положите файл docs/{html.escape(src)})</small></div>'
    body = re.sub(r'<p>\s*<img alt="(?P<alt>[^"]*)" src="(?P<src>[^"]+)"\s*/?>\s*</p>', repl, body)
    return body


LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s")


def normalize_lists(md: str) -> str:
    """Python-Markdown требует пустую строку перед списком и отступ 4 пробела для вложенности;
    исходник пишется в привычном стиле (как на GitHub) — приводим его здесь."""
    out, prev, in_fence, in_html = [], "", False, False
    for line in md.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_fence = not in_fence
        if s.startswith("<div") or s.startswith("<svg"):
            in_html = True
        if not in_fence and not in_html:
            if line.startswith(" ") and s:
                n = len(line) - len(line.lstrip(" "))
                line = " " * (n * 2) + line.lstrip(" ")
            if LIST_RE.match(line) and prev.strip() and not LIST_RE.match(prev):
                out.append("")
        if s.startswith("</div>"):
            in_html = False
        out.append(line)
        prev = line
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=str(DOCS / "description.md"))
    ap.add_argument("--out", default=str(DOCS / "description.pdf"))
    ap.add_argument("--html-only", action="store_true")
    a = ap.parse_args()
    try:
        import markdown
    except ImportError:
        sys.exit("нужен пакет markdown: pip install markdown")
    md_path = Path(a.md)
    body = markdown.markdown(normalize_lists(md_path.read_text(encoding="utf-8")), extensions=["tables", "fenced_code", "md_in_html"])
    body = figures(body, md_path.parent)
    title = re.search(r"^# (.+)$", md_path.read_text(encoding="utf-8"), re.M)
    page = (f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>{html.escape(title.group(1) if title else "Описание")}</title>'
            f"<style>{CSS}</style></head><body>{body}</body></html>")
    html_path = md_path.with_suffix(".html")
    html_path.write_text(page, encoding="utf-8")
    if a.html_only:
        print(html_path)
        return
    browser = find_browser()
    if not browser:
        sys.exit(f"Chrome/Edge не найден; HTML готов: {html_path} — напечатайте его в PDF из браузера")
    out = Path(a.out).resolve()
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}",
           html_path.resolve().as_uri()]
    subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    print(out)


if __name__ == "__main__":
    main()
