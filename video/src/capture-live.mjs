// Снимает вывод read-only команд CLI в data/live/*.txt (для сцен «вывод команды, снят <дата>»).
// Пишущие команды (--flag, claim add, gate, stage, step, report) здесь НЕ запускаются.
// validate дописывает строку в journal.md — после съёмки файл возвращается из git.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const OUT = path.join(ROOT, "video", "data", "live");
fs.mkdirSync(OUT, { recursive: true });
const py = process.env.PYTHON || "python";
const env = { ...process.env, PYTHONIOENCODING: "utf-8" };
const strat = (args) => {
  const r = spawnSync(py, ["tools/strat.py", ...args], { cwd: ROOT, env, encoding: "utf8" });
  return (r.stdout + r.stderr).replace(/\r/g, "");
};
const jobs = {
  status: ["status", "--journal", "5"],
  claim_C41: ["claim", "show", "C41"],
  claim_C55: ["claim", "show", "C55"],
  validate: ["validate"],
  search_antifrod: ["search", "Антифрод"],
  decision_list: ["decision", "list"],
  decision_check: ["decision", "check"],
  decision_conditions: ["decision", "check", "--conditions"],
  impact_S22: ["impact", "S22"],
  cost: ["cost"],
};
for (const [name, args] of Object.entries(jobs)) fs.writeFileSync(path.join(OUT, name + ".txt"), strat(args));
fs.writeFileSync(path.join(OUT, "outputs_ls.txt"), fs.readdirSync(path.join(ROOT, "projects", "antispam-2027", "outputs")).sort().join("\n") + "\n");
const d = new Date();
const p = (n) => String(n).padStart(2, "0");
fs.writeFileSync(path.join(OUT, "stamp.txt"), `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}\n`);
spawnSync("git", ["checkout", "--", "projects/antispam-2027/journal.md"], { cwd: ROOT });
console.log("снято в", OUT);
