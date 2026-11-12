"""Тесты ядра strat. Запуск: python -m unittest discover -s tests -v"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STRAT = REPO / "tools" / "strat.py"


class StratTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(REPO / "templates", self.tmp / "templates")
        (self.tmp / "projects").mkdir()
        self.env = {**os.environ, "STRAT_ROOT": str(self.tmp), "PYTHONIOENCODING": "utf-8"}
        self.env.pop("STRAT_PROJECT", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_s(self, *args, ok=True):
        r = subprocess.run([sys.executable, str(STRAT), *args], capture_output=True, text=True,
                           encoding="utf-8", env=self.env)
        if ok and r.returncode != 0:
            self.fail(f"strat {' '.join(args)} → {r.returncode}\n{r.stdout}\n{r.stderr}")
        return r

    @property
    def proj(self):
        return self.tmp / "projects" / "demo"

    def init(self):
        self.run_s("init", "demo", "--title", "Демо", "--question", "Почему падает удержание?")

    # --------------------------------------------------------------
    def test_status_without_active_project_is_a_hint_not_error(self):
        r = self.run_s("status")
        self.assertIn("Активного проекта нет", r.stdout)
        self.assertEqual(json.loads(self.run_s("status", "--json").stdout), {"active": None})

    def test_init_creates_structure_and_templates(self):
        self.init()
        for f in ["state.json", "sources.jsonl", "claims.jsonl", "journal.md", "outputs/04-options.md"]:
            self.assertTrue((self.proj / f).exists(), f)
        st = json.loads((self.proj / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(st["stage"], "brief")
        self.assertEqual(st["brief"]["question"], "Почему падает удержание?")

    def test_gates_block_stage_until_human_approves(self):
        self.init()
        r = self.run_s("stage", "research_plan", ok=False)
        self.assertEqual(r.returncode, 2)
        self.run_s("gate", "G1", "approve", "--note", "ок")
        self.run_s("stage", "research_plan")
        r = self.run_s("stage", "strategy", ok=False)
        self.assertEqual(r.returncode, 2)

    def test_fact_requires_source_and_synthetic_cannot_be_fact(self):
        self.init()
        r = self.run_s("claim", "add", "Рынок растёт", "--type", "fact", ok=False)
        self.assertNotEqual(r.returncode, 0)
        sid = self.run_s("source", "add", "--kind", "synthetic", "--ref", "interviews/p1.md", "--title", "Персона 1").stdout.strip()
        r = self.run_s("claim", "add", "Людям нужно X", "--type", "fact", "--sources", sid, ok=False)
        self.assertNotEqual(r.returncode, 0)
        self.run_s("claim", "add", "Людям, возможно, нужно X", "--type", "synthetic", "--sources", sid)

    def test_source_add_is_idempotent(self):
        self.init()
        a = self.run_s("source", "add", "--ref", "https://example.org/a", "--title", "A").stdout.strip()
        b = self.run_s("source", "add", "--ref", "https://example.org/a", "--title", "A").stdout.strip()
        self.assertEqual(a, "S1")
        self.assertTrue(b.startswith("S1"))

    def test_ingest_copies_and_registers_once(self):
        self.init()
        f = self.tmp / "data.csv"
        f.write_text("month,users\n2026-01,100\n", encoding="utf-8")
        out1 = self.run_s("ingest", str(f)).stdout
        out2 = self.run_s("ingest", str(f)).stdout
        self.assertIn("S1", out1)
        self.assertIn("уже был", out2)
        self.assertTrue((self.proj / "inputs" / "data.csv").exists())

    def test_impact_is_transitive_and_flags(self):
        self.init()
        self.run_s("source", "add", "--ref", "https://example.org/a", "--title", "A")
        self.run_s("claim", "add", "Факт 1", "--type", "fact", "--sources", "S1")      # C1
        self.run_s("claim", "add", "Вывод из C1", "--depends", "C1")                  # C2
        self.run_s("claim", "add", "Вывод из C2", "--type", "forecast", "--depends", "C2")  # C3
        self.run_s("claim", "add", "Независимое")                                     # C4
        out = self.run_s("impact", "S1", "--flag").stdout
        self.assertIn("C1, C2, C3", out)
        self.assertNotIn("C4", out.split("утверждения:")[1].splitlines()[0])
        claims = [json.loads(l) for l in (self.proj / "claims.jsonl").read_text(encoding="utf-8").splitlines() if l]
        self.assertTrue(all(c.get("needs_review") for c in claims if c["id"] in {"C1", "C2", "C3"}))

    def test_supersede_revokes_old(self):
        self.init()
        self.run_s("claim", "add", "Старое")                                   # C1
        self.run_s("claim", "add", "Вывод из старого", "--depends", "C1")      # C2
        self.run_s("claim", "add", "Новое", "--supersedes", "C1")              # C3
        claims = {json.loads(l)["id"]: json.loads(l) for l in (self.proj / "claims.jsonl").read_text(encoding="utf-8").splitlines() if l}
        self.assertEqual(claims["C1"]["status"], "revoked")
        self.assertEqual(claims["C3"]["supersedes"], "C1")
        self.assertIn("заменено C3", claims["C2"]["needs_review"])  # зависимый вывод помечен сразу

    def test_validate_catches_problems(self):
        self.init()
        self.run_s("source", "add", "--ref", "https://example.org/a", "--title", "A")
        self.run_s("claim", "add", "Отток 7% в месяц", "--type", "fact", "--sources", "S1")  # C1
        self.run_s("claim", "add", "Отозванное")                                          # C2
        self.run_s("claim", "revoke", "C2", "--reason", "устарело")
        (self.proj / "outputs" / "03-situation.md").write_text(
            "# Картина\n## Что известно\nОтток 7% в месяц [C1].\nЕщё [C2] и [C9].\nВыручка 12 млн руб.\n"
            "## Чего мы не знаем\n—\n", encoding="utf-8")
        r = self.run_s("validate", ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("C2 отозвано", r.stdout)
        self.assertIn("несуществующее утверждение C9", r.stdout)
        self.assertIn("число без ссылки", r.stdout)

    def test_fact_confidence_follows_source_reliability(self):
        self.init()
        self.run_s("source", "add", "--ref", "https://blog.example/x", "--title", "Блог", "--reliability", "low")
        self.run_s("claim", "add", "Кешбэк до 15%", "--type", "fact", "--sources", "S1")          # C1 → low
        self.run_s("claim", "add", "Кешбэк до 30%", "--type", "fact", "--sources", "S1",
                   "--confidence", "high")                                                       # C2 — завышено
        claims = [json.loads(l) for l in (self.proj / "claims.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(claims[0]["confidence"], "low")
        out = self.run_s("validate").stdout
        self.assertIn("факт C2 держится только на источниках низкой надёжности", out)
        self.assertNotIn("факт C1 держится", out)

    def test_confirm_can_lower_confidence_without_changing_id(self):
        self.init()
        self.run_s("source", "add", "--ref", "https://blog.example/x", "--title", "Блог", "--reliability", "low")
        self.run_s("claim", "add", "Кешбэк до 30%", "--type", "fact", "--sources", "S1", "--confidence", "high")
        self.run_s("claim", "confirm", "C1", "--confidence", "low", "--reason", "только блог")
        c = json.loads((self.proj / "claims.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual((c["id"], c["confidence"], c["status"]), ("C1", "low", "active"))
        self.assertEqual(c["confidence_history"][0]["old"], "high")
        self.assertNotIn("держится", self.run_s("validate").stdout)

    def test_impact_flag_does_not_reflag_already_reviewed(self):
        self.init()
        self.run_s("source", "add", "--ref", "https://example.org/a", "--title", "A")
        self.run_s("claim", "add", "Факт", "--type", "fact", "--sources", "S1")     # C1
        self.run_s("claim", "add", "Вывод", "--depends", "C1")                      # C2
        self.run_s("impact", "S1", "--flag")
        self.run_s("claim", "confirm", "C2")                                         # проверено
        out = self.run_s("impact", "S1", "--flag").stdout
        self.assertIn("уже проверены после изменения S1: C2", out)
        claims = {json.loads(l)["id"]: json.loads(l) for l in (self.proj / "claims.jsonl").read_text(encoding="utf-8").splitlines()}
        self.assertNotIn("needs_review", claims["C2"])
        self.run_s("impact", "S1", "--flag", "--again")
        claims = {json.loads(l)["id"]: json.loads(l) for l in (self.proj / "claims.jsonl").read_text(encoding="utf-8").splitlines()}
        self.assertIn("needs_review", claims["C2"])

    def test_validate_reports_docs_changed_after_gate(self):
        self.init()
        brief = self.proj / "outputs" / "01-brief.md"
        brief.write_text("# Бриф\nВопрос: что делать.\n", encoding="utf-8")
        self.run_s("gate", "G1", "approve", "--note", "ок")
        self.assertNotIn("изменён после одобрения", self.run_s("validate", ok=False).stdout)
        brief.write_text("# Бриф\nВопрос: что делать иначе.\n", encoding="utf-8")
        self.assertIn("01-brief.md: изменён после одобрения G1", self.run_s("validate", ok=False).stdout)
        self.run_s("gate", "G1", "approve", "--note", "правку видел")
        self.assertNotIn("изменён после одобрения", self.run_s("validate", ok=False).stdout)

    def test_validate_flags_unreferenced_duration_but_not_plan_steps(self):
        self.init()
        (self.proj / "outputs" / "04-options.md").write_text(
            "# Варианты\n## Вариант A. Оставить как есть\nСегмент вырастет через 3–5 лет.\n"
            "Этап 0 (2–4 недели).\nВ 2023 году было иначе.\n## Вариант B\n## Вариант C\n## Сравнение\n",
            encoding="utf-8")
        out = self.run_s("validate", ok=False).stdout
        self.assertIn("через 3–5 лет", out)
        self.assertNotIn("Этап 0", out)
        self.assertNotIn("2023 году", out)

    def test_decisions_with_stale_basis_show_in_status_and_can_be_rebased(self):
        self.init()
        self.run_s("claim", "add", "Основание")                                        # C1
        self.run_s("decision", "add", "--title", "Делать X", "--claims", "C1", "--review-if", "если Y")
        check = self.run_s("decision", "check").stdout
        self.assertIn("Решений с устаревшими основаниями нет", check)
        self.assertNotIn("если Y", check)                     # условия — только по --conditions
        self.assertIn("если Y", self.run_s("decision", "check", "--conditions").stdout)
        self.run_s("claim", "add", "Основание, уточнённое", "--supersedes", "C1")     # C2
        status = self.run_s("status").stdout
        self.assertIn("Решения к пересмотру", status)        # видно сразу после перерыва (хук SessionStart)
        self.assertIn("D1", json.loads(self.run_s("status", "--json").stdout)["decisions_to_review"])
        self.assertEqual(self.run_s("decision", "rebase", "D1", "--claims", "C1", ok=False).returncode, 1)  # отозвано
        self.run_s("decision", "rebase", "D1", "--claims", "C2", "--note", "по сути устояло")
        self.assertIn("Решений с устаревшими основаниями нет", self.run_s("decision", "check").stdout)
        d = json.loads((self.proj / "decisions.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(d["basis_history"][0]["old"], ["C1"])

    def test_validate_options_needs_three(self):
        self.init()
        (self.proj / "outputs" / "04-options.md").write_text(
            "# Варианты\n## Вариант A. Оставить как есть\n### Возражения\n## Вариант B\n## Сравнение\n", encoding="utf-8")
        r = self.run_s("validate", ok=False)
        self.assertIn("вариантов 2", r.stdout)

    def test_validate_synthetic_as_evidence_is_error(self):
        self.init()
        self.run_s("source", "add", "--kind", "synthetic", "--ref", "interviews/p1.md", "--title", "Персона")
        self.run_s("claim", "add", "Персона хочет X", "--type", "synthetic", "--sources", "S1")
        body = (REPO / "templates" / "05-strategy-product.md").read_text(encoding="utf-8")
        body = body.replace("<!-- template: не заполнено -->\n", "") + "\nСпрос подтверждён интервью [C1].\n"
        (self.proj / "outputs" / "05-strategy-product.md").write_text(body, encoding="utf-8")
        r = self.run_s("validate", ok=False)
        self.assertIn("использован как доказательство", r.stdout)

    def test_steps_are_idempotent(self):
        self.init()
        self.run_s("step", "start", "fetch-1", "--desc", "скачать отчёт")
        self.assertIn("fetch-1", self.run_s("status").stdout)
        self.run_s("step", "done", "fetch-1", "--result", "S1")
        r = self.run_s("step", "start", "fetch-1", ok=False)
        self.assertEqual(r.returncode, 3)

    def test_decisions_flag_stale_basis(self):
        self.init()
        self.run_s("claim", "add", "Основание")
        self.run_s("decision", "add", "--title", "Запускаем пилот", "--owner", "PM", "--claims", "C1",
                   "--review-if", "конверсия < 2%")
        self.run_s("claim", "revoke", "C1", "--reason", "новые данные")
        out = self.run_s("decision", "check").stdout
        self.assertIn("основание C1 отозвано", out)

    def test_costs_and_report(self):
        self.init()
        self.run_s("cost", "add", "--usd", "0.42", "--model", "claude-opus-5-5", "--input", "1000", "--output", "200")
        self.assertIn("$0.42", self.run_s("cost").stdout)
        self.run_s("report")
        rep = (self.proj / "outputs" / "00-transparency.md").read_text(encoding="utf-8")
        self.assertIn("Стоимость", rep)
        self.assertIn("Журнал действий", rep)

    def test_parallel_claims_get_unique_ids(self):
        self.init()
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(8) as ex:
            list(ex.map(lambda i: self.run_s("claim", "add", f"Утверждение {i}"), range(16)))
        ids = [json.loads(l)["id"] for l in (self.proj / "claims.jsonl").read_text(encoding="utf-8").splitlines() if l]
        self.assertEqual(len(ids), 16)
        self.assertEqual(len(set(ids)), 16)


if __name__ == "__main__":
    unittest.main()
