"""Where does a cold worker spend its time before the first progress?  python tests/diag_cold_start.py OUTDIR"""
import json
import os
import sys
import time

T0 = time.time()
OUT = os.path.abspath(sys.argv[1])
os.makedirs(OUT, exist_ok=True)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def t(label):
    print(f"{time.time() - T0:6.2f}s  {label}", flush=True)


from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402
t("PySide6 imported")
from streamgrab import engine  # noqa: E402
t("streamgrab.engine imported")
engine.ytdlp()
t("yt_dlp imported")
app = QCoreApplication([])
info_path = os.path.join(OUT, "info.json")
if not os.path.exists(info_path):
    info = engine.fetch_info("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(info, f)
    t("fetched info (first run only)")
with open(info_path, encoding="utf-8") as f:
    info = json.load(f)
t("info loaded")

seen = []


def prog(pct, head, detail):
    key = (round(pct) if pct and pct > 0 else pct, head)
    if not seen or seen[-1] != key:
        seen.append(key)
        t(f"progress {pct:.1f}% {head} | {detail[:60]}")


done = []
spec = dict(mode="audio", afmt="mp3", aq=128, embed_cover=True, outdir=os.path.join(OUT, "dl"), template="title",
            cookies="none", exists="replace")
job = engine.DownloadJob("https://www.youtube.com/watch?v=jNQXAC9IVRw", spec, info=info)
job.progress.connect(prog)
job.done.connect(lambda ok, msg, files: done.append(ok))
orig = engine._Log.debug


def dbg(self, msg):
    if any(k in msg for k in ("[youtube]", "[info]", "[download]", "jsc", "challenge", "player", "Downloading")):
        t("ytdlp: " + msg[:110])
    return orig(self, msg)


engine._Log.debug = dbg
t("job created")
job.start()
while not done:
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    time.sleep(0.01)
t(f"done ok={done[0]}")
