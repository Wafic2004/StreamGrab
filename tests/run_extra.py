"""Extra QA checks: PF-01, SV-07, SV-08, ST-09, CN-02, CN-03.  python tests/run_extra.py OUTROOT"""
import os, sys, json, time, glob, statistics, subprocess, threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer  # noqa
from streamgrab.engine import FetchJob, DownloadJob, ytdlp, build_opts, fetch_info, TEMPLATES  # noqa
from streamgrab.formats import Analysis  # noqa
from run_cases import summarize, human  # noqa

TD1 = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
TD2 = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
TD7 = "https://www.youtube.com/watch?v=68znNzM5kBI"   # title with Hindi script, '#' and '|'

out = os.path.abspath(sys.argv[1])
os.makedirs(out, exist_ok=True)
only = sys.argv[2].split(",") if len(sys.argv) > 2 else None
app = QCoreApplication(sys.argv)
log = open(os.path.join(out, "extra_results.jsonl"), "a", encoding="utf-8")


def rec(**kw):
    log.write(json.dumps(kw, ensure_ascii=False) + "\n")
    log.flush()
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def ffmpeg_children():
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"(Get-CimInstance Win32_Process -Filter \"Name='ffmpeg.exe'\" | Where-Object {{ $_.ParentProcessId -eq {os.getpid()} }}).Count"],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.strip() or 0)
    except ValueError:
        return -1


def run_job(url, spec, info, cancel_when=None):
    """Run a DownloadJob synchronously; cancel_when(head, pp_name) -> bool triggers cancel."""
    est = Analysis(info).estimate(spec)
    job = DownloadJob(url, spec, est["streams"], info=info)
    state = {"heads": [], "pps": [], "done": None, "cancel_at": None}
    orig_pp = job._pp_hook

    def pp_hook(d):
        if d.get("status") == "started":
            state["pps"].append(d.get("postprocessor"))
            if cancel_when and state["cancel_at"] is None and cancel_when(None, d.get("postprocessor")):
                state["cancel_at"] = d.get("postprocessor")
                # this hook runs on the download thread (no Qt event loop) -> use a plain thread timer
                threading.Timer(cancel_when.delay, job.cancel).start()
        return orig_pp(d)
    job._pp_hook = pp_hook

    def prog(p, h, d):
        if h not in state["heads"]:
            state["heads"].append(h)

    loop = QEventLoop()

    def done(ok, msg, files):
        state["done"] = (ok, msg, files)
        loop.quit()
    job.progress.connect(prog)
    job.done.connect(done)
    job.start()
    loop.exec()
    return state


def want(cid):
    return only is None or cid in only


ytdlp()

# ---------------- PF-01 / PF-02: fetch timing
if want("PF-01"):
    times = []
    for i in range(6):
        t = time.time()
        fetch_info(TD1)
        times.append(round(time.time() - t, 2))
    first, warm = times[0], times[1:]
    med = statistics.median(warm)
    rec(case="PF-01", status="Pass" if med <= 3 else "Fail",
        actual=f"Warm fetch times {warm} s, median {med:.2f} s (first after engine load {first:.2f} s)")

# ---------------- SV-07: file-name patterns (no download needed)
if want("SV-07"):
    info = fetch_info(TD2)
    names = {}
    for key in ("title", "title_res", "channel_title", "date_title"):
        spec = dict(mode="av", res=240, fps=30, container="mp4", codec="h264", outdir=out, template=key)
        y = ytdlp()
        with y.YoutubeDL(build_opts(spec)) as ydl:
            p = ydl.process_ie_result(dict(info, formats=[dict(f) for f in info["formats"]]), download=False)
            names[key] = os.path.basename(ydl.prepare_filename(p))
    ok = (names["title"].startswith("Me at the zoo.") and "[240p]" in names["title_res"]
          and names["channel_title"].startswith("jawed - ") and names["date_title"].startswith("2005-04-24 - "))
    rec(case="SV-07", status="Pass" if ok else "Fail", actual=" | ".join(f"{k}: {v}" for k, v in names.items()))

# ---------------- SV-08: special characters in the title -> valid Windows file name
if want("SV-08"):
    info = fetch_info(TD7)
    spec = dict(mode="audio", afmt="mp3", aq=192, outdir=out, template="title")
    y = ytdlp()
    with y.YoutubeDL(build_opts(spec)) as ydl:
        p = ydl.process_ie_result(dict(info, formats=[dict(f) for f in info["formats"]]), download=False)
        fn = ydl.prepare_filename(p)
    base = os.path.basename(fn)
    illegal = [c for c in '<>:"/\\|?*' if c in base]
    created = False
    try:
        with open(fn, "wb"):
            pass
        created = os.path.exists(fn)
    finally:
        if os.path.exists(fn):
            os.remove(fn)
    hindi_kept = any("ऀ" <= ch <= "ॿ" for ch in base)
    ok = not illegal and created and hindi_kept
    rec(case="SV-08", status="Pass" if ok else "Fail",
        actual=f"Title: {info.get('title')!r} -> file name: {base!r}; illegal chars left: {illegal or 'none'}; "
               f"Hindi kept: {hindi_kept}; Windows accepted the name: {created}")

# ---------------- ST-09: embed metadata on/off
if want("ST-09"):
    info = fetch_info(TD2)
    res = {}
    for flag in (False, True):
        d = os.path.join(out, f"ST-09_{'on' if flag else 'off'}")
        spec = dict(mode="av", res=240, fps=30, container="mp4", codec="h264", outdir=d, template="title", embed_meta=flag)
        st = run_job(TD2, spec, info)
        ok_, msg, files = st["done"]
        res[flag] = summarize(files[-1])["title"] if files else f"failed: {msg}"
    ok = (not res[False]) and bool(res[True])
    rec(case="ST-09", status="Pass" if ok else "Fail", actual=f"title tag with setting OFF: {res[False]!r}; ON: {res[True]!r}")

# ---------------- CN-02: cancel while merging
if want("CN-02"):
    info = fetch_info(TD1)
    d = os.path.join(out, "CN-02b")
    spec = dict(mode="av", res=1080, fps=60, container="mp4", codec="h264", outdir=d, template="title")
    cond = lambda h, pp: pp == "Merger"   # noqa
    cond.delay = 0.3
    st = run_job(TD1, spec, info, cancel_when=cond)
    time.sleep(1.5)
    left = [os.path.basename(p) for p in glob.glob(os.path.join(d, "*"))]
    kids = ffmpeg_children()
    ok = st["done"][1] == "__cancelled__" and not left and kids == 0
    rec(case="CN-02", status="Pass" if ok else "Fail",
        actual=f"cancelled during {st['cancel_at']}; result={st['done'][1]!r}; files left: {left or 'none'}; ffmpeg still running: {kids}; steps shown: {st['heads']}")

# ---------------- CN-03: cancel during AVI conversion (+ check the label shown)
if want("CN-03"):
    info = fetch_info(TD1)
    d = os.path.join(out, "CN-03b")
    spec = dict(mode="av", res=360, fps=30, container="avi", codec="h264", outdir=d, template="title")
    cond = lambda h, pp: pp == "VideoConvertor"   # noqa
    cond.delay = 4
    st = run_job(TD1, spec, info, cancel_when=cond)
    time.sleep(1.5)
    left = [os.path.basename(p) for p in glob.glob(os.path.join(d, "*"))]
    kids = ffmpeg_children()
    ok = (st["done"][1] == "__cancelled__" and kids == 0 and not left
          and any(h.startswith("Converting to AVI") for h in st["heads"]))
    rec(case="CN-03", status="Pass" if ok else "Fail",
        actual=f"cancelled during {st['cancel_at']}; result={st['done'][1]!r}; ffmpeg still running: {kids}; "
               f"files left: {left or 'none'}; postprocessors: {st['pps']}; steps shown: {st['heads']}")

# ---------------- SV-09: existing file -> Replace / Keep both
if want("SV-09"):
    from streamgrab.engine import predict_path
    info = fetch_info(TD2)
    d = os.path.join(out, "SV-09")
    base = dict(mode="av", res=240, fps=30, container="mp4", outdir=d, template="title")
    st1 = run_job(TD2, dict(base, codec="av1"), info)
    first = summarize(st1["done"][2][-1])
    spec2 = dict(base, codec="h264")
    target = predict_path(spec2, info)
    exists = bool(target and os.path.exists(target))
    st2 = run_job(TD2, dict(spec2, overwrite=True), info)
    replaced = summarize(st2["done"][2][-1])
    spec3 = dict(base, codec="vp9", name_suffix=" (2)")
    st3 = run_job(TD2, spec3, info)
    both = st3["done"][2][-1] if st3["done"][2] else ""
    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(d, "*")))
    ok = (exists and first["vcodec"] == "av1" and replaced["vcodec"] == "h264"
          and os.path.basename(both) == "Me at the zoo (2).mp4" and summarize(both)["vcodec"] == "vp9"
          and files == ["Me at the zoo (2).mp4", "Me at the zoo.mp4"])
    rec(case="SV-09", status="Pass" if ok else "Fail",
        actual=f"1st: {first['vcodec']}; app detected existing file: {exists} ({os.path.basename(target or '')}); "
               f"Replace -> {replaced['vcodec']}; Keep both -> {os.path.basename(both)} ({summarize(both)['vcodec'] if both else '-'}); folder: {files}")

# ---------------- ER-04: unavailable video message
if want("ER-04"):
    from streamgrab.engine import friendly_error
    try:
        fetch_info("https://www.youtube.com/watch?v=aaaaaaaaaaa")
        msg = "(fetch succeeded?)"
    except Exception as e:
        msg = friendly_error(str(e))
    ok = msg.startswith("This video is unavailable.")
    rec(case="ER-04", status="Pass" if ok else "Fail", actual=f"Message: {msg!r}")

# ---------------- ER-08: links older than 4 h are refreshed automatically
if want("ER-08"):
    info = fetch_info(TD2)
    info["_sg_time"] = time.time() - 5 * 3600          # pretend the app was left open for 5 hours
    for f in info.get("formats") or []:                 # and the old stream links have expired
        if f.get("url"):
            f["url"] = f["url"].replace("expire=", "expire=1").replace("googlevideo.com", "googlevideo.com/expired")
    d = os.path.join(out, "ER-08")
    spec = dict(mode="audio", afmt="mp3", aq=128, outdir=d, template="title")
    est = Analysis(info).estimate(spec)
    job = DownloadJob(TD2, spec, 1, info=info)
    reused = job.info is not None
    st = run_job(TD2, spec, info)
    ok_, msg, files = st["done"]
    ok = (not reused) and ok_ and files and os.path.exists(files[-1])
    rec(case="ER-08", status="Pass" if ok else "Fail",
        actual=f"stale info reused: {reused}; result ok={ok_} {msg!r}; file: {os.path.basename(files[-1]) if files else '-'}")

# ---------------- PF-07: 20 downloads in one session, memory
if want("PF-07"):
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + \
                   [(n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                                                   "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                                                   "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

    k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

    def ws_mb():
        r = subprocess.run(["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {os.getpid()}).WorkingSet64"],
                           capture_output=True, text=True)
        try:
            return round(int(r.stdout.strip()) / 1048576)
        except ValueError:
            return -1

    info = fetch_info(TD2)
    d = os.path.join(out, "PF-07")
    mems, times, fails = [], [], 0
    specs = [dict(mode="audio", afmt="mp3", aq=128), dict(mode="av", res=240, fps=30, container="mp4", codec="h264"),
             dict(mode="video", res=144, fps=30, container="mkv", codec="auto"), dict(mode="audio", afmt="opus", aq=96)]
    for i in range(20):
        spec = dict(specs[i % 4], outdir=os.path.join(d, str(i)), template="title")
        t = time.time()
        st = run_job(TD2, spec, info if i % 2 else fetch_info(TD2))
        times.append(round(time.time() - t, 1))
        fails += 0 if st["done"][0] else 1
        mems.append(ws_mb())
    slow = statistics.mean(times[-5:]) > statistics.mean(times[:5]) * 2
    ok = fails == 0 and max(mems) < 500 and not slow
    rec(case="PF-07", status="Pass" if ok else "Fail",
        actual=f"20 downloads, failures {fails}; memory {mems[0]} -> {mems[-1]} MB (peak {max(mems)} MB); "
               f"time first 5 avg {statistics.mean(times[:5]):.1f}s, last 5 avg {statistics.mean(times[-5:]):.1f}s")

# ---------------- PL-07: playlist with an item that can't be downloaded (age-restricted, no cookies)
if want("PL-07"):
    url = "https://www.youtube.com/watch_videos?video_ids=jNQXAC9IVRw,07FYdnEawAQ,YsKxkP_kGbE"
    info = fetch_info(url, playlist=True)
    n = len([e for e in (info.get("entries") or []) if e])
    d = os.path.join(out, "PL-07")
    spec = dict(mode="audio", afmt="mp3", aq=128, outdir=d, template="title", playlist=True, playlist_folder=False)
    job = DownloadJob(url, spec, 1, info=None)
    loop = QEventLoop(); res = {}
    job.done.connect(lambda ok, msg, files: (res.update(ok=ok, msg=msg, files=files), loop.quit()))
    job.start(); loop.exec()
    got = sorted(os.path.basename(f) for f in res["files"])
    ok = res["ok"] and len(got) == 2 and "skipped" in res["msg"] and "age-restricted" in res["msg"]
    rec(case="PL-07", status="Pass" if ok else "Fail",
        actual=f"playlist of {n}; result ok={res['ok']}; message: {res['msg']!r}; files: {got}")

# ---------------- ER-02: connection drops mid-download, then retry after reconnecting
if want("ER-02"):
    py = sys.executable
    proxy = subprocess.Popen([py, os.path.join(ROOT, "tests", "netsim.py"), "8898"])
    time.sleep(1.5)
    os.environ["HTTPS_PROXY"] = os.environ["HTTP_PROXY"] = "http://127.0.0.1:8898"
    try:
        info = fetch_info(TD1)
        d = os.path.join(out, "ER-02")
        spec = dict(mode="av", res=1080, fps=60, container="mp4", codec="h264", outdir=d, template="title")
        est = Analysis(info).estimate(spec)
        job = DownloadJob(TD1, spec, est["streams"], info=info)
        loop = QEventLoop(); res = {"heads": []}
        job.progress.connect(lambda p, h, dd: h not in res["heads"] and res["heads"].append(h))
        job.done.connect(lambda ok, msg, files: (res.update(ok=ok, msg=msg, files=files), loop.quit()))
        threading.Timer(6, proxy.kill).start()        # pull the plug 6 s into the download
        t0 = time.time(); job.start(); loop.exec(); t_fail = round(time.time() - t0)
        first = dict(ok=res["ok"], msg=res["msg"], files=list(res["files"]))
        proxy = subprocess.Popen([py, os.path.join(ROOT, "tests", "netsim.py"), "8898"])   # reconnect
        time.sleep(1.5)
        st = run_job(TD1, spec, info)
        ok2, msg2, files2 = st["done"]
        final = summarize(files2[-1]) if files2 else None
        ok = (not first["ok"]) and bool(first["msg"]) and ok2 and final and final["height"] == 1080
        rec(case="ER-02", status="Pass" if ok else "Fail",
            actual=f"after the drop: ok={first['ok']} message={first['msg']!r} after {t_fail}s; steps: {res['heads'][-3:]}; "
                   f"retry after reconnect: ok={ok2} -> {human(final) if final else msg2}")
    finally:
        os.environ.pop("HTTPS_PROXY", None); os.environ.pop("HTTP_PROXY", None)
        proxy.kill()

app.quit()
