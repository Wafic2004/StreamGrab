"""Queue / worker-process tests (real downloads, isolated data folder).

usage: python tests/test_queue.py OUTDIR [CASES]
cases: QU-PAR QU-CANCEL QU-PAUSE QU-PERSIST QU-CRASH QU-EXISTS QU-PLAYLIST QU-NAMES QU-RESTORE
"""
import os
import sys
import json
import time
import glob
import shutil
import tempfile
import subprocess

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "qa_runs/queue")
WANT = set(sys.argv[2].split(",")) if len(sys.argv) > 2 else None
os.makedirs(OUT, exist_ok=True)

# isolate everything the app writes (settings live in a dict below; data dir via LOCALAPPDATA)
SANDBOX = os.path.join(OUT, "_appdata")
os.makedirs(SANDBOX, exist_ok=True)
os.environ["LOCALAPPDATA"] = SANDBOX

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer   # noqa: E402
from streamgrab.downloads import QueueManager                       # noqa: E402
from streamgrab.utils import find_tool                              # noqa: E402

app = QCoreApplication([])
TD1 = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"   # Big Buck Bunny 10:35 4K60
TD2 = "https://www.youtube.com/watch?v=jNQXAC9IVRw"   # Me at the zoo 0:19
TD3 = "https://www.youtube.com/shorts/YsKxkP_kGbE"    # Short 0:30
PL = "https://www.youtube.com/playlist?list=PLa1F2ddGya_8Geu0rJ4y4dVCc9jZxS2IB"
RESULTS = os.path.join(OUT, "queue_results.jsonl")


class FakeSettings(dict):
    def value(self, k, default=None, type=None):
        v = self.get(k, default)
        return type(v) if type and v is not None else v

    def setValue(self, k, v):
        self[k] = v


def want(c):
    return WANT is None or c in WANT


def rec(**kw):
    print(json.dumps(kw, ensure_ascii=False), flush=True)
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(kw, ensure_ascii=False) + "\n")


def spec_audio(d, fmt="mp3", q=128, **kw):
    return dict(dict(mode="audio", afmt=fmt, aq=q, embed_cover=True, outdir=d, template="title", cookies="none"), **kw)


def spec_av(d, res=240, cont="mp4", codec="h264", **kw):
    return dict(dict(mode="av", res=res, fps=None, container=cont, codec=codec, outdir=d, template="title",
                     cookies="none", embed_meta=True), **kw)


def wait_until(cond, timeout, step=100):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, step)
        if cond():
            return True
        time.sleep(step / 1000)
    return False


def ffmpeg_children(qm):
    """FFmpeg processes belonging to each running worker (pid -> [ffmpeg pids])."""
    out = {}
    try:
        txt = subprocess.run(["wmic", "process", "get", "ProcessId,ParentProcessId,Name", "/format:csv"],
                             capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return out
    rows = [r.split(",") for r in txt.splitlines() if r.count(",") >= 3]
    for iid, w in qm.workers.items():
        pid = w["proc"].pid
        out[iid] = [int(r[3]) for r in rows if r[2].lower() == "ffmpeg.exe" and r[1].strip() == str(pid)]
    return out


def new_qm(parallel=2):
    s = FakeSettings(parallel=parallel)
    qm = QueueManager(s)
    return qm, s


# ---------------------------------------------------------------- QU-PAR: 2 at a time, all complete
if want("QU-PAR"):
    d = os.path.join(OUT, "QU-PAR")
    qm, _ = new_qm(2)
    peak = {"n": 0}
    qm.summary_changed.connect(lambda: peak.__setitem__("n", max(peak["n"], qm.counts()["running"])))
    ids = [qm.add(TD2, spec_audio(d, "mp3")), qm.add(TD3, spec_audio(d, "opus", 96)),
           qm.add(TD2, spec_av(d, 240, "mkv", "auto")), qm.add(TD3, spec_av(d, 360, "mp4", "h264"))]
    t0 = time.time()
    ok = wait_until(lambda: qm.counts()["active"] == 0, 300)
    st = [qm.item(i)["status"] for i in ids]
    files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(d, "*")))
    titles = [qm.item(i)["title"] for i in ids]
    good = ok and st == ["done"] * 4 and peak["n"] == 2 and len(files) == 4
    rec(case="QU-PAR", status="Pass" if good else "Fail",
        actual=f"4 items, parallel 2: statuses {st}; most running at once {peak['n']}; {round(time.time()-t0)}s; "
               f"titles {titles}; files {files}")
    qm.shutdown()

# ---------------------------------------------------------------- QU-CANCEL: cancelling one leaves the other running
if want("QU-CANCEL"):
    d = os.path.join(OUT, "QU-CANCEL")
    qm, _ = new_qm(2)
    a = qm.add(TD1, spec_av(d, 1080, "mp4", "h264"))
    b = qm.add(TD1, spec_av(os.path.join(d, "other"), 720, "mkv", "vp9"))
    wait_until(lambda: qm.item(a)["status"] == "downloading" and qm.item(b)["status"] == "downloading"
               and qm.item(a)["pct"] > 5 and qm.item(b)["pct"] > 5, 120)
    b_pct_before = qm.item(b)["pct"]
    qm.cancel(a)
    wait_until(lambda: qm.item(a)["status"] == "cancelled", 60)
    time.sleep(1)
    app.processEvents()
    b_alive = qm.item(b)["status"] == "downloading"
    wait_until(lambda: qm.item(b)["pct"] > b_pct_before + 3, 60)
    b_progress = qm.item(b)["pct"] > b_pct_before
    left_a = [os.path.basename(f) for f in glob.glob(os.path.join(d, "*")) if os.path.isfile(f)]
    ok_b = wait_until(lambda: qm.item(b)["status"] in ("done", "failed"), 400)
    good = (qm.item(a)["status"] == "cancelled" and not left_a and b_alive and b_progress
            and qm.item(b)["status"] == "done")
    rec(case="QU-CANCEL", status="Pass" if good else "Fail",
        actual=f"cancelled item A: {qm.item(a)['status']} ({qm.item(a)['detail']}), files left {left_a}; "
               f"item B kept running: {b_alive}, progressed {b_pct_before:.0f}% -> later, finished: {qm.item(b)['status']}")
    qm.shutdown()

# ---------------------------------------------------------------- QU-PAUSE: pause keeps partial file, resume continues
if want("QU-PAUSE"):
    d = os.path.join(OUT, "QU-PAUSE")
    qm, _ = new_qm(1)
    a = qm.add(TD1, spec_av(d, 720, "mp4", "h264"))
    wait_until(lambda: qm.item(a)["pct"] > 15, 180)
    qm.pause_all()
    wait_until(lambda: qm.item(a)["status"] == "paused", 60)
    parts = [os.path.basename(p) for p in glob.glob(os.path.join(d, "*.part"))]
    part_size = sum(os.path.getsize(p) for p in glob.glob(os.path.join(d, "*.part")))
    no_worker = len(qm.workers) == 0
    time.sleep(2)
    qm.resume_all()
    first_pct = {"v": None}

    def seen_pct():
        p = qm.item(a)["pct"]
        if first_pct["v"] is None and qm.item(a)["status"] == "downloading" and p and p > 0:
            first_pct["v"] = p
        return qm.item(a)["status"] in ("done", "failed")
    wait_until(seen_pct, 400)
    files = [os.path.basename(f) for f in glob.glob(os.path.join(d, "*")) if os.path.isfile(f)]
    good = (bool(parts) and part_size > 1_000_000 and no_worker and qm.item(a)["status"] == "done"
            and first_pct["v"] is not None and first_pct["v"] > 10 and len(files) == 1 and files[0].endswith(".mp4"))
    rec(case="QU-PAUSE", status="Pass" if good else "Fail",
        actual=f"paused: partial files {parts} ({part_size/1048576:.1f} MB), worker stopped {no_worker}; "
               f"resumed at {first_pct['v']}% (not 0%); final {qm.item(a)['status']}; files {files}")
    qm.shutdown()

# ---------------------------------------------------------------- QU-PERSIST: queue survives a restart
if want("QU-PERSIST"):
    d = os.path.join(OUT, "QU-PERSIST")
    qm, s = new_qm(1)
    a = qm.add(TD1, spec_av(d, 480, "mp4", "h264"))
    b = qm.add(TD2, spec_audio(d, "mp3"))
    wait_until(lambda: qm.item(a)["pct"] > 10, 180)
    qm.shutdown()           # what happens when the window closes
    qm.deleteLater()
    app.processEvents()
    qm2, _ = new_qm(1)
    unfinished = qm2.load()
    st_loaded = [qm2.item(a)["status"], qm2.item(b)["status"]] if qm2.item(a) and qm2.item(b) else None
    qm2.resume_all()
    ok = wait_until(lambda: qm2.counts()["active"] == 0, 400)
    st = [qm2.item(a)["status"], qm2.item(b)["status"]]
    files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(d, "*")) if os.path.isfile(f))
    good = unfinished == 2 and st_loaded == ["paused", "paused"] and st == ["done", "done"] and len(files) == 2
    rec(case="QU-PERSIST", status="Pass" if good else "Fail",
        actual=f"after restart: {unfinished} unfinished, statuses {st_loaded}; after Resume: {st}; files {files}")
    qm2.shutdown()

# ---------------------------------------------------------------- QU-CRASH: a worker dying is reported; Retry works
if want("QU-CRASH"):
    d = os.path.join(OUT, "QU-CRASH")
    qm, _ = new_qm(1)
    a = qm.add(TD2, spec_av(d, 240, "mp4", "h264"))
    wait_until(lambda: a in qm.workers and qm.workers[a]["conn"] is not None, 60)
    subprocess.run(["taskkill", "/PID", str(qm.workers[a]["proc"].pid), "/T", "/F"], capture_output=True)
    wait_until(lambda: qm.item(a)["status"] == "failed", 30)
    msg = qm.item(a)["detail"]
    qm.retry(a)
    wait_until(lambda: qm.item(a)["status"] in ("done", "failed"), 120)
    good = "unexpectedly" in msg and qm.item(a)["status"] == "done"
    rec(case="QU-CRASH", status="Pass" if good else "Fail",
        actual=f"worker killed -> '{msg}'; after Retry: {qm.item(a)['status']}")
    qm.shutdown()

# ---------------------------------------------------------------- QU-EXISTS: skip / keep both / replace
if want("QU-EXISTS"):
    d = os.path.join(OUT, "QU-EXISTS")
    qm, _ = new_qm(1)
    a = qm.add(TD2, spec_audio(d, "mp3"))
    wait_until(lambda: qm.item(a)["status"] == "done", 120)
    b = qm.add(TD2, spec_audio(d, "mp3", exists="skip"))
    wait_until(lambda: qm.item(b)["status"] in ("skipped", "done", "failed"), 120)
    c = qm.add(TD2, spec_audio(d, "mp3", exists="keep"))
    wait_until(lambda: qm.item(c)["status"] in ("done", "failed"), 120)
    before = os.path.getmtime(os.path.join(d, "Me at the zoo.mp3"))
    time.sleep(1.5)
    e = qm.add(TD2, spec_audio(d, "mp3", q=320, exists="replace"))
    wait_until(lambda: qm.item(e)["status"] in ("done", "failed"), 120)
    after = os.path.getmtime(os.path.join(d, "Me at the zoo.mp3"))
    files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(d, "*")))
    good = (qm.item(b)["status"] == "skipped" and files == ["Me at the zoo (2).mp3", "Me at the zoo.mp3"]
            and after > before and qm.item(e)["status"] == "done")
    rec(case="QU-EXISTS", status="Pass" if good else "Fail",
        actual=f"skip -> {qm.item(b)['status']}; keep both -> {files}; replace rewrote the file: {after > before}")
    qm.shutdown()

# ---------------------------------------------------------------- QU-PLAYLIST: one item per video, numbered, in a folder
if want("QU-PLAYLIST"):
    from streamgrab.engine import fetch_info
    from streamgrab.utils import safe_folder_name
    d = os.path.join(OUT, "QU-PLAYLIST")
    info = fetch_info(PL, playlist=True)
    entries = [e for e in info.get("entries") or [] if e]
    folder = os.path.join(d, safe_folder_name(info.get("title")))
    qm, _ = new_qm(2)
    ids = []
    for n, e in enumerate(entries, 1):
        url = e.get("url") or f"https://www.youtube.com/watch?v={e['id']}"
        ids.append(qm.add(url, spec_audio(folder, "mp3", 128, name_prefix=f"{n:03d} - "), title=e.get("title"),
                          group=info.get("title")))
    wait_until(lambda: qm.counts()["active"] == 0, 600)
    st = [qm.item(i)["status"] for i in ids]
    files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(folder, "*")))
    good = st == ["done"] * len(ids) and len(files) == len(ids) and all(f[:6] in (f"{i:03d} - " for i in range(1, 99))
                                                                        for f in files)
    rec(case="QU-PLAYLIST", status="Pass" if good else "Fail",
        actual=f"playlist '{info.get('title')}' -> {len(ids)} queue items, statuses {st}; folder {os.path.basename(folder)}: {files}")
    qm.shutdown()

# ---------------------------------------------------------------- QU-NAMES: downloads running at the same time never share a file name
if want("QU-NAMES"):
    d = os.path.join(OUT, "QU-NAMES")
    qm, _ = new_qm(4)
    # 1) the same video twice at once, nothing in the folder yet
    ids = [qm.add(TD2, spec_audio(d, "mp3", exists="keep")) for _ in range(2)]
    wait_until(lambda: all(qm.item(i)["status"] in ("done", "failed") for i in ids), 120)
    first = sorted(os.path.basename(f) for f in glob.glob(os.path.join(d, "*.mp3")))
    # 2) twice more at once, the file now exists ("keep both")
    ids2 = [qm.add(TD2, spec_audio(d, "mp3", exists="keep")) for _ in range(2)]
    wait_until(lambda: all(qm.item(i)["status"] in ("done", "failed") for i in ids2), 120)
    allf = sorted(os.path.basename(f) for f in glob.glob(os.path.join(d, "*")))
    # 3) a paused "keep both" download resumes into the name it chose
    d3 = os.path.join(d, "resume")
    a = qm.add(TD1, spec_av(d3, 720, "mp4", "h264"))
    wait_until(lambda: qm.item(a)["status"] in ("done", "failed"), 400)
    b = qm.add(TD1, spec_av(d3, 720, "mp4", "h264", exists="keep"))
    wait_until(lambda: qm.item(b)["pct"] > 10, 180)
    suffix = (qm.item(b)["spec"] or {}).get("name_suffix")
    qm.pause_all()
    wait_until(lambda: qm.item(b)["status"] == "paused", 60)
    qm.resume_all()
    wait_until(lambda: qm.item(b)["status"] in ("done", "failed"), 400)
    files3 = sorted(os.path.basename(f) for f in glob.glob(os.path.join(d3, "*")))
    good = (len(first) == 2 and len(set(first)) == 2 and len([f for f in allf if f.endswith(".mp3")]) == 4
            and not [f for f in allf if f.endswith((".part", ".lock"))] and suffix == " (2)"
            and len(files3) == 2 and not [f for f in files3 if f.endswith(".part")]
            and qm.item(b)["status"] == "done")
    rec(case="QU-NAMES", status="Pass" if good else "Fail",
        actual=f"same video twice at once -> {first}; twice more -> {allf}; paused keep-both item saved suffix "
               f"{suffix!r}, after resume folder {files3}")
    qm.shutdown()

# ---------------------------------------------------------------- QU-RESTORE: after a restart new downloads still start
if want("QU-RESTORE"):
    d = os.path.join(OUT, "QU-RESTORE")
    qm, s1 = new_qm(2)
    a = qm.add(TD1, spec_av(d, 720, "mp4", "h264"))
    wait_until(lambda: qm.item(a)["pct"] > 5, 180)
    qm.shutdown()
    qm2 = QueueManager(s1)
    n = qm2.load()
    restored = qm2.item(a)["status"] if qm2.item(a) else None
    b = qm2.add(TD2, spec_audio(d, "mp3"))
    started = wait_until(lambda: qm2.item(b)["status"] == "done", 90)
    a_still = qm2.item(a)["status"]
    # Pause all also holds downloads that haven't started yet
    s1["parallel"] = 1
    c1 = qm2.add(TD2, spec_audio(os.path.join(d, "p"), "opus", 96))
    c2 = qm2.add(TD3, spec_audio(os.path.join(d, "p"), "mp3"))
    wait_until(lambda: qm2.item(c1)["status"] in ("starting", "downloading"), 30)
    qm2.pause_all()
    wait_until(lambda: qm2.item(c1)["status"] in ("paused", "done"), 60)
    held = qm2.item(c2)["status"]
    flag = qm2.paused_all
    time.sleep(3)
    app.processEvents()
    held_later = qm2.item(c2)["status"]
    qm2.resume_all()
    wait_until(lambda: all(qm2.item(x)["status"] == "done" for x in (a, c1, c2)), 400)
    fin = [qm2.item(x)["status"] for x in (a, b, c1, c2)]
    good = (n == 1 and restored == "paused" and started and a_still == "paused" and held == "paused"
            and held_later == "paused" and flag and fin == ["done"] * 4)
    rec(case="QU-RESTORE", status="Pass" if good else "Fail",
        actual=f"restored {n} item as {restored}; new download finished without Resume: {started} (restored one stayed "
               f"{a_still}); Pause all with one not started -> {held}, still {held_later} 3 s later, Resume all shown: "
               f"{flag}; after Resume all: {fin}")
    qm2.shutdown()

print("finished", flush=True)
os._exit(0)
