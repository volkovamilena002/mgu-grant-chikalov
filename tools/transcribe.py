#!/usr/bin/env python3
"""Локальная расшифровка аудио/видео в текст (faster-whisper).

python tools/transcribe.py <файл> [--model small] [--lang ru] [--out путь.txt]
Пишет расшифровку с таймкодами рядом с файлом (или в --out) и печатает путь.
Требует: pip install faster-whisper (и ffmpeg в PATH для видео).
"""
import argparse
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--model", default="small", help="tiny|base|small|medium|large-v3")
    ap.add_argument("--lang", default="ru")
    ap.add_argument("--out")
    a = ap.parse_args()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper не установлен: pip install faster-whisper", file=sys.stderr)
        sys.exit(2)
    src = Path(a.file)
    out = Path(a.out) if a.out else src.with_suffix(".transcript.md")
    model = WhisperModel(a.model, compute_type="int8")
    segments, info = model.transcribe(str(src), language=a.lang)
    lines = [f"# Расшифровка: {src.name}", "", f"_модель whisper-{a.model}, язык {info.language}; автоматическая, возможны ошибки_", ""]
    for s in segments:
        m, sec = divmod(int(s.start), 60)
        lines.append(f"[{m:02d}:{sec:02d}] {s.text.strip()}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
