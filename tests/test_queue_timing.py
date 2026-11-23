"""PF-03 for 1.1.0: time from pressing Download to the first progress, through the real queue and worker processes.

usage: python tests/test_queue_timing.py OUTDIR [RUNS]
The window passes the already-fetched video info to the queue (as the app does), so no second fetch is made.
"""
import json
import os
import statistics
import sys
import time

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "qa_runs/pf03")
RUNS = int(sys.argv[2]) if len(sys.argv) > 2 else 8
os.makedirs(OUT, exist_ok=True)
os.environ["LOCALAPPDATA"] = os.path.join(OUT, "_appdata")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QCoreApplication, QEventLoop  # noqa: E402
from streamgrab.downloads import QueueManager  # noqa: E402
from streamgrab.engine import fetch_info  # noqa: E402

app = QCoreApplication([])
TD2 = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


class FakeSettings(dict):
    def value(self, k, default=None, type=None):
        v = self.get(k, default)
        return type(v) if type and v is not None else v

    def setValue(self, k, v):
        self[k] = v


qm = QueueManager(FakeSettings(parallel=1), None)
info = fetch_info(TD2)
times, firsts = [], {}


def changed(iid):
    it = qm.item(iid)
    if iid not in firsts and it and it["status"] == "downloading" and (it.get("pct") or 0) > 0:
        firsts[iid] = time.time()


qm.item_changed.connect(changed)
end = time.time() + 8          # the app starts its standby worker 3 s after launch; let it get ready
while time.time() < end:
    app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    time.sleep(0.02)
print("standby ready:", bool(qm._spare and qm._spare["ready"]), flush=True)
for i in range(RUNS):
    spec = dict(mode="audio", afmt="mp3", aq=128, embed_cover=True, outdir=os.path.join(OUT, f"r{i}"),
                template="title", cookies="none", exists="replace")
    t0 = time.time()
    iid = qm.add(TD2, spec, title=info.get("title"), info=info, duration=info.get("duration"))
    end = time.time() + 60
    while time.time() < end and qm.item(iid)["status"] not in ("done", "failed", "cancelled", "skipped"):
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        time.sleep(0.02)
    pause = time.time() + 4    # a person takes a few seconds to pick the next video
    while time.time() < pause:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
        time.sleep(0.02)
    st = qm.item(iid)["status"]
    if iid in firsts:
        times.append(firsts[iid] - t0)
    print(json.dumps({"run": i + 1, "status": st, "first_progress_s": round(firsts.get(iid, 0) - t0, 2)}), flush=True)
qm.shutdown()
res = {"case": "PF-03", "runs": len(times), "min": round(min(times), 2), "median": round(statistics.median(times), 2),
       "max": round(max(times), 2), "status": "Pass" if times and max(times) <= 3.0 else "Fail"}
print(json.dumps(res), flush=True)
with open(os.path.join(OUT, "pf03.json"), "w") as f:
    json.dump(res, f)
