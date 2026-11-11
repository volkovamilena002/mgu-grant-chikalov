"""SessionStart: показывает агенту статус активного проекта — так работа продолжается в новом чате."""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ROOT, active_project, read_event  # noqa: E402

read_event()
try:
    proj = active_project()
    if not proj:
        print("[Стратег] Активного проекта нет. Если пользователь приносит задачу — начни с навыка /kickoff; "
              "список проектов: python tools/strat.py list.")
        sys.exit(0)
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "strat.py"), "status", "--journal", "5"],
                       capture_output=True, text=True, encoding="utf-8", timeout=20, cwd=ROOT)
    print("[Стратег] Состояние активного проекта (продолжи с «Следующий шаг», навык /next):")
    print(r.stdout.strip() or r.stderr.strip())
except Exception as e:  # noqa: BLE001
    print(f"[Стратег] не удалось прочитать статус: {e}")
sys.exit(0)
