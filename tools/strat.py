#!/usr/bin/env python3
"""strat — детерминированное ядро агента «Стратег».

Хранит состояние задачи, реестр источников, реестр утверждений, решения,
журнал действий и расходы. Проверяет итоговые документы на связь с источниками.
Только стандартная библиотека Python 3.10+.

Запуск:  python tools/strat.py <команда> ...   (подсказка: python tools/strat.py -h)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(os.environ.get("STRAT_ROOT") or Path(__file__).resolve().parent.parent)
PROJECTS = ROOT / "projects"
TEMPLATES = ROOT / "templates"
CONFIG = ROOT / "config"
ACTIVE_FILE = PROJECTS / ".active"

STAGES = ["brief", "research_plan", "collect", "situation", "options", "strategy", "verify", "support"]
STAGE_TITLES = {
    "brief": "1. Постановка задачи",
    "research_plan": "2. План исследования",
    "collect": "3. Сбор материалов",
    "situation": "4. Картина ситуации",
    "options": "5. Варианты и возражения",
    "strategy": "6. Стратегии и план проверки",
    "verify": "7. Финальная проверка",
    "support": "8. Сопровождение решения",
}
STAGE_SKILL = {
    "brief": "kickoff", "research_plan": "research-plan", "collect": "collect",
    "situation": "situation", "options": "options", "strategy": "strategy",
    "verify": "verify", "support": "decisions",
}
# Ворота: чтобы войти в стадию (ключ), нужно одобрение человека (значение).
GATE_BEFORE = {"research_plan": "G1", "strategy": "G2", "support": "G3"}
GATE_TITLES = {
    "G1": "Бриф подтверждён",
    "G2": "Вариант выбран",
    "G3": "Стратегия утверждена",
}
CLAIM_TYPES = {
    "fact": "факт (подтверждён источником)",
    "hypothesis": "гипотеза (требует проверки)",
    "forecast": "прогноз (оценка будущего)",
    "assumption": "допущение (принято без проверки)",
    "synthetic": "синтетика (ответ ИИ-респондента, не доказательство)",
}
SOURCE_KINDS = ["web", "document", "table", "data", "interview", "synthetic", "user", "image", "audio", "video", "analysis"]
RELIABILITY = ["high", "medium", "low"]

OUTPUT_FILES = {
    "brief": "01-brief.md",
    "research_plan": "02-research-plan.md",
    "situation": "03-situation.md",
    "options": "04-options.md",
    "strategy_product": "05-strategy-product.md",
    "strategy_comms": "06-strategy-comms.md",
    "validation_plan": "07-validation-plan.md",
}
TEMPLATE_MARKER = "<!-- template: не заполнено -->"
# Обязательные разделы заполненных документов (проверяет `validate`).
REQUIRED_HEADINGS = {
    "01-brief.md": ["Вопрос", "Цель", "Получатель", "Ограничения", "Доступные данные"],
    "03-situation.md": ["Что известно", "Чего мы не знаем"],
    "04-options.md": ["Оставить как есть", "Возражения", "Сравнение"],
    "05-strategy-product.md": ["Аудитория и её задача", "Альтернативы", "Выбранное направление",
                               "Осознанные отказы", "Экономика"],
    "06-strategy-comms.md": ["Аудитория и ситуация", "Барьер", "Ключевое сообщение",
                             "Подтверждение", "Каналы", "Обещания"],
    "07-validation-plan.md": ["Ожидаемое изменение", "С чем сравниваем", "Срок наблюдения",
                              "Нежелательные последствия"],
}
STRATEGY_FILES = {"05-strategy-product.md", "06-strategy-comms.md", "07-validation-plan.md"}
# Документ должен быть заполнен, когда проект ушёл дальше этой стадии.
DOC_STAGE = {"01-brief.md": "brief", "02-research-plan.md": "research_plan", "03-situation.md": "situation",
             "04-options.md": "options", "05-strategy-product.md": "strategy",
             "06-strategy-comms.md": "strategy", "07-validation-plan.md": "strategy"}
NUMERIC_RE = re.compile(r"\d[\d\s.,]*\s?(%|₽|руб|млн|млрд|тыс|\$|€|п\.п\.|раз[а]?\b|пользоват|клиент|абонент|чел)", re.I)
REF_BLOCK_RE = re.compile(r"\[((?:[CS]\d+)(?:\s*[,;]\s*[CS]\d+)*)\]")


# ----------------------------------------------------------------- утилиты
def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def die(msg: str, code: int = 1):
    print(f"ошибка: {msg}", file=sys.stderr)
    sys.exit(code)


def read_json(p: Path, default=None):
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p: Path, data) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"предупреждение: {p.name}:{i} — повреждённая строка пропущена", file=sys.stderr)
    return out


def write_jsonl(p: Path, rows: list[dict]) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    os.replace(tmp, p)


def append_jsonl(p: Path, row: dict) -> None:
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def next_id(prefix: str, rows: list[dict]) -> str:
    n = 0
    for r in rows:
        m = re.fullmatch(rf"{prefix}(\d+)", str(r.get("id", "")))
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}{n + 1}"


def split_ids(s: str | None) -> list[str]:
    if not s:
        return []
    return [x.strip().upper() for x in re.split(r"[,\s;]+", s) if x.strip()]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", s.strip().lower(), flags=re.U).strip("-")
    return s or "project"


# ----------------------------------------------------------------- проект
class Project:
    def __init__(self, slug: str):
        self.slug = slug
        self.dir = PROJECTS / slug
        if not (self.dir / "state.json").exists():
            die(f"проект «{slug}» не найден в {PROJECTS}. Создайте: strat init <slug>")

    # пути
    @property
    def state_path(self): return self.dir / "state.json"
    @property
    def sources_path(self): return self.dir / "sources.jsonl"
    @property
    def claims_path(self): return self.dir / "claims.jsonl"
    @property
    def decisions_path(self): return self.dir / "decisions.jsonl"
    @property
    def costs_path(self): return self.dir / "costs.jsonl"
    @property
    def steps_path(self): return self.dir / "steps.jsonl"
    @property
    def journal_path(self): return self.dir / "journal.md"
    @property
    def outputs(self): return self.dir / "outputs"
    @property
    def inputs(self): return self.dir / "inputs"

    def state(self) -> dict:
        return read_json(self.state_path, {})

    def save_state(self, st: dict) -> None:
        st["updated"] = now()
        write_json(self.state_path, st)

    def sources(self): return read_jsonl(self.sources_path)
    def claims(self): return read_jsonl(self.claims_path)
    def decisions(self): return read_jsonl(self.decisions_path)

    def log(self, text: str, kind: str = "action") -> None:
        st = self.state()
        stage = st.get("stage", "?")
        with self.journal_path.open("a", encoding="utf-8") as f:
            f.write(f"- {now()} · [{kind}] · {stage} · {text}\n")


def active_slug(explicit: str | None = None) -> str | None:
    if explicit:
        return explicit
    if os.environ.get("STRAT_PROJECT"):
        return os.environ["STRAT_PROJECT"]
    if ACTIVE_FILE.exists():
        s = ACTIVE_FILE.read_text(encoding="utf-8").strip()
        return s or None
    return None


def get_project(args) -> Project:
    slug = active_slug(getattr(args, "project", None))
    if not slug:
        die("нет активного проекта. Создайте: strat init <slug> или выберите: strat use <slug>")
    return Project(slug)


# ----------------------------------------------------------------- команды: проект
def cmd_init(args):
    slug = slugify(args.slug)
    d = PROJECTS / slug
    if (d / "state.json").exists():
        die(f"проект «{slug}» уже существует. Продолжить: strat use {slug}")
    for sub in ["inputs", "inputs/_md", "outputs", "analysis", "interviews", "decisions"]:
        (d / sub).mkdir(parents=True, exist_ok=True)
    state = {
        "slug": slug,
        "title": args.title or slug,
        "created": now(),
        "updated": now(),
        "stage": "brief",
        "gates": {g: {"status": "pending", "note": "", "at": None} for g in GATE_TITLES},
        "brief": {"question": args.question or "", "goal": "", "recipient": "", "decision": "",
                  "deadline": "", "constraints": [], "data_available": []},
        "open_questions": [],
        "allowed_domains": [],
        "blocked_domains": [],
        "next_step": "Уточнить у руководителя вопрос, цель, получателя, ограничения и доступные данные (/kickoff).",
    }
    write_json(d / "state.json", state)
    for f in ["sources.jsonl", "claims.jsonl", "decisions.jsonl", "costs.jsonl", "steps.jsonl"]:
        (d / f).touch()
    (d / "journal.md").write_text(f"# Журнал проекта «{state['title']}»\n\n"
                                  "Только дописывается. Формат: время · [вид] · стадия · действие.\n\n",
                                  encoding="utf-8")
    if TEMPLATES.exists():
        for key, name in OUTPUT_FILES.items():
            src = TEMPLATES / name
            if src.exists():
                shutil.copy(src, d / "outputs" / name)
    PROJECTS.mkdir(exist_ok=True)
    ACTIVE_FILE.write_text(slug, encoding="utf-8")
    p = Project(slug)
    p.log(f"Проект создан: {state['title']}", "init")
    print(f"Создан проект «{slug}» в {d}\nОн выбран активным. Следующий шаг: {state['next_step']}")


def cmd_use(args):
    p = Project(slugify(args.slug))
    ACTIVE_FILE.write_text(p.slug, encoding="utf-8")
    print(f"Активный проект: {p.slug}")


def cmd_list(args):
    cur = active_slug()
    if not PROJECTS.exists():
        print("Проектов нет.")
        return
    rows = []
    for d in sorted(PROJECTS.iterdir()):
        st = read_json(d / "state.json")
        if st:
            mark = "*" if d.name == cur else " "
            rows.append(f"{mark} {d.name:<28} {STAGE_TITLES.get(st['stage'], st['stage']):<32} {st.get('title','')}")
    print("\n".join(rows) if rows else "Проектов нет.")


def stage_index(s: str) -> int:
    return STAGES.index(s)


def cmd_status(args):
    p = get_project(args)
    st = p.state()
    sources, claims = p.sources(), p.claims()
    active_claims = [c for c in claims if c.get("status", "active") == "active"]
    by_type: dict[str, int] = {}
    for c in active_claims:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    flagged = [c["id"] for c in active_claims if c.get("needs_review")]
    open_q = [q for q in st.get("open_questions", []) if q.get("status") == "open"]
    pending_steps = _pending_steps(p)
    cost = _cost_summary(p)
    if args.json:
        print(json.dumps({
            "project": p.slug, "title": st.get("title"), "stage": st["stage"],
            "gates": st["gates"], "next_step": st.get("next_step"),
            "sources": len(sources), "claims": by_type, "needs_review": flagged,
            "open_questions": open_q, "pending_steps": pending_steps, "cost_usd": cost["usd"],
        }, ensure_ascii=False, indent=2))
        return
    print(f"Проект: {st.get('title')}  ({p.slug})")
    print(f"Стадия: {STAGE_TITLES[st['stage']]}   → навык /{STAGE_SKILL[st['stage']]}")
    gates = "  ".join(f"{g}:{'✔' if v['status']=='approved' else ('✘' if v['status']=='rejected' else '…')}"
                      for g, v in st["gates"].items())
    print(f"Ворота: {gates}   (G1 бриф · G2 выбор варианта · G3 утверждение)")
    print(f"Источники: {len(sources)}   Утверждения: " +
          (", ".join(f"{k}={v}" for k, v in sorted(by_type.items())) or "0"))
    if flagged:
        print(f"Требуют пересмотра: {', '.join(flagged)}")
    if open_q:
        print("Открытые вопросы:")
        for q in open_q:
            print(f"  {q['id']}: {q['text']}" + (f"  (важно: {q['why']})" if q.get("why") else ""))
    if pending_steps:
        print("Незавершённые шаги (начаты, но не закрыты — проверьте, прежде чем повторять):")
        for s in pending_steps:
            print(f"  {s['key']}: {s.get('desc','')}  (начат {s['ts']})")
    print(f"Расходы: ${cost['usd']:.2f}  (токены: вход {cost['input']:,}, выход {cost['output']:,})".replace(",", " "))
    print(f"Следующий шаг: {st.get('next_step') or '—'}")
    if args.journal:
        lines = [l for l in p.journal_path.read_text(encoding="utf-8").splitlines() if l.startswith("- ")]
        print(f"\nПоследние записи журнала:")
        for l in lines[-args.journal:]:
            print("  " + l[2:])


def cmd_stage(args):
    p = get_project(args)
    st = p.state()
    new = args.name
    if new not in STAGES:
        die(f"неизвестная стадия «{new}». Варианты: {', '.join(STAGES)}")
    # проверяем все ворота на пути к новой стадии
    for s in STAGES[: stage_index(new) + 1]:
        gate = GATE_BEFORE.get(s)
        if gate and st["gates"][gate]["status"] != "approved" and not args.force:
            die(f"нельзя перейти к «{STAGE_TITLES[new]}»: ворота {gate} («{GATE_TITLES[gate]}») не одобрены "
                f"человеком. Спросите руководителя и выполните: strat gate {gate} approve --note \"...\"", 2)
    old = st["stage"]
    st["stage"] = new
    st["next_step"] = args.next or f"Выполнить стадию «{STAGE_TITLES[new]}» (навык /{STAGE_SKILL[new]})."
    p.save_state(st)
    p.log(f"Стадия: {old} → {new}" + (" (принудительно)" if args.force else ""), "stage")
    print(f"Стадия: {STAGE_TITLES[new]}")


def cmd_next(args):
    p = get_project(args)
    st = p.state()
    st["next_step"] = args.text
    p.save_state(st)
    print("Следующий шаг сохранён.")


def cmd_gate(args):
    p = get_project(args)
    st = p.state()
    g = args.gate.upper()
    if g not in st["gates"]:
        die(f"нет ворот {g}")
    status = {"approve": "approved", "reject": "rejected", "reset": "pending"}[args.action]
    st["gates"][g] = {"status": status, "note": args.note or "", "at": now()}
    p.save_state(st)
    p.log(f"Ворота {g} ({GATE_TITLES[g]}): {status}. {args.note or ''}", "gate")
    print(f"{g}: {status}")


BRIEF_FIELDS = ["question", "goal", "recipient", "decision", "deadline"]
BRIEF_LISTS = ["constraints", "data_available"]


def cmd_brief(args):
    p = get_project(args)
    st = p.state()
    b = st.setdefault("brief", {})
    changed = []
    for f in BRIEF_FIELDS:
        v = getattr(args, f)
        if v is not None:
            b[f] = v
            changed.append(f)
    for f in BRIEF_LISTS:
        v = getattr(args, f)
        if v:
            b.setdefault(f, []).extend(v)
            changed.append(f)
    if not changed:
        print(json.dumps(b, ensure_ascii=False, indent=2))
        return
    p.save_state(st)
    p.log(f"Бриф обновлён: {', '.join(changed)}", "brief")
    print("Бриф обновлён: " + ", ".join(changed))


def cmd_q(args):
    p = get_project(args)
    st = p.state()
    qs = st.setdefault("open_questions", [])
    if args.action == "add":
        qid = next_id("Q", qs)
        qs.append({"id": qid, "text": args.text, "why": args.why or "", "status": "open", "ts": now()})
        p.save_state(st)
        p.log(f"Открытый вопрос {qid}: {args.text}", "question")
        print(qid)
    elif args.action == "close":
        for q in qs:
            if q["id"] == args.text.upper():
                q["status"] = "closed"
                q["answer"] = args.answer or ""
                q["closed"] = now()
                p.save_state(st)
                p.log(f"Вопрос {q['id']} закрыт: {args.answer or ''}", "question")
                print(f"{q['id']} закрыт")
                return
        die(f"вопрос {args.text} не найден")
    else:
        for q in qs:
            print(f"{q['id']} [{q['status']}] {q['text']}" + (f" → {q.get('answer')}" if q.get("answer") else ""))


def cmd_domain(args):
    p = get_project(args)
    st = p.state()
    key = {"allow": "allowed_domains", "block": "blocked_domains"}.get(args.action)
    if key:
        for d in args.domains:
            d = d.lower().strip()
            if d not in st[key]:
                st[key].append(d)
        p.save_state(st)
        p.log(f"Домены ({args.action}): {', '.join(args.domains)}", "config")
    print(f"Разрешены: {', '.join(st['allowed_domains']) or '(все открытые)'}\n"
          f"Запрещены: {', '.join(st['blocked_domains']) or '—'}")


# ----------------------------------------------------------------- источники
def _add_source(p: Project, kind: str, ref: str, title: str, note: str = "", reliability: str = "medium",
                published: str = "", file_hash: str = "", md: str = "") -> tuple[str, bool]:
    rows = p.sources()
    for r in rows:  # идемпотентность: тот же файл или тот же URL не регистрируем дважды
        if (file_hash and r.get("sha256") == file_hash) or (not file_hash and r.get("ref") == ref):
            return r["id"], False
    sid = next_id("S", rows)
    row = {"id": sid, "kind": kind, "ref": ref, "title": title, "reliability": reliability,
           "published": published, "accessed": now(), "note": note}
    if file_hash:
        row["sha256"] = file_hash
    if md:
        row["markdown"] = md
    append_jsonl(p.sources_path, row)
    p.log(f"Источник {sid} ({kind}): {title} — {ref}", "source")
    return sid, True


def cmd_source(args):
    p = get_project(args)
    if args.action == "add":
        if not args.ref or not args.title:
            die("нужны --ref и --title")
        sid, new = _add_source(p, args.kind, args.ref, args.title, args.note or "", args.reliability,
                               args.published or "")
        print(sid if new else f"{sid} (уже зарегистрирован)")
    elif args.action == "list":
        for s in p.sources():
            print(f"{s['id']:<5} {s['kind']:<10} {s.get('reliability',''):<7} {s['title']}  ← {s['ref']}")
    elif args.action == "show":
        for s in p.sources():
            if s["id"] == (args.id or "").upper():
                print(json.dumps(s, ensure_ascii=False, indent=2))
                return
        die("источник не найден")


KIND_BY_EXT = {
    ".pdf": "document", ".docx": "document", ".doc": "document", ".pptx": "document", ".md": "document",
    ".txt": "document", ".html": "document", ".htm": "document", ".rtf": "document",
    ".xlsx": "table", ".xls": "table", ".csv": "table", ".tsv": "table", ".json": "data",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image", ".gif": "image",
    ".mp3": "audio", ".wav": "audio", ".m4a": "audio", ".ogg": "audio",
    ".mp4": "video", ".mov": "video", ".webm": "video",
}
TEXT_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".html", ".htm"}


def _to_markdown(src: Path, dst: Path) -> str:
    """Пытается получить текстовую версию файла. Возвращает описание результата."""
    ext = src.suffix.lower()
    if ext in TEXT_EXT:
        return "текстовый файл — читается напрямую"
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "изображение — модель читает его напрямую (Read)"
    if ext in {".mp3", ".wav", ".m4a", ".ogg", ".mp4", ".mov", ".webm"}:
        return "аудио/видео — нужна расшифровка (см. method/media.md)"
    exe = shutil.which("markitdown")
    if exe:
        try:
            r = subprocess.run([exe, str(src)], capture_output=True, timeout=300)
            if r.returncode == 0 and r.stdout.strip():
                dst.write_bytes(r.stdout)
                return f"конвертирован markitdown → {dst.relative_to(ROOT).as_posix()}"
            return f"markitdown не справился (код {r.returncode}); PDF модель может читать напрямую"
        except Exception as e:  # noqa: BLE001
            return f"markitdown упал: {e}"
    return "markitdown не установлен (pip install 'markitdown[all]'); PDF модель читает напрямую"


def cmd_ingest(args):
    p = get_project(args)
    for raw in args.paths:
        src = Path(raw).expanduser()
        if not src.exists():
            print(f"нет файла: {raw}", file=sys.stderr)
            continue
        src = src.resolve()
        try:
            src.relative_to(p.inputs.resolve())
            dst = src
        except ValueError:
            dst = p.inputs / src.name
            if dst.exists() and sha256(dst) != sha256(src):
                dst = p.inputs / f"{src.stem}-{sha256(src)[:8]}{src.suffix}"
            if not dst.exists():
                shutil.copy2(src, dst)
        h = sha256(dst)
        md_path = p.inputs / "_md" / (dst.stem + ".md")
        note = _to_markdown(dst, md_path)
        kind = args.kind or KIND_BY_EXT.get(dst.suffix.lower(), "document")
        rel = dst.relative_to(ROOT).as_posix()
        sid, new = _add_source(p, kind, rel, args.title or dst.name, note=note,
                               reliability=args.reliability, file_hash=h,
                               md=md_path.relative_to(ROOT).as_posix() if md_path.exists() else "")
        print(f"{sid}{'' if new else ' (уже был)'}  {rel}  — {note}")


# ----------------------------------------------------------------- утверждения
def cmd_claim(args):
    p = get_project(args)
    claims = p.claims()
    by_id = {c["id"]: c for c in claims}
    if args.action == "add":
        if not args.text:
            die("нужен текст утверждения")
        ctype = args.type or "hypothesis"
        srcs = split_ids(args.sources)
        deps = split_ids(args.depends)
        known_src = {s["id"]: s for s in p.sources()}
        for s in srcs:
            if s not in known_src:
                die(f"источник {s} не зарегистрирован (strat source add / strat ingest)")
        for d in deps:
            if d not in by_id:
                die(f"утверждение {d} не найдено")
        if ctype == "fact" and not srcs:
            die("факт без источника недопустим. Укажите --sources или выберите тип hypothesis/assumption")
        if ctype == "fact" and srcs and all(known_src[s]["kind"] == "synthetic" for s in srcs):
            die("ответы модельных респондентов не могут подтверждать факт. Используйте тип synthetic или hypothesis")
        if ctype == "synthetic" and srcs and any(known_src[s]["kind"] != "synthetic" for s in srcs):
            print("предупреждение: synthetic-утверждение ссылается на несинтетический источник", file=sys.stderr)
        cid = next_id("C", claims)
        row = {"id": cid, "text": args.text, "type": ctype, "sources": srcs, "depends_on": deps,
               "confidence": args.confidence, "status": "active", "created": now(),
               "stage": p.state().get("stage")}
        if args.note:
            row["note"] = args.note
        if args.supersedes:
            old = args.supersedes.upper()
            if old not in by_id:
                die(f"утверждение {old} не найдено")
            row["supersedes"] = old
            for c in claims:
                if c["id"] == old:
                    c["status"] = "revoked"
                    c["revoked_reason"] = f"заменено {cid}"
                    c["revoked_at"] = now()
            claims.append(row)
            write_jsonl(p.claims_path, claims)
            p.log(f"Утверждение {cid} заменяет {old}", "claim")
        else:
            append_jsonl(p.claims_path, row)
        p.log(f"Утверждение {cid} [{ctype}] {args.text[:120]}", "claim")
        print(cid)
    elif args.action == "list":
        for c in claims:
            if not args.all and c.get("status", "active") != "active":
                continue
            if args.type and c["type"] != args.type:
                continue
            flag = " ⚠пересмотр" if c.get("needs_review") else ""
            st = "" if c.get("status", "active") == "active" else f" ({c['status']})"
            src = ",".join(c.get("sources", [])) or "—"
            print(f"{c['id']:<5} {c['type']:<11} {c.get('confidence',''):<7} [{src}]{st}{flag}  {c['text']}")
    elif args.action == "show":
        c = by_id.get((args.text or "").upper())
        if not c:
            die("утверждение не найдено")
        print(json.dumps(c, ensure_ascii=False, indent=2))
    elif args.action in ("revoke", "confirm"):
        cid = (args.text or "").upper()
        if cid not in by_id:
            die("утверждение не найдено")
        for c in claims:
            if c["id"] == cid:
                if args.action == "revoke":
                    c["status"] = "revoked"
                    c["revoked_reason"] = args.reason or ""
                    c["revoked_at"] = now()
                else:
                    c.pop("needs_review", None)
                    c["reviewed_at"] = now()
        write_jsonl(p.claims_path, claims)
        p.log(f"Утверждение {cid}: {args.action}. {args.reason or ''}", "claim")
        print(f"{cid}: {args.action}")
        if args.action == "revoke":
            _print_impact(p, cid)


def _impacted_claims(claims: list[dict], start: str) -> list[str]:
    """Все активные утверждения, которые прямо или транзитивно опираются на start (S… или C…)."""
    hit: set[str] = set()
    frontier = {start}
    while frontier:
        nxt = set()
        for c in claims:
            if c.get("status", "active") != "active" or c["id"] in hit:
                continue
            if frontier & set(c.get("sources", [])) or frontier & set(c.get("depends_on", [])):
                hit.add(c["id"])
                nxt.add(c["id"])
        frontier = nxt
    hit.discard(start)
    return sorted(hit, key=lambda x: int(x[1:]))


def _refs_in_text(text: str) -> set[str]:
    ids = set()
    for m in REF_BLOCK_RE.finditer(text):
        ids.update(split_ids(m.group(1)))
    return ids


def _print_impact(p: Project, start: str, flag: bool = False) -> dict:
    claims = p.claims()
    ids = _impacted_claims(claims, start)
    targets = set(ids) | {start}
    files = []
    for f in sorted(p.outputs.glob("*.md")):
        refs = _refs_in_text(f.read_text(encoding="utf-8"))
        hits = sorted(refs & targets)
        if hits:
            files.append((f.name, hits))
    decisions = [d for d in p.decisions() if set(d.get("claims", [])) & targets and d.get("status") == "active"]
    print(f"Влияние {start}:")
    print(f"  утверждения: {', '.join(ids) if ids else '—'}")
    for name, hits in files:
        print(f"  документ {name}: ссылается на {', '.join(hits)}")
    for d in decisions:
        print(f"  решение {d['id']} «{d['title']}» опирается на {', '.join(sorted(set(d['claims']) & targets))}")
    if flag and ids:
        for c in claims:
            if c["id"] in ids:
                c["needs_review"] = f"затронуто {start} ({now()})"
        write_jsonl(p.claims_path, claims)
        p.log(f"Пересмотр: {start} затрагивает {', '.join(ids)}", "impact")
        print(f"  помечено для пересмотра: {len(ids)}. Снять пометку: strat claim confirm C… / заменить: claim add --supersedes")
    return {"claims": ids, "files": files, "decisions": [d["id"] for d in decisions]}


def cmd_impact(args):
    p = get_project(args)
    _print_impact(p, args.id.upper(), flag=args.flag)


# ----------------------------------------------------------------- поиск по знаниям
def _stem(w: str) -> str:
    """Грубая основа слова для русского: «роуминга», «роумингом» → «роумин»."""
    w = w.lower()
    return w[: max(4, len(w) - 2)] if len(w) > 5 else w


def _match(query_stems: list[str], text: str) -> int:
    words = re.findall(r"\w+", text.lower())
    return sum(1 for q in query_stems if any(w.startswith(q) for w in words))


def cmd_search(args):
    """Поиск по формулировке в реестрах (утверждения и источники) текущего или всех проектов.
    Отозванные утверждения по умолчанию скрыты; выводы агента помечены — память не превращает их в факты."""
    stems = [_stem(w) for w in re.findall(r"\w+", args.query) if len(w) > 2]
    if not stems:
        die("пустой запрос")
    if args.all_projects:
        slugs = [d.name for d in sorted(PROJECTS.iterdir()) if (d / "state.json").exists()] if PROJECTS.exists() else []
    else:
        slugs = [get_project(args).slug]
    need = len(stems) if args.strict else max(1, (len(stems) + 1) // 2)
    hits = []
    for slug in slugs:
        pdir = PROJECTS / slug
        sources = {s["id"]: s for s in read_jsonl(pdir / "sources.jsonl")}
        for c in read_jsonl(pdir / "claims.jsonl"):
            if c.get("status") == "revoked" and not args.include_revoked:
                continue
            score = _match(stems, c["text"] + " " + c.get("note", ""))
            if score >= need:
                hits.append((score, slug, c, "claim"))
        for s in sources.values():
            score = _match(stems, " ".join([s.get("title", ""), s.get("ref", ""), s.get("note", "")]))
            if score >= need:
                hits.append((score, slug, s, "source"))
    hits.sort(key=lambda h: -h[0])
    cur = active_slug()
    for score, slug, item, kind in hits[: args.limit]:
        where = "" if slug == cur and not args.all_projects else f"{slug}/"
        if kind == "claim":
            mark = ""
            if item.get("status") == "revoked":
                mark = f" [ОТОЗВАНО: {item.get('revoked_reason', '')}]"
            elif item.get("needs_review"):
                mark = " [требует пересмотра]"
            elif item["type"] in ("hypothesis", "forecast", "assumption"):
                mark = " [вывод/допущение — не факт]"
            elif item["type"] == "synthetic":
                mark = " [синтетика — не доказательство]"
            print(f"{where}{item['id']:<5} {item['type']:<10} [{','.join(item.get('sources', [])) or '—'}]{mark}  {item['text']}")
        else:
            print(f"{where}{item['id']:<5} источник  {item.get('reliability', ''):<6} {item['title']} ← {item['ref']}")
    if not hits:
        print("Ничего не найдено.")
    elif args.all_projects:
        print("\nСведения из других проектов — это подсказки, а не факты для текущего: перепроверь дату и заново "
              "зарегистрируй источник в текущем проекте.")


# ----------------------------------------------------------------- проверка документов
def cmd_validate(args):
    p = get_project(args)
    claims = {c["id"]: c for c in p.claims()}
    sources = {s["id"]: s for s in p.sources()}
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    files = ([Path(f) if Path(f).exists() else p.outputs / Path(f).name for f in args.files]
             if args.files else sorted(p.outputs.glob("*.md")))
    for f in files:
        if not f.exists():
            die(f"нет файла {f}")
    for f in files:
        if f.name == "00-transparency.md":
            continue
        text = f.read_text(encoding="utf-8")
        if TEMPLATE_MARKER in text:
            doc_stage = DOC_STAGE.get(f.name)
            if doc_stage and stage_index(p.state()["stage"]) > stage_index(doc_stage):
                warnings.append(f"{f.name}: стадия «{STAGE_TITLES[doc_stage]}» пройдена, а документ не заполнен")
            else:
                info.append(f"{f.name}: ещё не заполнен (шаблон)")
            continue
        for h in REQUIRED_HEADINGS.get(f.name, []):
            if not re.search(rf"^#+\s.*{re.escape(h)}", text, re.M | re.I):
                errors.append(f"{f.name}: нет обязательного раздела «{h}»")
        if f.name == "04-options.md":
            n = len(re.findall(r"^#{2,3}\s*Вариант", text, re.M | re.I))
            if n < 3:
                errors.append(f"{f.name}: вариантов {n}, нужно не меньше 3")
        in_code = False
        for i, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith("```"):
                in_code = not in_code
            if in_code or line.lstrip().startswith(("#", "<!--", "|---", "| ---")):
                continue
            refs = _refs_in_text(line)
            for r in refs:
                if r.startswith("C"):
                    c = claims.get(r)
                    if not c:
                        errors.append(f"{f.name}:{i}: ссылка на несуществующее утверждение {r}")
                        continue
                    if c.get("status") == "revoked":
                        errors.append(f"{f.name}:{i}: {r} отозвано ({c.get('revoked_reason','')}) — обновите текст")
                    if c.get("needs_review"):
                        warnings.append(f"{f.name}:{i}: {r} требует пересмотра ({c['needs_review']})")
                    if c["type"] == "synthetic" and f.name in STRATEGY_FILES:
                        if re.search(r"доказ|подтвержд|спрос|распростран|больш(ая|инство)", line, re.I):
                            errors.append(f"{f.name}:{i}: синтетический ответ {r} использован как доказательство")
                        else:
                            warnings.append(f"{f.name}:{i}: {r} — синтетика; допустимо только как гипотеза")
                elif r.startswith("S") and r not in sources:
                    errors.append(f"{f.name}:{i}: ссылка на несуществующий источник {r}")
            if not refs and NUMERIC_RE.search(line):
                warnings.append(f"{f.name}:{i}: число без ссылки на утверждение: «{line.strip()[:90]}»")
            if "TODO" in line or "{{" in line:
                warnings.append(f"{f.name}:{i}: незаполненное место")
    # целостность реестра
    for c in claims.values():
        if c.get("status") == "active" and c["type"] == "fact" and not c.get("sources"):
            errors.append(f"реестр: факт {c['id']} без источника")
        for s in c.get("sources", []):
            if s not in sources:
                errors.append(f"реестр: {c['id']} ссылается на неизвестный источник {s}")
    for label, items in (("ОШИБКИ", errors), ("ПРЕДУПРЕЖДЕНИЯ", warnings), ("СВЕДЕНИЯ", info)):
        if items:
            print(f"{label} ({len(items)}):")
            for it in items:
                print("  " + it)
    print(f"Итог: ошибок {len(errors)}, предупреждений {len(warnings)}.")
    p.log(f"Проверка документов: ошибок {len(errors)}, предупреждений {len(warnings)}", "validate")
    sys.exit(1 if errors else 0)


# ----------------------------------------------------------------- решения
def cmd_decision(args):
    p = get_project(args)
    rows = p.decisions()
    if args.action == "add":
        if not args.title:
            die("нужен --title")
        cl = split_ids(args.claims)
        known = {c["id"] for c in p.claims()}
        for c in cl:
            if c not in known:
                die(f"утверждение {c} не найдено")
        did = next_id("D", rows)
        row = {"id": did, "title": args.title, "choice": args.choice or "", "owner": args.owner or "",
               "metric": args.metric or "", "review_on": args.review_on or "", "review_if": args.review_if or "",
               "claims": cl, "status": "active", "created": now()}
        append_jsonl(p.decisions_path, row)
        p.log(f"Решение {did}: {args.title} (ответственный: {args.owner or '—'})", "decision")
        print(did)
    elif args.action == "list":
        for d in rows:
            print(f"{d['id']:<4} [{d['status']}] {d['title']} · отв.: {d.get('owner') or '—'} · "
                  f"метрика: {d.get('metric') or '—'} · пересмотр: {d.get('review_on') or d.get('review_if') or '—'}")
    elif args.action == "check":
        claims = {c["id"]: c for c in p.claims()}
        today = dt.date.today().isoformat()
        found = False
        for d in rows:
            if d.get("status") != "active":
                continue
            reasons = []
            for cid in d.get("claims", []):
                c = claims.get(cid)
                if not c:
                    continue
                if c.get("status") == "revoked":
                    reasons.append(f"основание {cid} отозвано")
                elif c.get("needs_review"):
                    reasons.append(f"основание {cid} требует пересмотра")
            if d.get("review_on") and d["review_on"] <= today:
                reasons.append(f"наступил срок пересмотра {d['review_on']}")
            if reasons:
                found = True
                print(f"{d['id']} «{d['title']}»: " + "; ".join(reasons))
            elif d.get("review_if"):
                print(f"{d['id']} «{d['title']}»: проверьте условие пересмотра — {d['review_if']}")
        if not found:
            print("Решений с устаревшими основаниями нет.")
    elif args.action in ("close", "revise"):
        did = (args.id or "").upper()
        for d in rows:
            if d["id"] == did:
                d["status"] = "closed" if args.action == "close" else "revised"
                d["closed_note"] = args.note or ""
                d["closed_at"] = now()
                write_jsonl(p.decisions_path, rows)
                p.log(f"Решение {did}: {d['status']}. {args.note or ''}", "decision")
                print(f"{did}: {d['status']}")
                return
        die("решение не найдено")


# ----------------------------------------------------------------- журнал и шаги
def cmd_log(args):
    p = get_project(args)
    p.log(args.text, args.kind)
    print("записано")


def _pending_steps(p: Project) -> list[dict]:
    state: dict[str, dict] = {}
    for r in read_jsonl(p.steps_path):
        state[r["key"]] = r
    return [r for r in state.values() if r["status"] == "started"]


def cmd_step(args):
    """Идемпотентные шаги: перед действием с побочным эффектом — start, после — done.
    Если шаг уже done, start вернёт код 3, и агент не должен повторять действие."""
    p = get_project(args)
    rows = read_jsonl(p.steps_path)
    last = {}
    for r in rows:
        last[r["key"]] = r
    if args.action == "pending":
        for s in _pending_steps(p):
            print(f"{s['key']}: {s.get('desc','')} (начат {s['ts']})")
        return
    if args.action == "check":
        r = last.get(args.key)
        print(r["status"] if r else "absent")
        sys.exit(0 if r and r["status"] == "done" else 3)
    key = args.key
    if args.action == "start" and last.get(key, {}).get("status") == "done" and not args.force:
        print(f"шаг {key} уже выполнен ({last[key]['ts']}): {last[key].get('result','')}. Повтор не нужен.")
        sys.exit(3)
    status = {"start": "started", "done": "done", "fail": "failed"}[args.action]
    row = {"key": key, "status": status, "ts": now(), "stage": p.state().get("stage")}
    if args.desc:
        row["desc"] = args.desc
    if args.result:
        row["result"] = args.result
    append_jsonl(p.steps_path, row)
    if status != "started":
        p.log(f"Шаг {key}: {status}. {args.result or ''}", "step" if status == "done" else "error")
    print(f"{key}: {status}")


# ----------------------------------------------------------------- расходы
def _cost_summary(p: Project) -> dict:
    tot = {"usd": 0.0, "input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    by_stage: dict[str, float] = {}
    by_model: dict[str, float] = {}
    by_source: dict[str, float] = {}
    for r in read_jsonl(p.costs_path):
        usd = float(r.get("usd", 0))
        tot["usd"] += usd
        for k in ("input", "output", "cache_read", "cache_write"):
            tot[k] += int(r.get(k, 0))
        by_stage[r.get("stage", "?")] = by_stage.get(r.get("stage", "?"), 0) + usd
        by_model[r.get("model", "?")] = by_model.get(r.get("model", "?"), 0) + usd
        by_source[r.get("source", "?")] = by_source.get(r.get("source", "?"), 0) + usd
    tot.update(by_stage=by_stage, by_model=by_model, by_source=by_source)
    return tot


def cmd_cost(args):
    p = get_project(args)
    if args.action == "add":
        row = {"ts": now(), "stage": p.state().get("stage"), "source": args.source, "model": args.model or "?",
               "input": args.input or 0, "output": args.output or 0, "usd": args.usd, "note": args.note or ""}
        append_jsonl(p.costs_path, row)
        p.log(f"Расход ${args.usd:.2f} ({args.source}): {args.note or ''}", "cost")
        print("записано")
        return
    s = _cost_summary(p)
    if args.json:
        print(json.dumps(s, ensure_ascii=False, indent=2))
        return
    print(f"Всего: ${s['usd']:.2f}   токены: вход {s['input']:,} · выход {s['output']:,} · "
          f"кэш-чтение {s['cache_read']:,} · кэш-запись {s['cache_write']:,}".replace(",", " "))
    for title, d in (("По стадиям", s["by_stage"]), ("По моделям", s["by_model"]), ("По источнику учёта", s["by_source"])):
        if d:
            print(title + ":")
            for k, v in sorted(d.items(), key=lambda x: -x[1]):
                print(f"  {k:<28} ${v:.3f}")


# ----------------------------------------------------------------- отчёт о прозрачности
def _stage_durations(p: Project) -> list[tuple[str, str, str]]:
    marks = []
    for line in p.journal_path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"- (\S+) · \[stage\] · \S+ · Стадия: (\S+) → (\S+)", line)
        if m:
            marks.append((m.group(1), m.group(3)))
    out = []
    st = p.state()
    start = st.get("created")
    cur = "brief"
    for ts, new in marks:
        out.append((cur, start, ts))
        cur, start = new, ts
    out.append((cur, start, now()))
    return out


def _fmt_dur(a: str, b: str) -> str:
    try:
        d = dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)
    except Exception:  # noqa: BLE001
        return "?"
    m = int(d.total_seconds() // 60)
    return f"{m // 60} ч {m % 60} мин" if m >= 60 else f"{m} мин"


def cmd_report(args):
    p = get_project(args)
    st = p.state()
    claims = p.claims()
    sources = p.sources()
    cost = _cost_summary(p)
    by_type: dict[str, int] = {}
    for c in claims:
        if c.get("status", "active") == "active":
            by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    L = [f"# Прозрачность: {st.get('title')}", "",
         f"_Сформировано {now()} командой `strat report`. Не редактируйте вручную._", "",
         "## Где мы", "",
         f"- Стадия: **{STAGE_TITLES[st['stage']]}**",
         "- Ворота: " + "; ".join(f"{g} {GATE_TITLES[g]} — {v['status']}" + (f" ({v['note']})" if v.get('note') else "")
                                  for g, v in st["gates"].items()),
         f"- Следующий шаг: {st.get('next_step') or '—'}", "",
         "## Основания", "",
         f"- Источников: {len(sources)}; утверждений: " + ", ".join(f"{CLAIM_TYPES[k].split(' (')[0]} — {v}"
                                                               for k, v in sorted(by_type.items())),
         f"- Отозвано утверждений: {sum(1 for c in claims if c.get('status') == 'revoked')}; "
         f"требуют пересмотра: {sum(1 for c in claims if c.get('needs_review') and c.get('status', 'active') == 'active')}", "",
         "| ID | Тип | Источник | Надёжность |", "|---|---|---|---|"]
    for s in sources:
        L.append(f"| {s['id']} | {s['kind']} | {s['title']} — {s['ref']} | {s.get('reliability','')} |")
    L += ["", "## Время по стадиям", "", "| Стадия | Длительность |", "|---|---|"]
    for stage, a, b in _stage_durations(p):
        L.append(f"| {STAGE_TITLES.get(stage, stage)} | {_fmt_dur(a, b)} |")
    L += ["", "## Стоимость", "", f"Всего: **${cost['usd']:.2f}** (вход {cost['input']:,} ток., выход {cost['output']:,} ток.)".replace(",", " "), ""]
    if cost["by_stage"]:
        L += ["| Стадия | $ |", "|---|---|"] + [f"| {STAGE_TITLES.get(k, k)} | {v:.3f} |" for k, v in cost["by_stage"].items()] + [""]
    if cost["by_model"]:
        L += ["| Модель | $ |", "|---|---|"] + [f"| {k} | {v:.3f} |" for k, v in cost["by_model"].items()] + [""]
    L += ["## Журнал действий", "", "```"]
    L += [l[2:] for l in p.journal_path.read_text(encoding="utf-8").splitlines() if l.startswith("- ")][-args.last:]
    L += ["```", ""]
    out = p.outputs / "00-transparency.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"Отчёт: {out.relative_to(ROOT).as_posix()}")


# ----------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="strat", description="Ядро агента «Стратег»: состояние, источники, утверждения, решения, расходы.")
    ap.add_argument("-p", "--project", help="slug проекта (по умолчанию — активный)")
    sp = ap.add_subparsers(dest="cmd", required=True)

    a = sp.add_parser("init", help="создать проект"); a.add_argument("slug"); a.add_argument("--title"); a.add_argument("--question"); a.set_defaults(fn=cmd_init)
    a = sp.add_parser("use", help="сделать проект активным"); a.add_argument("slug"); a.set_defaults(fn=cmd_use)
    a = sp.add_parser("list", help="список проектов"); a.set_defaults(fn=cmd_list)
    a = sp.add_parser("status", help="где мы и что дальше"); a.add_argument("--json", action="store_true"); a.add_argument("--journal", type=int, default=0, metavar="N"); a.set_defaults(fn=cmd_status)
    a = sp.add_parser("stage", help="перейти на стадию"); a.add_argument("name", choices=STAGES); a.add_argument("--next"); a.add_argument("--force", action="store_true"); a.set_defaults(fn=cmd_stage)
    a = sp.add_parser("next", help="записать следующий шаг"); a.add_argument("text"); a.set_defaults(fn=cmd_next)
    a = sp.add_parser("gate", help="решение человека на воротах"); a.add_argument("gate"); a.add_argument("action", choices=["approve", "reject", "reset"]); a.add_argument("--note"); a.set_defaults(fn=cmd_gate)

    a = sp.add_parser("brief", help="поля брифа")
    for f in BRIEF_FIELDS:
        a.add_argument(f"--{f}")
    a.add_argument("--constraint", dest="constraints", action="append")
    a.add_argument("--data", dest="data_available", action="append")
    a.set_defaults(fn=cmd_brief)

    a = sp.add_parser("q", help="открытые вопросы"); a.add_argument("action", choices=["add", "close", "list"]); a.add_argument("text", nargs="?", default=""); a.add_argument("--why"); a.add_argument("--answer"); a.set_defaults(fn=cmd_q)
    a = sp.add_parser("domain", help="разрешённые/запрещённые домены"); a.add_argument("action", choices=["allow", "block", "list"]); a.add_argument("domains", nargs="*"); a.set_defaults(fn=cmd_domain)

    a = sp.add_parser("source", help="реестр источников"); a.add_argument("action", choices=["add", "list", "show"]); a.add_argument("id", nargs="?")
    a.add_argument("--kind", choices=SOURCE_KINDS, default="web"); a.add_argument("--ref"); a.add_argument("--title"); a.add_argument("--note")
    a.add_argument("--reliability", choices=RELIABILITY, default="medium"); a.add_argument("--published"); a.set_defaults(fn=cmd_source)
    a = sp.add_parser("ingest", help="добавить файлы в inputs/ и реестр"); a.add_argument("paths", nargs="+"); a.add_argument("--kind", choices=SOURCE_KINDS); a.add_argument("--title")
    a.add_argument("--reliability", choices=RELIABILITY, default="medium"); a.set_defaults(fn=cmd_ingest)

    a = sp.add_parser("claim", help="реестр утверждений"); a.add_argument("action", choices=["add", "list", "show", "revoke", "confirm"]); a.add_argument("text", nargs="?")
    a.add_argument("--type", choices=list(CLAIM_TYPES), help="при add по умолчанию hypothesis; при list — фильтр"); a.add_argument("--sources"); a.add_argument("--depends")
    a.add_argument("--confidence", choices=RELIABILITY, default="medium"); a.add_argument("--note"); a.add_argument("--supersedes"); a.add_argument("--reason")
    a.add_argument("--all", action="store_true"); a.set_defaults(fn=cmd_claim)
    a = sp.add_parser("impact", help="что затронет источник/утверждение"); a.add_argument("id"); a.add_argument("--flag", action="store_true", help="пометить затронутые утверждения для пересмотра"); a.set_defaults(fn=cmd_impact)
    a = sp.add_parser("validate", help="проверить документы outputs/"); a.add_argument("files", nargs="*"); a.set_defaults(fn=cmd_validate)
    a = sp.add_parser("search", help="поиск по утверждениям и источникам")
    a.add_argument("query"); a.add_argument("--all-projects", action="store_true", help="искать во всех проектах")
    a.add_argument("--include-revoked", action="store_true"); a.add_argument("--strict", action="store_true", help="все слова запроса")
    a.add_argument("--limit", type=int, default=20); a.set_defaults(fn=cmd_search)

    a = sp.add_parser("decision", help="решения и условия пересмотра"); a.add_argument("action", choices=["add", "list", "check", "close", "revise"]); a.add_argument("id", nargs="?")
    for f in ["title", "choice", "owner", "metric", "review-on", "review-if", "claims", "note"]:
        a.add_argument(f"--{f}")
    a.set_defaults(fn=cmd_decision)

    a = sp.add_parser("log", help="запись в журнал"); a.add_argument("text"); a.add_argument("--kind", default="action"); a.set_defaults(fn=cmd_log)
    a = sp.add_parser("step", help="идемпотентные шаги"); a.add_argument("action", choices=["start", "done", "fail", "check", "pending"]); a.add_argument("key", nargs="?")
    a.add_argument("--desc"); a.add_argument("--result"); a.add_argument("--force", action="store_true"); a.set_defaults(fn=cmd_step)
    a = sp.add_parser("cost", help="расходы"); a.add_argument("action", nargs="?", choices=["show", "add"], default="show"); a.add_argument("--usd", type=float, default=0.0)
    a.add_argument("--model"); a.add_argument("--input", type=int); a.add_argument("--output", type=int); a.add_argument("--note"); a.add_argument("--source", default="manual"); a.add_argument("--json", action="store_true"); a.set_defaults(fn=cmd_cost)
    a = sp.add_parser("report", help="сформировать outputs/00-transparency.md"); a.add_argument("--last", type=int, default=60); a.set_defaults(fn=cmd_report)
    return ap





class ProjectLock:
    """Межпроцессная блокировка: субагенты могут писать в реестры параллельно,
    а ID (S#, C#, D#) выдаются по чтению текущего файла — без блокировки возможны дубли."""

    def __init__(self, path: Path, timeout: float = 30.0):
        self.path, self.timeout, self.fd = path, timeout, None

    def __enter__(self):
        import time
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:  # «зависшая» блокировка от упавшего процесса
                    if time.time() - self.path.stat().st_mtime > 120:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    die(f"проект занят другим процессом ({self.path}); если это ошибка — удалите файл")
                time.sleep(0.05)

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def main(argv=None):
    args = build_parser().parse_args(argv)
    if getattr(args, "cmd", None) == "step" and args.action != "pending" and not args.key:
        die("нужен ключ шага")
    slug = None if args.cmd in ("init", "use", "list") else active_slug(getattr(args, "project", None))
    read_only = args.cmd in ("status", "list", "validate", "search") or getattr(args, "action", None) in ("list", "show", "check", "pending")
    if slug and not read_only and (PROJECTS / slug).is_dir():
        with ProjectLock(PROJECTS / slug / ".lock"):
            args.fn(args)
    else:
        args.fn(args)


if __name__ == "__main__":
    main()
