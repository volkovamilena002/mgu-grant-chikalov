// Сборка демо-видео: сценарий → озвучка (edge-tts) → таймлайн → кадры (Playwright) → mp4 + srt + скриншоты.
//   npm run video             — полная сборка
//   VIDEO_DRY=1 npm run video — только озвучка и хронометраж (без рендера кадров)
//   VIDEO_SHOTS=1 …           — только 4 скриншота для PDF
import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium } from "@playwright/test";
import { scenes, SPEAK } from "./scenario.mjs";

const VID = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = path.resolve(VID, "..");
const OUT = path.join(VID, "out");
const CACHE = path.join(VID, "cache", "voice");
const IMG = path.join(ROOT, "docs", "img");
const FPS = Number(process.env.VIDEO_FPS ?? 15);
const VOICE = process.env.VIDEO_VOICE ?? "ru-RU-DmitryNeural";
const RATE = process.env.VIDEO_RATE ?? "+0%";
const PY = process.env.VIDEO_PY ?? [path.join(VID, ".venv", "Scripts", "python.exe"), path.join(VID, ".venv", "bin", "python")].find((p) => fs.existsSync(p));
if (!PY) throw new Error("Нет video/.venv: выполните npm run setup (или задайте VIDEO_PY)");
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(CACHE, { recursive: true });
fs.mkdirSync(IMG, { recursive: true });

// ---------- озвучка ----------
const speakable = (t) => SPEAK.reduce((s, [re, to]) => s.replace(re, to), t);
const phraseOf = (t) => (typeof t === "string" ? { text: t, speak: speakable(t) } : { text: t.text, speak: speakable(t.speak ?? t.text) });
const idOf = (speak) => createHash("sha1").update(`${VOICE}|${RATE}|${speak}`).digest("hex").slice(0, 12);
const run = (list) => {
  const f = path.join(CACHE, "phrases.json");
  fs.writeFileSync(f, JSON.stringify(list));
  return spawnSync(PY, [path.join(VID, "scripts", "tts.py"), VOICE, CACHE, f], {
    encoding: "utf8",
    env: { ...process.env, PYTHONIOENCODING: "utf-8", VIDEO_RATE: RATE },
    timeout: 180000,
  });
};
const all = scenes.flatMap((s) => s.narr.map(phraseOf));
const items = [...new Map(all.map((p) => [idOf(p.speak), { id: idOf(p.speak), text: p.speak }])).values()];
const FAKE = !!process.env.VIDEO_FAKE; // отладка вёрстки без озвучки: каждая фраза 5 с
for (const i of FAKE ? [] : items) {
  if (fs.existsSync(path.join(CACHE, i.id + ".mp3"))) continue;
  for (let a = 1; ; a++) {
    const r = run([i]);
    if (r.status === 0) break;
    if (a === 4) throw new Error("Озвучка не удалась: " + i.text + "\n" + r.stderr);
    spawnSync(process.execPath, ["-e", `setTimeout(()=>{}, ${3000 * a})`]);
  }
}
const durs = FAKE ? Object.fromEntries(items.map((i) => [i.id, 5000])) : JSON.parse(run(items).stdout);

// ---------- таймлайн ----------
const LEAD = 0.4, GAP = 0.3, TAIL = 0.65;
const SPEED = Number(process.env.VIDEO_TYPING ?? 1.25); // во сколько раз «печать» быстрее базовой
const dOf = (it) => (it.dur ? it.dur : baseDur(it) / SPEED);
const baseDur = (it) => {
  const n = (it.text ?? it.args ?? "").length;
  switch (it.k) {
    case "user": return Math.max(0.9, n / 42);
    case "agent": return Math.max(0.6, n / 160);
    case "tool": return Math.max(0.5, n / 140);
    case "cmd": return Math.max(0.8, n / 55);
    case "out": return Math.max(0.4, it.lines.length / (it.lps ?? 10));
    case "doc": return Math.max(0.5, it.lines.length / (it.lps ?? 7));
    case "note": return 0.35;
    case "skip": return 1.5;
    case "gap": return 0.1;
    case "clear": return 0.05;
    case "ask": return 4;
    case "h1": return 0.6;
    case "sub": return 0.8;
    case "b": return 0.7;
    case "chips": return 0.7;
    case "big": return 0.8;
    default: return 0.6;
  }
};
let cursor = 0;
const tl = { scenes: [], clips: [] };
for (const sc of scenes) {
  const start = cursor, phrases = [];
  let pt = start + LEAD;
  for (const raw of sc.narr) {
    const p = phraseOf(raw), id = idOf(p.speak), d = durs[id] / 1000;
    phrases.push({ start: pt, end: pt + d, text: p.text, id });
    pt += d + GAP;
  }
  const narrEnd = phrases.length ? phrases[phrases.length - 1].end : start + LEAD;
  let prevEnd = start + 0.3;
  const its = [];
  for (const it of sc.items) {
    const ps = phrases[Math.min(it.p ?? 0, phrases.length - 1)].start;
    const pad = it.k === "clear" || it.k === "gap" ? 0 : ["ask", "cmd", "tool"].includes(it.k) ? 0.35 : 0.12;
    const s = Math.max(prevEnd + pad, ps);
    const d = dOf(it);
    its.push({ ...it, start: s, dur: d });
    prevEnd = s + d;
  }
  const end = Math.max(narrEnd, prevEnd) + TAIL;
  tl.scenes.push({ id: sc.id, layout: sc.layout, fs: sc.fs, plaque: sc.plaque, start, end, items: its, phrases, carryId: sc.carry, shot: sc.shot });
  for (const ph of phrases) tl.clips.push({ start: ph.start, id: ph.id });
  cursor = end;
}
for (const sc of tl.scenes) if (sc.carryId) sc.carry = tl.scenes.find((x) => x.id === sc.carryId).items.filter((i) => i.k !== "clear");
const TOTAL = cursor;
const words = all.reduce((n, p) => n + p.text.split(/\s+/).length, 0);

// ---------- приватность: в кадре не должно быть этого ----------
const blob = JSON.stringify(tl);
const USER = os.userInfo().username.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const bad = blob.match(new RegExp(String.raw`@|${USER}|C:\\\\Users|C:\/Users|gmail`, "gi"));
if (bad) throw new Error("Приватные данные в сценах: " + [...new Set(bad)].join(", "));

fs.writeFileSync(path.join(OUT, "timeline.json"), JSON.stringify({ total: TOTAL, scenes: tl.scenes.map((s) => ({ id: s.id, start: s.start, end: s.end })) }, null, 1));
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
console.log(`Озвучка: ${all.length} фраз, ${words} слов. Длительность: ${mmss(TOTAL)} (${TOTAL.toFixed(1)} с)`);
for (const s of tl.scenes) console.log(`  ${mmss(s.start)}–${mmss(s.end)}  ${s.id}`);
if (process.env.VIDEO_DRY) process.exit(0);
const DEBUG = process.env.VIDEO_DEBUG; // каталог для кадров всех сцен (середина и конец)

// ---------- рендер ----------
const ffmpeg = spawnSync(PY, ["-c", "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"], { encoding: "utf8" }).stdout.trim();
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
await page.goto(pathToFileURL(path.join(VID, "src", "player.html")).href);
await page.evaluate((t) => window.load(t), tl);

// скриншоты для PDF (те же сцены, окно выше)
for (const sc of tl.scenes.filter((s) => s.shot)) {
  await page.setViewportSize({ width: 1280, height: sc.shot.h ?? 720 });
  await page.evaluate(([t, f]) => window.renderAt(t, f), [sc.end - 0.35, sc.shot.fs ?? null]);
  await page.screenshot({ path: path.join(IMG, sc.shot.file), type: "png" });
  console.log("кадр:", sc.shot.file);
}
if (DEBUG) {
  fs.mkdirSync(DEBUG, { recursive: true });
  await page.setViewportSize({ width: 1280, height: 720 });
  for (const sc of tl.scenes) for (const [nm, f] of [["a", 0.45], ["b", 0.999]]) {
    await page.evaluate((t) => window.renderAt(t), sc.start + (sc.end - sc.start) * f - (f > 0.9 ? 0.4 : 0));
    await page.screenshot({ path: path.join(DEBUG, `${sc.id}-${nm}.png`) });
  }
  await browser.close();
  process.exit(0);
}
await page.setViewportSize({ width: 1280, height: 720 });
if (process.env.VIDEO_SHOTS) {
  await browser.close();
  process.exit(0);
}

const mp4 = path.join(OUT, "strateg-demo.mp4");
const clips = tl.clips;
const inputs = clips.flatMap((c) => ["-i", path.join(CACHE, c.id + ".mp3")]);
const delays = clips.map((c, k) => {
  const ms = Math.round(c.start * 1000);
  return `[${k + 1}:a]adelay=${ms}|${ms}[a${k}]`;
});
const mix = `${clips.map((_, k) => `[a${k}]`).join("")}amix=inputs=${clips.length}:normalize=0:dropout_transition=0,loudnorm=I=-16:TP=-1.5:LRA=11,apad=whole_dur=${TOTAL.toFixed(2)}[aout]`;
const proc = spawn(
  ffmpeg,
  ["-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", String(FPS), "-i", "pipe:0", ...inputs,
    "-filter_complex", [...delays, mix].join(";"), "-map", "0:v", "-map", "[aout]",
    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", String(FPS),
    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-t", TOTAL.toFixed(2), mp4],
  { stdio: ["pipe", "inherit", "inherit"] },
);
const done = new Promise((res, rej) => {
  proc.on("exit", (c) => (c === 0 ? res() : rej(new Error("ffmpeg " + c))));
  proc.on("error", rej);
});
const frames = Math.ceil(TOTAL * FPS);
let prevSig = null, buf = null, shots = 0;
for (let i = 0; i < frames; i++) {
  const sig = await page.evaluate((t) => window.renderAt(t), i / FPS);
  if (sig !== prevSig) {
    buf = await page.screenshot({ type: "jpeg", quality: 92 });
    prevSig = sig;
    shots++;
  }
  if (!proc.stdin.write(buf)) await new Promise((r) => proc.stdin.once("drain", r));
  if (i % 450 === 0) console.log(`кадр ${i}/${frames} (${mmss(i / FPS)})`);
}
proc.stdin.end();
await done;
await browser.close();

// субтитры
const ts = (s) => {
  const ms = Math.round(s * 1000), p = (n, l = 2) => String(n).padStart(l, "0");
  return `${p(Math.floor(ms / 3600000))}:${p(Math.floor(ms / 60000) % 60)}:${p(Math.floor(ms / 1000) % 60)},${p(ms % 1000, 3)}`;
};
const srt = tl.scenes.flatMap((s) => s.phrases).map((p, k) => `${k + 1}\n${ts(p.start)} --> ${ts(p.end + 0.2)}\n${p.text}\n`).join("\n");
fs.writeFileSync(path.join(OUT, "strateg-demo.srt"), srt);
console.log(`Готово: ${mp4} (${mmss(TOTAL)}), уникальных кадров ${shots}/${frames}`);
