"""Download worker process.

Every queued download runs in its own StreamGrab process started with ``--worker <job.json>``. That keeps
downloads independent: cancelling one stops only its own FFmpeg, a crash can't take the window or other
downloads down, and each new worker loads the newest download engine.

The worker talks to the window over a local connection (multiprocessing.connection, authenticated with a
random key from the job file). Messages are small dicts:
    worker -> window: hello, progress, meta, done
    window -> worker: cancel, pause
"""
import os
import sys
import json
import time
import threading
import traceback


def _log(msg):
    try:
        from .utils import data_dir
        d = os.path.join(data_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "worker.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + f"[{os.getpid()}] {msg}\n")
    except OSError:
        pass


T0 = time.time()


def _t(label):
    if os.environ.get("SG_WORKER_TIMING"):
        _log(f"{label}: {time.time() - T0:.2f}s")


def run_worker(job_path):
    _t("start")
    from .engine import activate_engine_updates, ACTIVE_WHEELS
    activate_engine_updates()
    if ACTIVE_WHEELS:
        _log("using updated engine: " + ", ".join(os.path.basename(w) for w in ACTIVE_WHEELS.values()))

    with open(job_path, encoding="utf-8") as f:
        job = json.load(f)
    from multiprocessing.connection import Client
    conn = Client(tuple(job["addr"]), authkey=bytes.fromhex(job["key"]))
    lock = threading.Lock()
    finished = threading.Event()

    def send(msg):
        with lock:
            if msg.get("t") == "done":
                if finished.is_set():
                    return            # only one final answer per job
                finished.set()
            try:
                conn.send(msg)
            except (OSError, EOFError, ValueError):
                pass

    _t("connected")
    send({"t": "hello", "id": job["id"], "pid": os.getpid()})
    if job.get("standby"):
        # Standby worker: load everything now, then wait for the window to hand over a download, so it
        # starts without the ~2 s of starting a process and loading yt-dlp.
        from .engine import ytdlp, DownloadJob, fetch_info, predict_path  # noqa: F401
        from .formats import Analysis  # noqa: F401
        ytdlp()
        _t("standby ready")
        send({"t": "ready"})
        try:
            msg = conn.recv()
        except (OSError, EOFError):
            msg = {}
        if msg.get("t") != "job":
            try:
                conn.close()
            except OSError:
                pass
            try:
                os.remove(job_path)
            except OSError:
                pass
            return 0
        global T0
        T0 = time.time()
        _t("got job")
        job = dict(msg["job"], addr=job["addr"], key=job["key"])
        send({"t": "hello", "id": job["id"], "pid": os.getpid()})
    state = {"dj": None, "stop": None}

    def listen():
        # commands from the window; if the window goes away, pause (keep partial files) and quit
        while not finished.is_set():
            try:
                if not conn.poll(0.3):
                    continue
                cmd = conn.recv()
            except (OSError, EOFError):
                cmd = {"t": "pause"}
            t = cmd.get("t")
            if t not in ("cancel", "pause"):
                continue
            state["stop"] = t
            dj = state["dj"]
            if dj is not None:
                dj.cancel(keep_partial=(t == "pause"))
            else:   # nothing downloading yet: just stop
                send({"t": "done", "ok": False, "msg": "__paused__" if t == "pause" else "__cancelled__",
                      "files": [], "raw": ""})

    threading.Thread(target=listen, daemon=True).start()

    try:
        _work(job, send, state, finished)
    except Exception as e:
        _log("worker crashed: " + traceback.format_exc())
        from .engine import friendly_error
        send({"t": "done", "ok": False, "msg": friendly_error(str(e)), "files": [], "raw": str(e)})
    finished.wait(timeout=24 * 3600)
    time.sleep(0.2)
    try:
        conn.close()
    except OSError:
        pass
    try:
        os.remove(job_path)
    except OSError:
        pass
    return 0


def _work(job, send, state, finished):
    from PySide6.QtCore import Qt
    from .engine import (DownloadJob, fetch_info, friendly_error, predict_path, INFO_MAX_AGE)
    from .formats import Analysis

    _t("imports done")
    url, spec = job["url"], dict(job["spec"])
    info = None
    if job.get("info_path") and os.path.isfile(job["info_path"]):
        try:
            with open(job["info_path"], encoding="utf-8") as f:
                info = json.load(f)
            if time.time() - info.get("_sg_time", 0) >= INFO_MAX_AGE:
                info = None
        except (OSError, ValueError):
            info = None
    if finished.is_set():
        return
    if info is None:
        send({"t": "progress", "pct": -1, "head": "Reading video details", "detail": "Asking YouTube…"})
        try:
            info = fetch_info(url, cookies=spec.get("cookies"))
        except Exception as e:
            send({"t": "done", "ok": False, "msg": friendly_error(str(e)), "files": [], "raw": str(e)})
            return
    if finished.is_set():
        return

    _t("info ready")
    an = Analysis(info)
    est = an.estimate(spec)
    send({"t": "meta", "title": info.get("title"), "id": info.get("id"), "duration": info.get("duration"),
          "size": est.get("size"), "desc": est.get("desc")})

    # file already there? (or being downloaded right now by another queued download)
    target = predict_path(spec, info)
    lock = None
    if target and not spec.get("name_suffix") and not spec.get("overwrite"):
        lock = _reserve(target)
        busy = lock is None                       # the same file is being downloaded right now
        if os.path.exists(target) or busy:
            policy = spec.get("exists", "keep")
            if busy and policy in ("replace", "skip"):
                policy = "keep"                   # never write into a file another download is writing
            if policy == "skip":
                _release(lock)
                send({"t": "done", "ok": True, "msg": "__skipped__", "files": [target], "raw": ""})
                return
            if policy == "replace":
                spec["overwrite"] = True
            else:  # keep both: the first free " (n)" name, reserved so two downloads can't pick the same one
                _release(lock)
                lock, n = None, 2
                while n < 1000:
                    spec["name_suffix"] = f" ({n})"
                    p = predict_path(spec, info)
                    if p and not _name_taken(p):
                        lock = _reserve(p)
                        if lock is not None:
                            break
                    n += 1
                send({"t": "meta", "name_suffix": spec["name_suffix"]})   # saved, so a resume uses the same name
    elif target:
        lock = _reserve(target) or ""             # resuming with a name chosen before

    dj = DownloadJob(url, spec, est.get("streams", 2 if spec["mode"] == "av" else 1), info=info)
    direct = Qt.ConnectionType.DirectConnection
    dj.progress.connect(lambda pct, head, detail: send({"t": "progress", "pct": pct, "head": head, "detail": detail}),
                        direct)
    dj.meta.connect(lambda m: send(dict(m, t="meta")), direct)

    def on_done(ok, msg, files):
        _t(f"done ok={ok}")
        _release(lock)
        send({"t": "done", "ok": ok, "msg": msg, "files": files, "raw": dj.raw_error})

    dj.done.connect(on_done, direct)
    state["dj"] = dj
    if state["stop"]:                      # a cancel/pause arrived while we were preparing
        on_done(False, "__paused__" if state["stop"] == "pause" else "__cancelled__", [])
        return
    _t("download starting")
    dj.start()


def _lock_path(path):
    import hashlib
    from .utils import data_dir
    d = os.path.join(data_dir(), "queue", "names")
    os.makedirs(d, exist_ok=True)
    key = os.path.normcase(os.path.abspath(path)).encode("utf-8", "surrogatepass")
    return os.path.join(d, hashlib.md5(key).hexdigest() + ".lock")


def _reserve(path):
    """Claim a file name while this download runs. Returns the lock file, None if another download holds the
    name, or "" if names can't be reserved (e.g. read-only data folder)."""
    try:
        lock = _lock_path(path)
    except OSError:
        return ""
    for _ in range(2):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return lock
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > 6 * 3600:   # left behind by a crash
                    os.remove(lock)
                    continue
            except OSError:
                pass
            return None
        except OSError:
            return ""
    return None


def _release(lock):
    if lock:
        try:
            os.remove(lock)
        except OSError:
            pass


def _name_taken(path):
    """The file, or partial/temporary files of a download into it, already exist."""
    import glob
    if os.path.exists(path) or os.path.exists(path + ".part"):
        return True
    stem = glob.escape(os.path.splitext(path)[0])
    return bool(glob.glob(stem + ".f*.part") or glob.glob(stem + ".temp.*") or glob.glob(stem + ".f*.*"))


def run_selftest(out_path):
    from .engine import activate_engine_updates
    activate_engine_updates()
    from .engine import engine_selftest
    return engine_selftest(out_path)
