"""Озвучка фраз нейроголосом Microsoft (edge-tts).
python scripts/tts.py <голос> <папка> <фразы.json>  — [{"id","text"}] -> <папка>/<id>.mp3, в stdout JSON {id: мс}.
Готовые файлы не перезаписываются (кеш video/cache/voice, в git не попадает)."""
import asyncio, json, os, re, subprocess, sys
import edge_tts, imageio_ffmpeg
FF = imageio_ffmpeg.get_ffmpeg_exe()

def dur_ms(path):
    err = subprocess.run([FF, "-hide_banner", "-i", path], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", err).groups()
    return round((int(h) * 3600 + int(m) * 60 + float(s)) * 1000)

async def main():
    voice, out_dir, ph_file = sys.argv[1:4]
    rate = os.environ.get("VIDEO_RATE", "+0%")
    os.makedirs(out_dir, exist_ok=True)
    phrases = json.load(open(ph_file, encoding="utf-8"))
    res = {}
    for p in phrases:
        path = os.path.join(out_dir, p["id"] + ".mp3")
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            for attempt in range(6):
                try:
                    await edge_tts.Communicate(p["text"], voice, rate=rate).save(path); break
                except Exception:
                    if os.path.exists(path): os.remove(path)
                    if attempt == 5: raise
                    await asyncio.sleep(2 * (attempt + 1))
            await asyncio.sleep(0.3)
        res[p["id"]] = dur_ms(path)
    sys.stdout.write(json.dumps(res))
asyncio.run(main())
