"""Headless engine test: fetch + one download per mode. Usage: python tests/test_engine.py URL OUTDIR [modes]"""
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QCoreApplication, QTimer  # noqa
from streamgrab.engine import FetchJob, DownloadJob, activate_engine_updates, ytdlp  # noqa
from streamgrab.formats import Analysis  # noqa

url, outdir = sys.argv[1], sys.argv[2]
modes = sys.argv[3].split(",") if len(sys.argv) > 3 else ["fetch"]
app = QCoreApplication(sys.argv)
log = open(os.path.join(outdir, "test_log.txt"), "a", encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


SPECS = {
    "av": dict(mode="av", res=360, fps=30, container="mp4", codec="h264", abr=None),
    "av_mkv": dict(mode="av", res=480, fps=30, container="mkv", codec="vp9", abr=130),
    "av_webm": dict(mode="av", res=360, fps=30, container="webm", codec="vp9", abr=None),
    "video": dict(mode="video", res=360, fps=30, container="mp4", codec="h264"),
    "audio_mp3": dict(mode="audio", afmt="mp3", aq=192, embed_cover=True),
    "audio_flac": dict(mode="audio", afmt="flac", aq=0, embed_cover=True),
    "audio_orig": dict(mode="audio", afmt="original", aq=0, embed_cover=True),
    "audio_opus": dict(mode="audio", afmt="opus", aq=128, embed_cover=True),
}

state = {"info": None, "queue": [m for m in modes if m != "fetch"]}


def run_next():
    if not state["queue"]:
        app.quit()
        return
    m = state["queue"].pop(0)
    spec = dict(SPECS[m], outdir=os.path.join(outdir, m), template="title", embed_meta=True)
    est = Analysis(state["info"]).estimate(spec)
    p(f"\n=== {m} === estimate: {est}")
    job = DownloadJob(url, spec, est["streams"], info=state["info"])
    last = {"t": 0, "start": time.time(), "first": None}

    def prog(pct, head, detail):
        if last["first"] is None and pct > 0:
            last["first"] = time.time() - last["start"]
            p(f"  first progress after {last['first']:.1f}s")
        if time.time() - last["t"] > 1.5 or pct >= 95:
            last["t"] = time.time()
            p(f"  {pct:5.1f}%  {head}  |  {detail}")

    def done(ok, msg, files):
        p(f"  DONE in {time.time()-last['start']:.1f}s ok={ok} msg={msg!r} files={files}")
        QTimer.singleShot(100, run_next)

    job.progress.connect(prog)
    job.done.connect(done)
    job._keep = job
    state["job"] = job
    job.start()


def fetched(info):
    state["info"] = info
    p(f"FETCH took {time.time()-T0:.1f}s (fast={info.get('_sg_fast')})")
    a = Analysis(info)
    p("title:", info.get("title"), "| formats:", len(info.get("formats") or []))
    p("res options:", [o[0] for o in a.res_options])
    p("audio:", [(f.get("format_id"), f.get("ext"), f.get("abr")) for f in a.audios])
    p("codecs at:", {k: sorted(v) for k, v in a.codecs_at.items()})
    run_next()


def failed(msg):
    p("FETCH FAILED:", msg)
    app.quit()


ytdlp()
T0 = time.time()
f = FetchJob(url, False)
f.done.connect(fetched)
f.failed.connect(failed)
f.start()
app.exec()
