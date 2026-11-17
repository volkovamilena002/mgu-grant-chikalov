// Сценарий видео. Весь текст в кадре берётся из реальных материалов:
//   data/real.json  — дословные записи сессий Claude Code (scripts/extract_real.py)
//   data/live/*.txt — вывод read-only команд CLI, снятый сейчас (src/capture-live.mjs)
//   projects/antispam-2027/ — документы проекта (только чтение)
// Фразы озвучки (narr) — единственный «авторский» текст; на экране они же как субтитры.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const VID = path.join(ROOT, "video");
const PROJ = path.join(ROOT, "projects", "antispam-2027");
const real = JSON.parse(fs.readFileSync(path.join(VID, "data", "real.json"), "utf8"));
const liveTxt = (n) => fs.readFileSync(path.join(VID, "data", "live", n + ".txt"), "utf8").replace(/\r/g, "").trimEnd();
export const LIVE_DATE = fs.readFileSync(path.join(VID, "data", "live", "stamp.txt"), "utf8").trim();

const R = (k) => real[k].text.replace(/\r/g, "");
const J = (k) => JSON.parse(R(k));
const lines = (s) => s.replace(/\r/g, "").split("\n");
const nonEmpty = (s) => lines(s).filter((l) => l.trim() !== "");
const clip = (s, n) => (s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s);
const projLines = (f) => lines(fs.readFileSync(path.join(PROJ, f === "journal.md" ? f : path.join("outputs", f)), "utf8"));
/** Заголовок раздела + следующие непустые строки (n всего), каждая обрезана до w символов */
const sect = (f, head, n, w = 220, from = 0) => {
  const L = projLines(f);
  const i = L.findIndex((l, k) => k >= from && l.startsWith(head));
  if (i < 0) throw new Error(`нет раздела «${head}» в ${f}`);
  const out = [];
  for (let k = i; k < L.length && out.length < n; k++) if (L[k].trim()) out.push(clip(L[k].replace(/\*\*/g, ""), w));
  return out;
};
const rowsOf = (f, head) => {
  const L = projLines(f); const i = L.findIndex((l) => l.startsWith(head));
  const t = []; for (let k = i; k < L.length; k++) { if (L[k].startsWith("|")) t.push(L[k]); else if (t.length) break; }
  return t.map((r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
};

// ---------- построители элементов ----------
const U = (text, p = 0) => ({ k: "user", text, p });
const A = (text, p = 0) => ({ k: "agent", text, p });
const T = (name, args, p = 0) => ({ k: "tool", name, args, p });
const C = (text, p = 0) => ({ k: "cmd", text, p });
const O = (ls, p = 0, o = {}) => ({ k: "out", lines: Array.isArray(ls) ? ls : nonEmpty(ls), p, ...o });
const D = (ls, p = 0, o = {}) => ({ k: "doc", lines: ls.map((l) => l.split("**").join("")), p, ...o });
const N = (text, p = 0) => ({ k: "note", text, p });
const S = (text, p = 0) => ({ k: "skip", text, p });
const G = (p = 0) => ({ k: "gap", p });
const CLR = (p = 0) => ({ k: "clear", p });
const ASK = (a, chosen, p = 0, dur, compact = false) => ({ k: "ask", header: a.header, q: a.question, opts: a.options.map((o) => ({ label: o.label, desc: compact ? "" : o.description })), chosen, p, dur });
const askOf = (key, i = 0) => J(key).questions[i];

const RECON = { kind: "recon", text: "Воспроизведение реального прогона 16–17.11.2026 по записи сессий Claude Code, ускорено" };
const LIVE = { kind: "live", text: `Вывод команды, снят ${LIVE_DATE}` };
const DOC = (t) => ({ kind: "doc", text: t });
const NONE = (t = "") => ({ kind: "none", text: t });

const kickArgs = R("kick_user").match(/<command-args>([\s\S]*?)<\/command-args>/)[1];
const initCmd = J("init_cmd").command.split(" && ")[0];
const initShown = clip(initCmd.replace(/--question "(.{70})[\s\S]*"$/, '--question "$1…"'), 400);
const fix = (s) => s.replace(/C:\\Users\\[^\\]+\\Desktop\\university-grant-2\\/g, "").replace(/\\/g, "/");
const tsOf = (k) => (real[k].ts || "").slice(11, 19);

// ---------- сцены ----------
export const scenes = [];
const add = (s) => scenes.push(s);

add({
  id: "title", layout: "slide", plaque: RECON,
  narr: [
    "Это «Стратег Фабрики продуктов» — агент для Claude Code. Он ведёт руководителя продукта от размытого запроса до стратегии и потом сопровождает решение.",
    "Покажем один настоящий прогон: что делать в 2027 году с защитой от спама и мошеннических звонков.",
  ],
  items: [
    { k: "h1", text: "Стратег Фабрики продуктов", p: 0 },
    { k: "sub", text: "ИИ-агент для Claude Code: от размытого запроса до стратегии, в которой каждое утверждение можно проверить", p: 0 },
    { k: "b", text: "Демо-прогон: защита от спама и мошеннических звонков, продукт на 2027 год", p: 1 },
    { k: "b", text: "Только открытые источники; внутренних данных оператора нет — и это названо пробелом", p: 1 },
    { k: "note", text: "Сцены-реконструкции собраны из записи сессий; вывод команд CLI в отдельных сценах снят заново и помечен.", p: 1 },
  ],
});

add({
  id: "idea", layout: "slide", plaque: NONE("Идея: доверие к выводу = проверяемое основание"),
  narr: [
    "Веб-интерфейса у агента нет. Это папка с инструкциями, навыками, субагентами, хуками и командой strat. Работает он в чате Claude Code и в терминале.",
    "Главное — реестр утверждений. Каждое сведение записано как факт, гипотеза, прогноз, допущение или синтетика, а у факта есть источник.",
    "В документах рядом с каждым числом стоит ссылка, например C12. Команда validate проверяет это построчно.",
  ],
  items: [
    { k: "h1", text: "Как устроен агент", p: 0 },
    { k: "b", text: "Нет веб-интерфейса: чат Claude Code, терминал, папка с инструкциями (AGENTS.md, .claude/)", p: 0 },
    { k: "sub", text: "Реестр утверждений: у каждого сведения есть тип", p: 1 },
    { k: "chips", chips: [["факт", "#7ee787"], ["гипотеза", "#f2b84b"], ["прогноз", "#79b8ff"], ["допущение", "#d2a8ff"], ["синтетика", "#ff7b72"]], p: 1 },
    { k: "b", text: "У факта всегда есть источник с надёжностью: high, medium или low", p: 1 },
    { k: "b", text: "Вывод агента — гипотеза или прогноз, а не факт; прежний ответ сам не становится фактом", p: 1 },
    { k: "b", text: "В документах ссылка [C12] стоит в той же строке, что и число", p: 2 },
    { k: "b", text: "python tools/strat.py validate проверяет ссылки; запись в состояние — только через CLI", p: 2 },
  ],
});

add({
  id: "kick", layout: "term", fs: 15, plaque: RECON,
  narr: [
    "Начинаем с запроса. Вот реальная реплика руководителя, слово в слово: платная подписка, бесплатная защита или не вкладываться.",
    "Агент создаёт проект и сначала спрашивает только важное: какое решение будет принято, кто получатель и какие данные разрешены.",
    "Ответы выбираются кнопками, рекомендуемый вариант идёт первым.",
  ],
  items: [
    U("/kickoff " + kickArgs, 0),
    T("Bash", initShown, 1),
    O(["Создан проект «antispam-2027» в projects/antispam-2027", ...nonEmpty(R("init_res")).slice(1, 2)], 1),
    ASK(askOf("ask_kick", 0), 0, 1, 2.6, true),
    ASK(askOf("ask_kick", 1), 0, 2, 2.6, true),
    ASK(askOf("ask_kick", 2), 0, 2, 2.6, true),
  ],
});

add({
  id: "g1", layout: "term", fs: 15, plaque: RECON, carry: "kick",
  narr: [
    "Дальше агент пишет бриф и запускает validate. Он замечает числа без ссылок и сам их исправляет.",
    "Затем первые ворота, гэ-один: человек подтверждает бриф. Без этого агент в исследование не пойдёт.",
  ],
  items: [
    T("Bash", "python tools/strat.py validate", 0),
    O(nonEmpty(R("validate_warn")).slice(0, 3).map((l) => clip(l, 150)), 0),
    T("Bash", 'python tools/strat.py claim add "В коммуникации о защите нельзя обещать «100% защиты» (ограничение руководителя)" --type assumption', 0),
    O(["C4"], 0),
    T("Edit", "outputs/01-brief.md  →  «- В коммуникации нельзя обещать «100% защиты» [C4].»", 0),
    T("Bash", "python tools/strat.py validate | tail -1", 0),
    O(nonEmpty(R("validate_ok")).slice(0, 1), 0),
    A(R("brief_done"), 1),
    ASK(askOf("ask_g1"), 0, 1, 5.5),
    C('python tools/strat.py gate G1 approve --note "Бриф подтверждён: модель защиты в план 2027 (платно / бесплатно в тарифах / как есть) и коммуникация; …"', 1),
    O(nonEmpty(R("gate_g1_res")).slice(0, 2), 1),
  ],
  shot: { file: "01-kickoff.png", at: "gate", h: 1500, fs: 13 },
});

add({
  id: "research", layout: "term", fs: 15, plaque: RECON,
  narr: [
    "План исследования строится от вопросов, которые могут изменить решение. Здесь семь вопросов: от масштаба проблемы до ограничений рекламы.",
    "Читать сотни страниц в основном контексте дорого и небезопасно. Поэтому агент запускает пять субагентов-исследователей параллельно.",
    "Каждый сам регистрирует источники и утверждения. Здесь ускорено: на деле это заняло около полутора минут.",
    "Итог: двадцать три источника и пятьдесят два утверждения.",
  ],
  items: [
    N("— outputs/02-research-plan.md (фрагмент) —", 0),
    D(rowsOf("02-research-plan.md", "| # |").slice(2, 9).map((r) => clip(`| ${r[0]} | ${r[1]} |`, 150)), 0),
    CLR(1),
    T("Bash", "strat step start collect-R1 … collect-R6R7", 1),
    O(nonEmpty(R("steps_start_res")).slice(0, 5), 1),
    T("Agent", `researcher · ${J("ag_r1").description}`, 1),
    T("Agent", `researcher · ${J("ag_r2").description}`, 1),
    T("Agent", `researcher · ${J("ag_r3").description}`, 1),
    T("Agent", `researcher · ${J("ag_r45").description}`, 1),
    T("Agent", `researcher · ${J("ag_r67").description}`, 1),
    S("×8 · пять исследователей работают параллельно · реально ≈ 1,5 мин (16:24:50 → 16:26:19)", 2),
    A(nonEmpty(R("collect_done"))[0], 3),
  ],
});

const claimC55 = liveTxt("claim_C55").split("\n");
const claimC41 = liveTxt("claim_C41").split("\n");
const journalErr = projLines("journal.md").find((l) => l.includes("[error]")).replace(/^-\s*/, "");
add({
  id: "claims", layout: "term", fs: 15, plaque: LIVE,
  narr: [
    "Посмотрим на утверждение вживую. Команда claim show: тип, источник, надёжность и ссылка на сам закон.",
    "Здесь важный эпизод. Сначала нормы двести десятого закона были взяты из пересказа юрфирмы, надёжность средняя.",
    "Агент нашёл текст закона и заменил утверждение. Старое не удалено, а отозвано с причиной.",
    "Агент и ошибался, и сам себя ловил. Субагент назвал номера утверждений со сдвигом. Агент сверил их с реестром и записал ошибку в журнал.",
  ],
  items: [
    C("python tools/strat.py claim show C55", 0),
    O(claimC55, 0, { lps: 7 }),
    CLR(1),
    C("python tools/strat.py claim show C41", 1),
    O(claimC41, 1, { lps: 7 }),
    N("— journal.md, запись типа [error] —", 3),
    D([journalErr], 3),
  ],
});

add({
  id: "situation", layout: "term", fs: 15, plaque: DOC("Документ проекта: outputs/03-situation.md (фрагменты)"),
  narr: [
    "Картина ситуации разделяет известное, предположения и пробелы.",
    "Известное идёт со ссылками на реестр. Выводы самого агента помечены как гипотезы, а не как факты.",
    "Пробелы названы честно: чего не знаем, почему и чем это опасно. Внутренних данных оператора нет, и это записано, а не замазано.",
    "Противоречия источников тоже названы: ЦБ видит рост операций, МВД — падение дел, потому что они считают разное.",
  ],
  items: [
    D(sect("03-situation.md", "## Коротко", 4, 235), 0),
    G(1),
    D(sect("03-situation.md", "## Чего мы не знаем", 5, 205), 2),
    G(3),
    D(sect("03-situation.md", "## Противоречия в источниках", 2, 300), 3),
  ],
});

const optRows = rowsOf("04-options.md", "| Критерий");
const pick = (names) => names.map((n) => optRows.find((r) => r[0].startsWith(n))).filter(Boolean);
add({
  id: "opt_table", layout: "slide", plaque: DOC("Документ проекта: outputs/04-options.md · таблица сравнения (строки)"),
  narr: [
    "Дальше шесть вариантов, которые различаются логикой, а не степенью. Среди них обязательный вариант «оставить как есть».",
    "Сравнение идёт по трём критериям из брифа. Видно, что платная подписка и бесплатная защита как довод не проходят, а оснований под них мало.",
  ],
  items: [
    { k: "h1", text: "Варианты по критериям брифа", p: 0 },
    {
      k: "table", p: 1, dur: 7,
      head: optRows[0].map((c) => clip(c.replace(/\*\*/g, ""), 34)),
      rows: pick(["Отличает от конкурентов", "Окупается за 12", "Обратимость", "Уверенность"]).map((r) => r.map((c) => c.replace(/\*\*/g, ""))),
    },
    { k: "note", text: "A оставить как есть · B платная подписка · C бесплатно в тарифах · D заметность · E «защита близких» · F партнёрство с банком", p: 1 },
  ],
});

add({
  id: "redteam", layout: "term", fs: 15, plaque: RECON,
  narr: [
    "Возражения пишет отдельный субагент — ред-тим, на самой сильной модели.",
    "Он нашёл, что вариант «оставить как есть» агент описал слабее, чем он есть на самом деле. А вариант «сделать заметным» держался на круговой опоре: незаметность — лишь оценка руководителя.",
    "Агент принял возражения: переписал вариант A и поставил проверку качества фильтра раньше громкой коммуникации.",
  ],
  items: [
    T("Agent", `red-team · ${J("ag_redteam1").description}`, 0),
    S("×4 · независимый критик читает 03-situation и 04-options · реально 1 мин 38 с (17:23:05 → 17:24:43)", 0),
    N("— 04-options.md, вариант A: возражение red-team —", 1),
    D(sect("04-options.md", "### Возражения (red-team)", 4, 250, 14), 1),
    N("— 04-options.md, вариант D: возражение red-team —", 1),
    D(sect("04-options.md", "### Возражения (red-team)", 4, 250, 130), 1),
    A(nonEmpty(R("g2_text")).find((l) => l.includes("Вариант D держался")).replace(/^-\s*/, ""), 2),
  ],
});

add({
  id: "g2", layout: "term", fs: 15, plaque: RECON,
  narr: [
    "Вторые ворота, гэ-два. Агент рекомендует комбинацию «А плюс Д» с двумя пилотами, но выбор остаётся за человеком.",
    "Ответ человека виден на экране: он выбрал рекомендованный вариант.",
  ],
  items: [
    ASK(askOf("ask_g2"), 0, 0, 6),
    C('python tools/strat.py gate G2 approve --note "Выбрана комбинация A + D с пилотами E и F: I кв. 2027 — исполнение 210-ФЗ; …"', 1),
    O(nonEmpty(R("gate_g2_res")).slice(0, 3), 1),
  ],
});

const rt2 = lines(R("redteam2_report")).map((l) => l.replace(/^ {2}/, ""));
const rt2pick = (re) => { const i = rt2.findIndex((l) => re.test(l)); return [clip(rt2[i], 190), clip(rt2[i + 1], 230)]; };
add({
  id: "strategy", layout: "term", fs: 15, plaque: RECON,
  narr: [
    "Затем продуктовая стратегия, коммуникационная и план проверки, с порогами, заданными заранее.",
    "Ред-тим проверяет и их. Он нашёл, например, что главное допущение — видимая защита снижает отток — не успеет проверяться в 2027 году. И что одно обещание держится на допущении.",
    "Агент заменил пороги, запустил тест сразу, а руководителя попросил подтвердить факт о собственном продукте.",
  ],
  items: [
    A(nonEmpty(R("strategy_text"))[0] + "\n" + nonEmpty(R("strategy_text")).find((l) => l.includes("Принцип продукта")).replace(/^- /, "").replace(/\[([^\]]+)\]\([^)]*\)/g, "$1"), 0),
    N("— 07-validation-plan.md: пороги, заданные до получения данных —", 0),
    D(sect("07-validation-plan.md", "## Минимальный значимый эффект и пороги", 6, 190), 0),
    CLR(1),
    T("Agent", "red-team · Red-team проверка стратегий", 1),
    S("реально 1 мин 52 с (17:31:50 → 17:33:42)", 1),
    D(rt2pick(/^\*\*1\. Главное допущение не успевает/), 1),
    D(rt2pick(/^\*\*1\. Обещание названо/), 1),
    C('python tools/strat.py claim add "Допущение (порог, заменяет прежний): пропуск считаем высоким, если …" --type assumption --supersedes C76', 2),
    O(nonEmpty(R("claim_add_res")), 2),
  ],
});

add({
  id: "verify", layout: "term", fs: 15, plaque: RECON,
  narr: [
    "Перед последними воротами агент проверяет сам себя. Оценщик judge на дешёвой модели поставил тридцать четыре из тридцати шести.",
    "Validate не находит ни ошибок, ни предупреждений. Всё, что оценщик отметил слабым, агент доработал.",
  ],
  items: [
    T("Agent", `judge · ${J("ag_judge").description}`, 0),
    S("реально 1 мин 37 с (17:45:12 → 17:46:50)", 0),
    C('python tools/strat.py log "Judge: 34/36 (94%), порог пройден; доработаны возражения к F (написаны агентом, помечено) и таблица обещаний в 06" --kind reasoning', 1),
    O(["записано"], 1),
    C("python tools/strat.py validate | tail -1", 1),
    O(nonEmpty(R("validate_ok")).slice(0, 1), 1),
  ],
});

add({
  id: "g3", layout: "term", fs: 15, plaque: RECON,
  narr: [
    "Третьи ворота, гэ-три: человек утверждает стратегию.",
    "После этого агент записывает восемь решений. У каждого есть ответственный, показатель и условие пересмотра.",
  ],
  items: [
    ASK(askOf("ask_g3"), 0, 0, 6.5),
    C('python tools/strat.py gate G3 approve --note "Стратегия утверждена: A+D, пилоты E и F; validate 0 ошибок; judge 34/36"', 1),
    O(nonEmpty(R("gate_g3_res")).slice(0, 3), 1),
  ],
});

add({
  id: "decisions", layout: "term", fs: 14, plaque: LIVE,
  narr: [
    "Эта таблица — живой вывод команды decision list. Восемь решений, у каждого роль-ответственный и показатель.",
    "Условия пересмотра записаны заранее. Так позже видно, когда решение пора пересматривать.",
  ],
  items: [
    C("python tools/strat.py decision list", 0),
    O(liveTxt("decision_list").split("\n").map((l) => clip(l, 235)), 0, { lps: 3.2 }),
  ],
});

const hook = R("hook").split("\n").map((l) => l.replace(/\s+\(важно:.*$/, "…").replace(/^(  Q\d: .{110}).*$/, "$1…"));
const nextLines = R("next_text").split("\n");
add({
  id: "resume", layout: "term", fs: 15, plaque: { kind: "recon", text: "Новый чат после перерыва · воспроизведение записи второй сессии Claude Code, ускорено" },
  narr: [
    "Теперь перерыв. Закрываем окно, открываем новый чат. Хук SessionStart сам показывает, где мы остановились: стадию, ворота, открытые вопросы и следующий шаг.",
    "Командой next агент сверяет незавершённые шаги и ничего не повторяет. Решений с устаревшими основаниями нет.",
    "Он сам предлагает проверить свежие правовые новости, и человек соглашается.",
  ],
  items: [
    N("— хук SessionStart, вывод при открытии нового чата —", 0),
    O(hook.filter((l) => l.trim()).map((l) => clip(l, 170)), 0, { lps: 4.5 }),
    U("/next", 1),
    T("PowerShell", J("next_status_cmd").command, 1),
    O(["Решений с устаревшими основаниями нет."], 1),
    A(clip(nextLines.slice(0, 1)[0], 500) + "\n" + nextLines.filter((l) => l.startsWith("Можно заранее")).join(""), 1),
    U(R("yes_check"), 2),
  ],
  shot: { file: "02-resume.png", at: "end", h: 1000 },
});

add({
  id: "newdata", layout: "term", fs: 15, plaque: { kind: "recon", text: "Вторая сессия: проверка правовых новостей · воспроизведение записи, ускорено" },
  narr: [
    "Новые данные. Исследователь проверяет, утвердило ли правительство критерии мошеннического номера и внесён ли «Антифрод три ноль» в Госдуму.",
    "Нашлись четыре новых утверждения, но только из источников средней надёжности. Первоисточники не открывались, и агент записал это как ограничение.",
    "Он закрывает шаг и сообщает: ни одно решение пересматривать не нужно, но до конца января критерии надо проверить снова.",
  ],
  items: [
    T("Agent", `researcher · ${J("ag_law").description}`, 0),
    S("×6 · исследователь проверяет около 8 страниц · реально ≈ 1 мин (18:50:51 → 18:51:50)", 0),
    N("— отчёт субагента (по реестру проверяет основной агент) —", 1),
    A(nonEmpty(R("law_handback")).find((l) => l.includes("Проверено около 8")).trim(), 1),
    C("python tools/strat.py claim show C85", 1),
    O(nonEmpty(R("claims_show_res")).slice(0, nonEmpty(R("claims_show_res")).findIndex((l) => l.startsWith("источник")) + 1), 1, { lps: 7 }),
    C('python tools/strat.py log "Ранняя проверка 16.11.2026: условия пересмотра D1, D2, D6 не сработали. Критерии номеров пока проект (C85), …" --kind reasoning', 2),
    O(nonEmpty(R("law_log_res")), 2),
    A(R("law_final").split("\n")[0], 2),
  ],
});

const searchLines = liveTxt("search_antifrod").split("\n").map((l) => clip(l, 205));
add({
  id: "impact", layout: "term", fs: 15, plaque: LIVE,
  narr: [
    "А что будет, если источник про «Антифрод три ноль» окажется неверным? Команда impact показывает всё, что от него зависит.",
    "Одно утверждение, пять документов и решение дэ-шесть. Флаг не ставили: это просто просмотр.",
    "Validate по-прежнему без ошибок. Условия пересмотра всех восьми решений записаны, и по новым данным их можно сверять.",
  ],
  items: [
    C('python tools/strat.py search "Антифрод"', 0),
    O(searchLines.slice(0, 7), 0, { lps: 5 }),
    CLR(0),
    C("python tools/strat.py impact S22", 0),
    O(liveTxt("impact_S22"), 1, { lps: 3.5 }),
    C("python tools/strat.py validate", 2),
    O(liveTxt("validate"), 2),
    C("python tools/strat.py decision check", 2),
    O(liveTxt("decision_check"), 2),
  ],
  shot: { file: "03-validate-impact.png", at: "end", h: 600 },
});

const trLines = (head, n) => sect("00-transparency.md", head, n, 120);
add({
  id: "transparency", layout: "term", fs: 15, plaque: LIVE,
  narr: [
    "Прозрачность. Отчёт показывает время и стоимость по стадиям и по моделям.",
    "Агент обошёлся примерно в десять долларов: восемь семьдесят девять до решений и один двадцать четыре после перерыва. Почти всё — Opus. Исследователи на Sonnet стоили меньше доллара.",
    "В живом выводе сумма больше: хук учитывает и вспомогательные сессии разработчика. В стоимость агента они не входят.",
  ],
  items: [
    C("python tools/strat.py cost", 0),
    O(liveTxt("cost"), 1, { lps: 4 }),
    CLR(2),
    N("— 00-transparency.md, формируется командой strat report —", 2),
    D(trLines("## Время по стадиям", 11), 2),
  ],
});

add({
  id: "human", layout: "slide", plaque: DOC("По docs/description.md, раздел 6 (цифры прогона 16–17.11.2026)"),
  narr: [
    "Человек отвечал на вопросы брифа, прошёл три ворот и подтвердил один факт о своём продукте. Документы вручную не правились.",
    "Две проверки ред-тима, оценщик на тридцать четыре из тридцати шести и ноль замечаний у validate.",
  ],
  items: [
    { k: "h1", text: "Что сделал человек и сколько это стоило", p: 0 },
    {
      k: "kv", p: 0, dur: 6, rows: [
        ["Человек", "ответы на вопросы брифа; ворота G1, G2, G3; подтверждение факта C72 о собственном продукте; ручных правок документов не было"],
        ["Время", "≈ 2 ч 10 мин в первой сессии (с ожиданием на воротах) и ≈ 25 мин во второй"],
        ["Стоимость агента", "≈ $10.0: $8.79 до G3 и решений + $1.24 после перерыва"],
        ["По моделям", "Opus $9.19 · Sonnet (исследователи) $0.82 · Haiku (judge) $0.02"],
        ["Объём", "27 источников, 88 утверждений, 8 решений D1–D8, 7 открытых вопросов"],
        ["Проверки", "red-team дважды · judge 34 из 36 · validate: 0 ошибок, 0 предупреждений"],
      ],
    },
  ],
});

add({
  id: "outputs", layout: "term", fs: 15, plaque: LIVE,
  narr: [
    "На выходе — резюме для руководителя, семь документов со ссылками на реестр и отчёт о прозрачности.",
    "Всё это обычные файлы в папке проекта. Их можно открыть, проверить и положить в историю изменений.",
  ],
  items: [
    C("ls projects/antispam-2027/outputs", 0),
    O(liveTxt("outputs_ls"), 0, { lps: 6 }),
    N("— 00-summary.md, первые строки —", 1),
    D(projLines("00-summary.md").filter((l) => l.trim()).slice(0, 3).map((l) => clip(l, 215)), 1),
    N("— 00-transparency.md, время по стадиям —", 1),
    D(trLines("## Время по стадиям", 11), 1),
  ],
  shot: { file: "04-outputs.png", at: "end", h: 900 },
});

add({
  id: "final", layout: "slide", plaque: NONE("Репозиторий и инструкция — открытые"),
  narr: [
    "Итого агент проводит от запроса до стратегии, показывает основания и возражения, останавливается на воротах и продолжает после перерыва.",
    "Он не придумывает данные: чего нет, то названо пробелом. Исходники и инструкция — в репозитории на гитхабе. Спасибо!",
  ],
  items: [
    { k: "h1", text: "Что умеет агент", p: 0 },
    { k: "b", text: "8 стадий и 3 ворот: решает человек (G1, G2, G3)", p: 0 },
    { k: "b", text: "Субагенты: researcher, red-team, judge, data-analyst, synthetic-respondent", p: 0 },
    { k: "b", text: "Реестр утверждений, validate, impact, decision check", p: 0 },
    { k: "b", text: "Продолжение после перерыва и пересмотр при новых данных", p: 1 },
    { k: "b", text: "Только открытые источники; пробелы названы честно", p: 1 },
    { k: "big", text: "github.com/volkovamilena002/mgu-grant-chikalov", p: 1 },
  ],
});

// Таблица «как читать». Произношение (только для озвучки; на субтитры не влияет)
export const SPEAK = [
  [/Claude Code/g, "Клод Код"],
  [/\bred-team\b/gi, "ред-тим"],
  [/\bCLI\b/g, "си-эл-ай"],
  [/\bvalidate\b/gi, "вэлидэйт"],
  [/\bimpact\b/g, "импакт"],
  [/\bjudge\b/g, "джадж"],
  [/\bSessionStart\b/g, "сэшн старт"],
  [/\bstrat\b/g, "страт"],
  [/\bclaim show\b/g, "клэйм шоу"],
  [/\bdecision list\b/g, "дисижн лист"],
  [/\bnext\b/g, "некст"],
  [/\bOpus\b/g, "Опус"],
  [/\bSonnet\b/g, "Сонет"],
  [/C12/g, "цэ-двенадцать"],
  [/«|»/g, ""],
];
