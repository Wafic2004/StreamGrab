import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QCoreApplication, QTimer
from streamgrab.engine import DownloadJob

out = os.path.abspath(sys.argv[1])
os.makedirs(out, exist_ok=True)
app = QCoreApplication(sys.argv)
spec = dict(mode="av", res=1080, fps=60, container="mp4", codec="h264", abr=None, outdir=out, template="title")
job = DownloadJob("https://www.youtube.com/watch?v=aqz-KE-bpKQ", spec, 2)
state = {"cancelled": False}

def prog(p, h, d):
    if p > 3 and not state["cancelled"]:
        state["cancelled"] = True
        print(f"cancelling at {p:.1f}% ({d})", flush=True)
        job.cancel()

def done(ok, msg, files):
    print("done:", ok, msg, files, flush=True)
    print("left in folder:", os.listdir(out), flush=True)
    app.quit()

job.progress.connect(prog)
job.done.connect(done)
job.start()
QTimer.singleShot(150000, app.quit)
app.exec()
