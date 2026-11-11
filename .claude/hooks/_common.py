"""Общие функции хуков. Хуки никогда не должны ронять сессию: все ошибки глушатся."""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2])
PROJECTS = ROOT / "projects"


def read_event() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def active_project() -> Path | None:
    slug = os.environ.get("STRAT_PROJECT")
    f = PROJECTS / ".active"
    if not slug and f.exists():
        slug = f.read_text(encoding="utf-8").strip()
    if slug and (PROJECTS / slug / "state.json").exists():
        return PROJECTS / slug
    return None


def load_state(proj: Path) -> dict:
    try:
        return json.loads((proj / "state.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def journal(proj: Path, text: str, kind: str) -> None:
    try:
        stage = load_state(proj).get("stage", "?")
        ts = datetime.now().astimezone().isoformat(timespec="seconds")
        with (proj / "journal.md").open("a", encoding="utf-8") as f:
            f.write(f"- {ts} · [{kind}] · {stage} · {text}\n")
    except Exception:
        pass


def emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))
