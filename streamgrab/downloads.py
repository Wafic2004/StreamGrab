"""Download queue: runs each item in its own worker process, a few at a time, and remembers the queue
between sessions."""
import os
import json
import time
import uuid
import secrets
import threading
import subprocess

from PySide6.QtCore import QObject, Signal, QTimer

from .utils import data_dir, app_command, app_env, NO_WINDOW

ACTIVE = ("waiting", "starting", "downloading", "paused")
RUNNING = ("starting", "downloading")
FINISHED = ("done", "skipped", "cancelled")
MAX_PARALLEL = 4


def _queue_dir():
    d = os.path.join(data_dir(), "queue")
    os.makedirs(d, exist_ok=True)
    return d


def _json_default(o):
    return str(o)


def _kill_tree(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    else:
        try:
            os.kill(pid, 9)
        except OSError:
            pass


class QueueManager(QObject):
    item_added = Signal(str)
    item_changed = Signal(str)
    item_removed = Signal(str)
    summary_changed = Signal()
    item_finished = Signal(str, bool)       # id, ok
    queue_finished = Signal(int, int)       # done count, failed count (all work finished)
    _incoming = Signal(str, object)         # from connection threads -> main thread

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s = settings
        self.items = []                     # ordered list of dicts
        self.by_id = {}
        self.workers = {}                   # id -> {"proc", "conn", "started", "hello"}
        self.closed = False                 # after shutdown(): nothing new starts, late messages are ignored
        self._session = {"done": 0, "failed": 0}
        self._incoming.connect(self._handle)
        self._key = secrets.token_bytes(24)
        from multiprocessing.connection import Listener
        self._listener = Listener(("127.0.0.1", 0), authkey=self._key)
        threading.Thread(target=self._accept_loop, daemon=True, name="sg-queue-accept").start()
        self._save_timer = QTimer(self, singleShot=True, interval=800, timeout=self.save)
        self._watch = QTimer(self, interval=1000, timeout=self._watchdog)
        self._watch.start()
        # one worker kept ready in the background (yt-dlp already loaded), so a download starts at once
        self._spare = None
        self._spare_fails = 0
        self.use_standby = True
        QTimer.singleShot(3000, self._ensure_spare)

    # ------------------------------------------------------------------ settings
    @property
    def parallel(self):
        try:
            return max(1, min(MAX_PARALLEL, int(self.s.value("parallel", 2))))
        except (TypeError, ValueError):
            return 2

    # ------------------------------------------------------------------ public API
    def add(self, url, spec, title=None, thumb=None, info=None, group=None, duration=None, size=None, desc=None,
            front=False):
        iid = uuid.uuid4().hex[:12]
        info_path = None
        if info is not None:
            info_path = os.path.join(_queue_dir(), f"{iid}.info.json")
            try:
                data = dict(info)
                data.pop("requested_formats", None)
                data.pop("requested_downloads", None)
                with open(info_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, default=_json_default)
            except (OSError, TypeError, ValueError):
                info_path = None
        it = dict(id=iid, url=url, spec=spec, title=title or url, thumb=thumb, group=group, duration=duration,
                  size=size, desc=desc or "", info_path=info_path, status="waiting", pct=0.0,
                  head="Waiting", detail="", msg="", files=[], partials=[], added=time.time(), raw="")
        if front:
            # after the items already running/starting, before the waiting ones
            pos = next((i for i, x in enumerate(self.items) if x["status"] == "waiting"), len(self.items))
            self.items.insert(pos, it)
        else:
            self.items.append(it)
        self.by_id[iid] = it
        self.item_added.emit(iid)
        self._changed_summary()
        self._schedule()
        return iid

    def item(self, iid):
        return self.by_id.get(iid)

    def counts(self):
        c = {"waiting": 0, "running": 0, "paused": 0, "done": 0, "failed": 0, "cancelled": 0, "skipped": 0}
        for it in self.items:
            st = it["status"]
            if st in RUNNING:
                c["running"] += 1
            elif st in c:
                c[st] += 1
        c["active"] = c["waiting"] + c["running"] + c["paused"]
        return c

    def cancel(self, iid):
        it = self.by_id.get(iid)
        if not it:
            return
        if it["status"] in RUNNING and iid in self.workers:
            it["head"], it["detail"] = "Cancelling", "Stopping download and cleaning up…"
            self.item_changed.emit(iid)
            self._send(iid, {"t": "cancel"})
        elif it["status"] in ("waiting", "paused"):
            self._remove_partials(it)
            self._set_final(it, "cancelled", "Cancelled", "Partial files were removed." if it["partials"] else "")

    def retry(self, iid):
        it = self.by_id.get(iid)
        if not it or it["status"] in RUNNING or it["status"] == "waiting":
            return
        it.update(status="waiting", pct=0.0, shown_pct=0.0, head="Waiting", detail="", msg="", raw="")
        self.item_changed.emit(iid)
        self._changed_summary()
        self._schedule()

    def remove(self, iid):
        it = self.by_id.get(iid)
        if not it or it["status"] in RUNNING:
            return
        if it["status"] in ("waiting", "paused"):
            self._remove_partials(it)
        self._drop(it)

    def clear_finished(self):
        for it in [x for x in self.items if x["status"] in FINISHED]:
            self._drop(it)

    @property
    def paused_all(self):
        """Everything left to do is paused (nothing running or waiting) - the button then offers Resume all."""
        c = self.counts()
        return c["paused"] > 0 and c["running"] == 0 and c["waiting"] == 0

    def pause_all(self):
        for it in self.items:
            if it["status"] == "waiting":
                it.update(status="paused", head="Paused", detail="Not started yet.")
                self.item_changed.emit(it["id"])
        for iid, w in list(self.workers.items()):
            it = self.by_id.get(iid)
            if it and it["status"] in RUNNING:
                it["head"], it["detail"] = "Pausing", "Stopping, partial files are kept…"
                self.item_changed.emit(iid)
                self._send(iid, {"t": "pause"})
        self._changed_summary()

    def resume_all(self):
        for it in self.items:
            if it["status"] == "paused":
                it.update(status="waiting", head="Waiting", detail="")
                self.item_changed.emit(it["id"])
        self._changed_summary()
        self._schedule()

    def resume(self, iid):
        """Resume one paused download; the other paused ones stay paused."""
        it = self.by_id.get(iid)
        if not it or it["status"] != "paused" or self.closed:
            return
        it.update(status="waiting", head="Waiting", detail="")
        self.item_changed.emit(iid)
        self._schedule()
        self._changed_summary()

    def failed_ids(self):
        return [x["id"] for x in self.items if x["status"] == "failed"]

    def shutdown(self, timeout=6.0):
        """Pause running downloads (partial files are kept) and save the queue; used when the app closes."""
        self.closed = True
        self._watch.stop()
        sp, self._spare = self._spare, None
        if sp:
            try:
                if sp["conn"] is not None:
                    sp["conn"].close()
            except OSError:
                pass
            if sp["proc"].poll() is None:
                _kill_tree(sp["proc"].pid)
        running = [iid for iid in self.workers if self.by_id.get(iid, {}).get("status") in RUNNING]
        for iid in running:
            self._send(iid, {"t": "pause"})
        end = time.time() + timeout
        while time.time() < end and any(w["proc"].poll() is None for w in self.workers.values()):
            time.sleep(0.1)
        for iid, w in list(self.workers.items()):
            if w["proc"].poll() is None:
                _kill_tree(w["proc"].pid)
        for it in self.items:
            if it["status"] in RUNNING:
                it.update(status="paused", head="Paused", detail="Resumes where it stopped.")
        self.workers.clear()
        self.save()

    # ------------------------------------------------------------------ persistence
    def _path(self):
        return os.path.join(data_dir(), "queue.json")

    def save(self):
        keep = [dict(x) for x in self.items if x["status"] not in ("cancelled",)]
        for x in keep:
            if x["status"] in RUNNING:
                x["status"], x["head"] = "paused", "Paused"
        try:
            tmp = self._path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "items": keep[-500:]}, f, default=_json_default)
            os.replace(tmp, self._path())
        except OSError:
            pass

    def load(self):
        """Restore the saved queue. Returns how many downloads were left unfinished."""
        try:
            with open(self._path(), encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return 0
        unfinished = 0
        for it in data.get("items", []):
            if not it.get("id") or it["id"] in self.by_id:
                continue
            if it.get("status") in RUNNING or it.get("status") == "waiting":
                it.update(status="paused", head="Paused", detail="Resumes where it stopped.")
            if it.get("status") == "paused":
                unfinished += 1
            it.setdefault("partials", [])
            it.setdefault("files", [])
            self.items.append(it)
            self.by_id[it["id"]] = it
            self.item_added.emit(it["id"])
        # restored downloads stay paused until the user resumes them; new downloads start as usual
        self._changed_summary()
        return unfinished

    # ------------------------------------------------------------------ internals
    def _drop(self, it):
        self.items.remove(it)
        self.by_id.pop(it["id"], None)
        for p in (it.get("info_path"),):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass
        self.item_removed.emit(it["id"])
        self._changed_summary()

    def _remove_partials(self, it):
        for p in it.get("partials") or []:
            for path in (p, p + ".part", p + ".ytdl"):
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except OSError:
                    pass

    def _changed_summary(self):
        self.summary_changed.emit()
        self._save_timer.start()

    def _schedule(self):
        if self.closed:
            return
        running = sum(1 for x in self.items if x["status"] in RUNNING)
        for it in self.items:
            if running >= self.parallel:
                break
            if it["status"] == "waiting":
                self._launch(it)
                running += 1

    # ------------------------------------------------------------------ standby worker
    def _ensure_spare(self):
        if self.closed or not self.use_standby or self._spare is not None or self._spare_fails >= 3:
            return
        sid = "__standby__" + uuid.uuid4().hex[:8]
        path = os.path.join(_queue_dir(), f"{sid}.job.json")
        addr = self._listener.address
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(dict(id=sid, standby=True, addr=[addr[0], addr[1]], key=self._key.hex()), f)
            proc = subprocess.Popen(app_command() + ["--worker", path], env=app_env(), creationflags=NO_WINDOW,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            self._spare_fails += 1
            return
        self._spare = {"id": sid, "proc": proc, "conn": None, "ready": False, "started": time.time()}

    def _drop_spare(self, failed=False):
        sp, self._spare = self._spare, None
        if not sp:
            return
        if failed:
            self._spare_fails += 1
        try:
            if sp["conn"] is not None:
                sp["conn"].close()        # the standby worker exits when its connection closes
        except OSError:
            pass
        if sp["proc"].poll() is None:
            QTimer.singleShot(3000, lambda p=sp["proc"]: p.poll() is None and _kill_tree(p.pid))

    def refresh_standby(self):
        """Replace the standby worker (e.g. after an engine update, so new downloads use the new engine)."""
        self._drop_spare()
        QTimer.singleShot(1500, self._ensure_spare)

    def _take_spare(self, job):
        sp = self._spare
        if not sp or not sp["ready"] or sp["conn"] is None or sp["proc"].poll() is not None:
            return None
        try:
            sp["conn"].send({"t": "job", "job": job})
        except (OSError, ValueError):
            self._drop_spare(failed=True)
            return None
        self._spare = None
        QTimer.singleShot(1500, self._ensure_spare)
        return sp

    def _launch(self, it):
        jobfile = os.path.join(_queue_dir(), f"{it['id']}.job.json")
        addr = self._listener.address
        job = dict(id=it["id"], url=it["url"], spec=it["spec"], info_path=it.get("info_path"),
                   addr=[addr[0], addr[1]], key=self._key.hex())
        sp = self._take_spare(job)
        if sp is not None:
            self.workers[it["id"]] = {"proc": sp["proc"], "conn": sp["conn"], "started": time.time(), "exited": None}
            it.update(status="starting", pct=0.0, head="Starting", detail="Preparing download…", msg="")
            self.item_changed.emit(it["id"])
            self._changed_summary()
            return
        with open(jobfile, "w", encoding="utf-8") as f:
            json.dump(job, f, default=_json_default)
        try:
            proc = subprocess.Popen(app_command() + ["--worker", jobfile], env=app_env(), creationflags=NO_WINDOW,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            self._set_final(it, "failed", "Download failed", f"Couldn't start the download ({e}).")
            return
        self.workers[it["id"]] = {"proc": proc, "conn": None, "started": time.time(), "exited": None}
        it.update(status="starting", pct=0.0, head="Starting", detail="Preparing download…", msg="")
        self.item_changed.emit(it["id"])
        self._changed_summary()

    def _send(self, iid, msg):
        w = self.workers.get(iid)
        if not w:
            return
        if w["conn"] is None:
            w["pending"] = msg          # delivered as soon as the worker connects
            return
        try:
            w["conn"].send(msg)
        except (OSError, ValueError):
            pass

    def _accept_loop(self):
        while True:
            try:
                conn = self._listener.accept()
            except Exception:
                time.sleep(0.2)
                continue
            threading.Thread(target=self._reader, args=(conn,), daemon=True, name="sg-queue-conn").start()

    def _reader(self, conn):
        iid = None
        while True:
            try:
                msg = conn.recv()
            except (EOFError, OSError):
                break
            if msg.get("t") == "hello":
                iid = msg.get("id")
                self._incoming.emit("__conn__", {"id": iid, "conn": conn})
                continue
            if iid:
                self._incoming.emit(iid, msg)
            if msg.get("t") == "done":
                break
        if iid:
            self._incoming.emit(iid, {"t": "__closed__"})

    def _handle(self, iid, msg):
        if self.closed:
            return
        if iid == "__conn__" and msg["id"].startswith("__standby__"):
            if self._spare and self._spare["id"] == msg["id"]:
                self._spare["conn"] = msg["conn"]
            else:
                try:
                    msg["conn"].close()     # a standby worker we no longer want
                except OSError:
                    pass
            return
        if iid.startswith("__standby__"):
            if self._spare and self._spare["id"] == iid:
                if msg.get("t") == "ready":
                    self._spare["ready"] = True
                    self._spare_fails = 0
                elif msg.get("t") == "__closed__":
                    self._drop_spare(failed=True)
                    QTimer.singleShot(5000, self._ensure_spare)
            return
        if iid == "__conn__":
            w = self.workers.get(msg["id"])
            if w is not None:
                w["conn"] = msg["conn"]
                if w.get("pending"):
                    self._send(msg["id"], w.pop("pending"))
            return
        it = self.by_id.get(iid)
        if it is None:
            return
        t = msg.get("t")
        if t == "progress":
            if it["status"] == "starting":
                it["status"] = "downloading"
                self._changed_summary()
            if it["head"] in ("Pausing", "Cancelling"):
                return              # keep the "stopping" note and the last real progress
            pct = msg.get("pct", -1)
            it["pct"] = pct
            if pct is not None and pct > 0:
                it["shown_pct"] = pct
            it["head"], it["detail"] = msg.get("head", ""), msg.get("detail", "")
            self.item_changed.emit(iid)
        elif t == "meta":
            for k in ("title", "duration", "size", "desc"):
                if msg.get(k):
                    if k == "title" and it.get("group") and it.get("title") not in (None, it["url"]):
                        continue      # keep the playlist entry title we already have
                    it[k] = msg[k]
            if msg.get("id") and not it.get("thumb"):
                it["thumb"] = f"https://i.ytimg.com/vi/{msg['id']}/mqdefault.jpg"
            if msg.get("name_suffix"):
                it["spec"] = dict(it["spec"], name_suffix=msg["name_suffix"])   # resume into the same file
                self._save_timer.start()
            self.item_changed.emit(iid)
        elif t == "done":
            self._finish(it, msg)
        elif t == "__closed__":
            pass

    def _finish(self, it, msg):
        iid = it["id"]
        self.workers.pop(iid, None)
        ok, text, files = msg.get("ok"), msg.get("msg", ""), msg.get("files") or []
        it["raw"] = msg.get("raw", "")
        if ok and text == "__skipped__":
            it["files"] = files
            self._set_final(it, "skipped", "Already downloaded", "Skipped, the file is already in the folder.")
        elif ok:
            it["files"] = [f for f in files if os.path.exists(f)] or files
            detail = (os.path.basename(it["files"][-1]) if it["files"] else "Saved.") + (f"\n{text}" if text else "")
            it["pct"] = 100.0
            self._set_final(it, "done", "Done", detail)
            if it.get("info_path"):
                try:
                    os.remove(it["info_path"])
                except OSError:
                    pass
                it["info_path"] = None
        elif text == "__paused__":
            it["partials"] = sorted(set((it.get("partials") or []) + files))
            it.update(status="paused", head="Paused", detail="Resumes where it stopped.",
                      pct=it.get("shown_pct", 0.0))
            self.item_changed.emit(iid)
            self._changed_summary()
        elif text == "__cancelled__":
            left = files
            it["pct"] = 0.0
            self._set_final(it, "cancelled", "Cancelled",
                            "Some partial files couldn't be removed." if left else "Partial files were removed.")
        else:
            it["pct"] = 0.0
            self._set_final(it, "failed", "Failed", text or "Download failed.")
        self._schedule()
        self._check_all_done()

    def _set_final(self, it, status, head, detail):
        it.update(status=status, head=head, detail=detail)
        if status == "done":
            self._session["done"] += 1
        elif status == "failed":
            self._session["failed"] += 1
        self.item_changed.emit(it["id"])
        if status in ("done", "failed", "skipped"):
            self.item_finished.emit(it["id"], status != "failed")
        self._changed_summary()

    def _check_all_done(self):
        c = self.counts()
        if c["active"] == 0 and (self._session["done"] or self._session["failed"]):
            self.queue_finished.emit(self._session["done"], self._session["failed"])
            self._session = {"done": 0, "failed": 0}

    def _watchdog(self):
        now = time.time()
        sp = self._spare
        if sp and (sp["proc"].poll() is not None or (not sp["ready"] and now - sp["started"] > 60)):
            self._drop_spare(failed=True)
            QTimer.singleShot(5000, self._ensure_spare)
        for iid, w in list(self.workers.items()):
            it = self.by_id.get(iid)
            code = w["proc"].poll()
            if code is not None:
                if w["exited"] is None:
                    w["exited"] = now        # give the final message a moment to arrive
                elif now - w["exited"] > 2.5 and it and it["status"] in RUNNING:
                    self.workers.pop(iid, None)
                    self._set_final(it, "failed", "Failed", "The download stopped unexpectedly. Press Retry.")
                    self._schedule()
                    self._check_all_done()
            elif w["conn"] is None and now - w["started"] > 90:
                _kill_tree(w["proc"].pid)
                self.workers.pop(iid, None)
                if it:
                    self._set_final(it, "failed", "Failed", "The download didn't start. Press Retry.")
                self._schedule()
