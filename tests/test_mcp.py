"""Тесты MCP-сервера strat: протокол JSON-RPC по stdio и инструменты. Запуск: python -m unittest discover -s tests -v"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class McpTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(REPO / "templates", self.tmp / "templates")
        (self.tmp / "projects").mkdir()
        env = {**os.environ, "STRAT_ROOT": str(self.tmp), "PYTHONIOENCODING": "utf-8"}
        env.pop("STRAT_PROJECT", None)
        self.proc = subprocess.Popen([sys.executable, str(REPO / "tools" / "strat_mcp.py")], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", env=env)
        self.next_id = 0

    def tearDown(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)
        self.proc.stdout.close()
        self.proc.stderr.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def send(self, method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            self.next_id += 1
            msg["id"] = self.next_id
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        if notify:
            return None
        resp = json.loads(self.proc.stdout.readline())
        self.assertEqual(resp["id"], self.next_id)
        return resp

    def call(self, tool_name, **args):
        r = self.send("tools/call", {"name": tool_name, "arguments": args})["result"]
        return r["content"][0]["text"], r["isError"]

    def handshake(self):
        r = self.send("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}})
        self.send("notifications/initialized", notify=True)
        return r

    def test_initialize_and_list(self):
        r = self.handshake()["result"]
        self.assertEqual(r["protocolVersion"], "2025-06-18")
        self.assertIn("tools", r["capabilities"])
        tools = {t["name"]: t for t in self.send("tools/list")["result"]["tools"]}
        self.assertIn("strat_claim_add", tools)
        self.assertIn("strat_search", tools)
        self.assertEqual(tools["strat_claim_add"]["inputSchema"]["type"], "object")
        # ворота — только человек: инструмента одобрения нет
        self.assertFalse(any("gate" in n for n in tools))
        self.assertEqual(self.send("ping")["result"], {})
        self.assertEqual(self.send("no/such")["error"]["code"], -32601)

    def test_end_to_end_registry_rules(self):
        self.handshake()
        text, err = self.call("strat_status")
        self.assertTrue(err)  # нет активного проекта
        _, err = self.call("strat_init", slug="demo", title="Демо")
        self.assertFalse(err)
        text, err = self.call("strat_claim_add", text="Рынок растёт", type="fact")
        self.assertTrue(err)  # факт без источника запрещён
        self.assertIn("без источника", text)
        sid, err = self.call("strat_source_add", ref="https://example.org/r", title="Пример: отчёт", reliability="high")
        self.assertEqual((sid, err), ("S1", False))
        cid, err = self.call("strat_claim_add", text="Рынок вырос на 12% в 2025 году", type="fact", sources=[sid])
        self.assertEqual((cid, err), ("C1", False))
        self.call("strat_claim_add", text="Рост продолжится", type="forecast", depends=[cid])
        text, _ = self.call("strat_search", query="рынок рост")
        self.assertIn("C1", text)
        self.assertIn("не факт", text)
        text, _ = self.call("strat_impact", id="S1", flag=True)
        self.assertIn("C1, C2", text)
        # ворота закрыты — стадия не меняется, ответ подсказывает, что нужен человек
        text, err = self.call("strat_stage", name="strategy")
        self.assertTrue(err)
        self.assertIn("gate", text)
        # шаги: повтор выполненного — нормальный ответ, а не ошибка
        self.call("strat_step", action="start", key="k1")
        self.call("strat_step", action="done", key="k1", result="ok")
        text, err = self.call("strat_step", action="start", key="k1")
        self.assertFalse(err)
        self.assertIn("уже выполнен", text)
