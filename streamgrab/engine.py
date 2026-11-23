"""Download engine.

yt-dlp runs *inside* the app (imported once and kept warm) instead of launching yt-dlp.exe for every
action. That removes ~6 s of process start-up per call. Fetches first try YouTube's fast "visionos"
client (no JavaScript challenge, ~2 s) and fall back to yt-dlp's default clients if needed. Downloads
reuse the fetched info, so they start immediately instead of asking YouTube again.
"""
import os
import re
import sys
import glob
import json
import time
import hashlib
import threading
import subprocess

from PySide6.QtCore import QObject, Signal

from .utils import find_tool, fmt_bytes, fmt_eta, data_dir
from .formats import AUDIO_FORMAT_LABELS

ENGINE_DIR = os.path.join(data_dir(), "engine")
FAST_ARGS = {"youtube": {"player_client": ["visionos"], "skip": ["hls"]}}
INFO_MAX_AGE = 4 * 3600   # stream URLs expire after ~6 h

VCODEC_SORT = {"h264": "vcodec:h264", "vp9": "vcodec:vp9", "av1": "vcodec:av01"}

TEMPLATES = {
    "title": "%(title)s.%(ext)s",
    "title_res": "%(title)s%(height& [{}p]|)s.%(ext)s",
    "channel_title": "%(channel,uploader|Unknown)s - %(title)s.%(ext)s",
    "date_title": "%(upload_date>%Y-%m-%d|)s - %(title)s.%(ext)s",
}

PP_NAMES = {
    "Merger": "Merging video and audio",
    "ExtractAudio": "Converting audio",
    "VideoConvertor": "Converting video (this can take a while)",
    "VideoRemuxer": "Finalizing container",
    "EmbedThumbnail": "Embedding cover art",
    "Metadata": "Writing metadata",
    "MoveFiles": "Finishing up",
    "FixupM4a": "Finalizing file",
    "FixupM3u8": "Finalizing file",
    "FixupDuplicateMoov": "Finalizing file",
    "ThumbnailsConvertor": "Preparing cover art",
}


# --------------------------------------------------------------------------- engine loading / updates
def _vkey(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "0"))


def _wheel_version(path):
    parts = os.path.basename(path).split("-")
    return parts[1] if len(parts) > 1 else "0"


def _latest_wheel(pkg):
    wheels = glob.glob(os.path.join(ENGINE_DIR, f"{pkg}-*-py3-none-any.whl"))
    return max(wheels, key=lambda p: _vkey(_wheel_version(p)), default=None)


def _dist_version(dist):
    try:
        from importlib.metadata import version
        return version(dist)
    except Exception:
        return "0"


def activate_engine_updates():
    """Call before yt_dlp is imported: prefer a newer yt-dlp downloaded by the in-app updater."""
    for pkg, dist in (("yt_dlp", "yt-dlp"), ("yt_dlp_ejs", "yt-dlp-ejs")):
        whl = _latest_wheel(pkg)
        if whl and _vkey(_wheel_version(whl)) > _vkey(_dist_version(dist)):
            sys.path.insert(0, whl)


_yt = None
_yt_lock = threading.Lock()


def ytdlp():
    global _yt
    with _yt_lock:
        if _yt is None:
            import yt_dlp
            import yt_dlp.utils  # noqa
            _yt = yt_dlp
    return _yt


def engine_version():
    try:
        return ytdlp().version.__version__
    except Exception:
        return "unavailable"


def warm_up():
    """Import yt-dlp and touch FFmpeg in the background so the first fetch is fast."""
    def run():
        try:
            y = ytdlp()
            from yt_dlp.postprocessor.ffmpeg import FFmpegPostProcessor
            with y.YoutubeDL(base_opts()) as ydl:
                FFmpegPostProcessor(ydl).available  # noqa
        except Exception:
            pass
    threading.Thread(target=run, daemon=True, name="sg-warmup").start()


class _Log:
    def __init__(self, on_retry=None):
        self.errors = []
        self.on_retry = on_retry

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        # yt-dlp reports network retries as warnings, e.g. "... Retrying (3/10)..."
        if self.on_retry and "Retrying" in msg:
            m = re.search(r"Retrying[^(]*\((\d+)/(\d+)\)", msg)
            self.on_retry(f"{m.group(1)} of {m.group(2)}" if m else "")

    def error(self, msg):
        self.errors.append(msg)


def base_opts(cookies=None):
    o = dict(quiet=True, no_warnings=True, noprogress=True, logger=_Log())
    ff = find_tool("ffmpeg")
    if ff:
        o["ffmpeg_location"] = os.path.dirname(ff)
    deno = find_tool("deno")
    if deno:
        o["js_runtimes"] = {"deno": {"path": deno}}
    if cookies and cookies != "none":
        o["cookiesfrombrowser"] = (cookies, None, None, None)
    return o


# --------------------------------------------------------------------------- errors / processes
def friendly_error(text):
    t = (text or "").lower()
    rules = [
        ("private video", "This video is private."),
        ("confirm your age", "This video is age-restricted. Turn on 'Use cookies from browser' in Settings while signed in to YouTube."),
        ("not a bot", "YouTube wants to verify you're not a bot. Turn on 'Use cookies from browser' in Settings, then try again."),
        ("members-only", "This video is for channel members only."),
        ("join this channel", "This video is for channel members only."),
        ("premieres in", "This video hasn't premiered yet."),
        ("live event will begin", "This live stream hasn't started yet."),
        ("video unavailable", "This video is unavailable. It may have been removed or blocked in your country."),
        ("video is unavailable", "This video is unavailable. It may have been removed or blocked in your country."),
        ("video is not available", "This video is unavailable. It may have been removed or blocked in your country."),
        ("this video has been removed", "This video has been removed."),
        ("is not a valid url", "That doesn't look like a valid link."),
        ("unsupported url", "That link isn't supported. Paste a YouTube video or playlist link."),
        ("requested format is not available", "The selected quality isn't available for this video. Try another resolution."),
        ("could not copy", "Couldn't read browser cookies. Close the browser completely and try again, or pick another browser in Settings."),
        ("failed to decrypt", "Couldn't read browser cookies. Try Firefox, or close the browser and retry."),
        ("getaddrinfo", "No internet connection. Check your network and try again."),
        ("failed to resolve", "No internet connection. Check your network and try again."),
        ("unable to connect to proxy", "No internet connection. Check your network and try again."),
        ("network is unreachable", "No internet connection. Check your network and try again."),
        ("connection refused", "No internet connection. Check your network and try again."),
        ("no connection could be made", "No internet connection. Check your network and try again."),
        ("actively refused", "No internet connection. Check your network and try again."),
        ("winerror 10060", "The connection timed out. Check your network and try again."),
        ("winerror 10054", "The connection was lost. Check your network and try again."),
        ("name or service not known", "No internet connection. Check your network and try again."),
        ("urlopen error", "Couldn't reach the update server. Check your network and try again."),
        ("connection reset", "The connection was lost. Check your network and try again."),
        ("connection aborted", "The connection was lost. Check your network and try again."),
        ("remote end closed", "The connection was lost. Check your network and try again."),
        ("incompleteread", "The connection was lost. Check your network and try again."),
        ("connection broken", "The connection was lost. Check your network and try again."),
        ("timed out", "The connection timed out. Check your network and try again."),
        ("http error 403", "YouTube refused the download (HTTP 403). Updating the engine in Settings usually fixes this."),
        ("permission denied", "Can't write to the selected folder. Choose a different save location."),
        ("no space left", "Your disk is full. Free up some space or pick another drive."),
        ("ffmpeg", "FFmpeg failed while processing the file."),
    ]
    for needle, msg in rules:
        if needle in t:
            return msg
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    if lines:
        last = lines[-1]
        if last.startswith("ERROR:"):
            last = last[6:].strip()
        if last.startswith("[") and "]" in last:
            last = last.split("]", 1)[1].strip()
        last = re.sub(r"^[\w-]{11}: ", "", last)          # drop yt-dlp's "<video id>: " prefix
        return last[:300]
    return "Something went wrong. Please try again."


def kill_child_tools():
    """Stop FFmpeg / Deno processes started by this app (used when cancelling)."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes as wt

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD),
                    ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    k32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W)]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if not snap or snap == ctypes.c_void_p(-1).value:
        return
    me, kids = os.getpid(), []
    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    ok = k32.Process32FirstW(snap, ctypes.byref(pe))
    while ok:
        if pe.th32ParentProcessID == me and pe.szExeFile.lower() in ("ffmpeg.exe", "ffprobe.exe", "deno.exe"):
            kids.append(pe.th32ProcessID)
        ok = k32.Process32NextW(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    for pid in kids:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# --------------------------------------------------------------------------- fetching
def fetch_info(url, playlist=False, cookies=None):
    y = ytdlp()
    opts = base_opts(cookies)
    if playlist:
        opts.update(extract_flat="in_playlist", noplaylist=False)
        with y.YoutubeDL(opts) as ydl:
            return ydl.sanitize_info(ydl.extract_info(url, download=False))

    opts["noplaylist"] = True
    attempts = [FAST_ARGS, None] if not cookies or cookies == "none" else [None]
    last_err, info = None, None
    for ea in attempts:
        o = dict(opts, logger=_Log())
        if ea:
            o["extractor_args"] = ea
        try:
            with y.YoutubeDL(o) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:  # fast client failed, try the full one
            last_err = e
            continue
        if any(f.get("vcodec") not in (None, "none") for f in info.get("formats") or []):
            info["_sg_fast"] = bool(ea)
            info["_sg_time"] = time.time()
            return info
    if info is not None:
        info["_sg_time"] = time.time()
        return info
    raise last_err or RuntimeError("Couldn't read this video.")


class FetchJob(QObject):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, url, playlist=False, cookies=None, parent=None):
        super().__init__(parent)
        self.url, self.playlist, self.cookies = url, playlist, cookies
        self._aborted = False

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="sg-fetch").start()

    def abort(self):
        self._aborted = True

    def _run(self):
        try:
            info = fetch_info(self.url, self.playlist, self.cookies)
            if not self._aborted:
                self.done.emit(info)
        except Exception as e:
            if not self._aborted:
                self.failed.emit(friendly_error(str(e)))


# --------------------------------------------------------------------------- downloading
def common_args(cookies_browser=None):
    a = []
    ff = find_tool("ffmpeg")
    if ff:
        a += ["--ffmpeg-location", os.path.dirname(ff)]
    deno = find_tool("deno")
    if deno:
        a += ["--js-runtimes", f"deno:{deno}"]
    if cookies_browser and cookies_browser != "none":
        a += ["--cookies-from-browser", cookies_browser]
    return a


def build_download_args(spec):
    """yt-dlp command-line options for a download spec (converted to API options by build_opts)."""
    a = common_args(spec.get("cookies"))
    a += ["--no-mtime", "--concurrent-fragments", "4"]
    tmpl = TEMPLATES.get(spec.get("template"), TEMPLATES["title"])
    if spec.get("playlist"):
        a += ["--yes-playlist", "--ignore-errors"]
        prefix = "%(playlist_index|0)03d - "
        if spec.get("playlist_folder", True):
            prefix = "%(playlist_title,playlist_id|Playlist)s/" + prefix
        tmpl = prefix + tmpl
    else:
        a.append("--no-playlist")
    if spec.get("name_suffix"):
        tmpl = tmpl.replace(".%(ext)s", spec["name_suffix"].replace("%", "%%") + ".%(ext)s")
    if spec.get("overwrite"):
        a.append("--force-overwrites")
    a += ["-P", spec["outdir"], "-o", tmpl]

    mode = spec["mode"]
    if mode in ("av", "video"):
        cont, codec = spec["container"], spec["codec"]
        sort = []
        if spec.get("res"):
            sort.append(f"res:{spec['res']}")
        if spec.get("fps"):
            sort.append(f"fps:{spec['fps']}")
        if codec in VCODEC_SORT:
            sort.append(VCODEC_SORT[codec])
        if cont in ("mp4", "mov"):
            sort += ["vext:mp4", "aext:m4a"]
        if mode == "av":
            sort.append("channels:2")
            if spec.get("abr"):
                sort.append(f"abr:{spec['abr']}")
        if sort:
            a += ["-S", ",".join(sort)]
        if mode == "av":
            fmt = "bv*[ext=webm]+ba[ext=webm]/bv*+ba/b" if cont == "webm" else "bv*+ba/b"
            merge = {"mp4": "mp4", "mkv": "mkv", "webm": "webm/mkv", "mov": "mov", "avi": "mkv"}[cont]
            a += ["-f", fmt, "--merge-output-format", merge]
        else:
            fmt = "bv[ext=webm]/bv/bv*" if cont == "webm" else "bv/bv*"
            a += ["-f", fmt]
            if cont in ("mp4", "mkv", "mov"):
                a += ["--remux-video", cont]
        if cont == "avi":
            a += ["--recode-video", "avi"]
        if spec.get("embed_meta", True):
            a.append("--embed-metadata")
    else:
        fmt, q = spec["afmt"], spec.get("aq") or 0
        a += ["-f", "ba/b"]
        aext = {"m4a": "aext:m4a", "aac": "aext:m4a", "opus": "aext:webm", "vorbis": "aext:webm"}.get(fmt)
        if q and fmt in ("m4a", "aac", "opus"):
            # yt-dlp copies the stream (ignoring the bitrate) when the source already has the target codec,
            # so start from the other codec to get a real encode at the chosen bitrate.
            aext = "aext:webm" if fmt in ("m4a", "aac") else "aext:m4a"
        a += ["-S", "channels:2" + (f",{aext}" if aext else "")]
        a.append("-x")
        if fmt != "original":
            a += ["--audio-format", fmt, "--audio-quality", f"{q}K" if q else "0"]
        if spec.get("embed_cover", True):
            a.append("--embed-metadata")
            if fmt != "wav":
                a.append("--embed-thumbnail")
    return a


def final_ext(spec):
    if spec["mode"] in ("av", "video"):
        return spec.get("container") or "mp4"
    return {"aac": "m4a", "vorbis": "ogg"}.get(spec.get("afmt"), spec.get("afmt"))


def predict_path(spec, info):
    """Full path the download will be saved as (single videos only), or None if it can't be worked out."""
    if spec.get("playlist") or not info or spec.get("afmt") == "original":
        return None
    try:
        tmpl = TEMPLATES.get(spec.get("template"), TEMPLATES["title"])
        if spec.get("name_suffix"):
            tmpl = tmpl.replace(".%(ext)s", spec["name_suffix"].replace("%", "%%") + ".%(ext)s")
        y = ytdlp()
        with y.YoutubeDL({"quiet": True, "paths": {"home": spec["outdir"]}, "outtmpl": {"default": tmpl},
                          "logger": _Log()}) as ydl:
            d = dict(info)
            r = spec.get("res")
            if r and spec["mode"] != "audio":
                d["height"] = r
            name = ydl.prepare_filename(d)
        return os.path.splitext(name)[0] + "." + final_ext(spec)
    except Exception:
        return None


def build_opts(spec):
    return ytdlp().parse_options(build_download_args(spec)).ydl_opts


class DownloadJob(QObject):
    progress = Signal(float, str, str)   # percent (or -1 = busy), headline, detail
    done = Signal(bool, str, list)        # ok, message, files

    def __init__(self, url, spec, expected_streams=1, info=None, parent=None):
        super().__init__(parent)
        self.url, self.spec = url, spec
        self.mode = spec["mode"]
        self.playlist = bool(spec.get("playlist"))
        self.expected = max(1, expected_streams)
        self.info = info if (info and not self.playlist and time.time() - info.get("_sg_time", 0) < INFO_MAX_AGE) else None
        self.cancelled = False
        self.files, self.seen = [], []
        self._before = {}      # folder -> file names that existed before this job wrote there
        self.cur_item, self.n_items = 1, 0
        self.last_pct, self._last_emit = 0.0, 0.0
        cont = spec.get("container")
        self.convert_text = f"Converting to {(cont or 'video').upper()} (this can take a while)"
        if self.mode == "av":
            self.finish_text = "Merging video and audio"
        elif self.mode == "audio" and spec.get("afmt") not in (None, "original"):
            self.finish_text = f"Converting to {AUDIO_FORMAT_LABELS.get(spec['afmt'], spec['afmt'].upper())}"
        elif spec.get("container") == "avi":
            self.finish_text = "Converting to AVI (this can take a while)"
        else:
            self.finish_text = "Finishing up"

    def start(self):
        self.progress.emit(-1, "Preparing download", "Starting…")
        threading.Thread(target=self._run, daemon=True, name="sg-download").start()

    def cancel(self):
        if self.cancelled:
            return
        self.cancelled = True
        self.progress.emit(-1, "Cancelling", "Stopping download and cleaning up…")
        threading.Thread(target=kill_child_tools, daemon=True).start()

    # ---- worker thread
    def _run(self):
        y = ytdlp()
        try:
            opts = build_opts(self.spec)
            try:
                self._download(y, opts, reuse=self.info is not None)
            except y.utils.DownloadCancelled:
                raise
            except Exception as e:
                msg = str(e).lower()
                if self.info is None or self.cancelled or "no space" in msg or "permission denied" in msg:
                    raise
                # cached stream links were refused/expired: ask YouTube again with the full client set
                self.seen = []
                self.progress.emit(-1, "Preparing download", "Refreshing video links…")
                self._download(y, opts, reuse=False)
            if self.cancelled:
                raise y.utils.DownloadCancelled()
            note = ""
            skipped = getattr(self, "skipped", [])
            if skipped:
                n = len(skipped)
                note = (f"{n} video{'s were' if n > 1 else ' was'} skipped: "
                        f"{friendly_error(skipped[-1])}")
            self.done.emit(True, note, self.files)
        except Exception as e:
            if self.cancelled or isinstance(e, y.utils.DownloadCancelled):
                time.sleep(0.5)
                self._cleanup()
                self.done.emit(False, "__cancelled__", list(getattr(self, "left_over", [])))
            elif self.files:
                self.done.emit(True, f"Some videos were skipped: {friendly_error(str(e))}", self.files)
            else:
                self.done.emit(False, friendly_error(str(e)), [])

    def _download(self, y, opts, reuse):
        from yt_dlp.postprocessor.common import PostProcessor
        job = self

        class Recorder(PostProcessor):
            def run(self, info):
                fp = info.get("filepath")
                if fp and fp not in job.files:
                    job.files.append(fp)
                return [], info

        log = _Log(on_retry=self._retrying)
        o = dict(opts, quiet=True, noprogress=True, logger=log,
                 progress_hooks=[self._hook], postprocessor_hooks=[self._pp_hook])
        with y.YoutubeDL(o) as ydl:
            ydl.add_post_processor(Recorder(), when="after_move")
            if reuse:
                info = dict(self.info)
                info["formats"] = [dict(f) for f in self.info.get("formats") or []]
                for k in ("requested_formats", "requested_downloads", "_sg_fast", "_sg_time"):
                    info.pop(k, None)
                ydl.process_ie_result(info, download=True)
                code = 1 if log.errors else 0
            else:
                code = ydl.download([self.url])
            # yt-dlp's default "keep going on download errors" only logs a failed download; never report it
            # as finished. (A playlist with some files saved is handled by the caller as a partial success.)
            if (code or log.errors) and not self.files:
                raise y.utils.DownloadError(log.errors[-1] if log.errors else "Download failed")
            self.skipped = list(log.errors)

    def _hook(self, d):
        if self.cancelled:
            raise ytdlp().utils.DownloadCancelled()
        status = d.get("status")
        if status not in ("downloading", "finished"):
            return
        now = time.time()
        if status == "downloading" and now - self._last_emit < 0.12:
            return
        self._last_emit = now
        info = d.get("info_dict") or {}
        down, total = d.get("downloaded_bytes"), d.get("total_bytes") or d.get("total_bytes_estimate")
        spd, eta = d.get("speed"), d.get("eta")
        pidx = int(info.get("playlist_index") or 1)
        n = int(info.get("n_entries") or 0)
        if n:
            self.n_items = n
        if self.playlist and pidx != self.cur_item:
            self.cur_item, self.seen = pidx, []
        key = d.get("tmpfilename") or d.get("filename") or ""
        if key.endswith(".part"):
            key = key[:-5]
        if key and key not in self.seen:
            self._snapshot(os.path.dirname(key))
            self.seen.append(key)
        idx = max(1, len(self.seen))
        steps = max(self.expected, idx)
        frac = 1.0 if status == "finished" else ((down / total) if (down and total) else 0.0)
        item = ((min(idx, steps) - 1) + min(frac, 1.0)) / steps * 0.95

        if status == "finished" and idx >= steps:
            self._emit_item(0.96, self.finish_text, "Almost done…")
            return
        if self.mode == "av" and steps > 1:
            kind = "video stream" if idx == 1 else "audio stream"   # yt-dlp fetches video first, then audio
        elif self.mode == "av":
            kind = "video"
        else:
            kind = "audio" if self.mode == "audio" else "video"
        head = f"Downloading {kind}" + (f"  ({min(idx, steps)} of {steps})" if steps > 1 else "")
        parts = []
        if total:
            parts.append(f"{fmt_bytes(down)} of {fmt_bytes(total)}")
        elif down:
            parts.append(fmt_bytes(down))
        if spd:
            parts.append(f"{fmt_bytes(spd)}/s")
        if eta is not None and status != "finished":
            parts.append(f"{fmt_eta(eta)} left")
        self._emit_item(item, head, "   •   ".join(parts))

    def _pp_hook(self, d):
        if self.cancelled:
            raise ytdlp().utils.DownloadCancelled()
        if d.get("status") == "started":
            name = d.get("postprocessor") or ""
            if name == "VideoConvertor":
                self._emit_item(0.965, self.convert_text, "Almost done…")
            elif name in ("ExtractAudio", "Merger"):
                self._emit_item(0.96, self.finish_text, "Almost done…")
            elif name in PP_NAMES:
                self._emit_item(0.97, PP_NAMES[name], "Almost done…")

    def _retrying(self, which):
        if self.cancelled:
            return
        self.progress.emit(self.last_pct if self.last_pct > 0 else -1, "Connection problem, retrying",
                           f"Attempt {which}…" if which else "Trying again…")

    def _emit_item(self, item, head, detail):
        if self.playlist and self.n_items:
            overall = ((self.cur_item - 1) + item) / self.n_items
            head = f"Video {self.cur_item} of {self.n_items}   ·   {head}"
            pct = overall * 100
        else:
            pct = max(self.last_pct, item * 100)
        self.last_pct = pct
        self.progress.emit(pct, head, detail)

    def _snapshot(self, folder):
        folder = os.path.abspath(folder or ".")
        if folder not in self._before:
            try:
                names = set(os.listdir(folder))
            except OSError:
                names = set()
            # the stream that just started is ours, not pre-existing
            self._before[folder] = {n for n in names if not n.endswith((".part", ".ytdl"))}

    @staticmethod
    def _stem(key):
        """'Title.f137.mp4' -> 'Title'; 'Title.mp4' -> 'Title'."""
        base = os.path.basename(key)
        base = re.sub(r"\.f[\w-]+\.\w+$", "", base)
        return os.path.splitext(base)[0] if base == os.path.basename(key) else base

    def _cleanup(self):
        """Remove everything this job created: stream parts, merge/convert temp files and half-written outputs."""
        self.left_over = []
        targets = set()
        for key in self.seen:
            folder = os.path.abspath(os.path.dirname(key) or ".")
            before = self._before.get(folder, set())
            stem = self._stem(key)
            for path in glob.glob(os.path.join(glob.escape(folder), glob.escape(stem) + ".*")):
                if os.path.basename(path) in before or path in self.files:
                    continue
                targets.add(path)
        for path in sorted(targets):
            for attempt in range(10):       # FFmpeg may still hold the file for a moment after being stopped
                try:
                    os.remove(path)
                    break
                except FileNotFoundError:
                    break
                except OSError:
                    time.sleep(0.3)
            else:
                self.left_over.append(path)
        # a playlist folder we created and left empty
        for folder in self._before:
            try:
                if not os.listdir(folder) and os.path.abspath(folder) != os.path.abspath(self.spec["outdir"]):
                    os.rmdir(folder)
            except OSError:
                pass


# --------------------------------------------------------------------------- updates
class EngineUpdater(QObject):
    """Downloads the newest yt-dlp (+ its JS solver) from PyPI. Takes effect after a restart."""
    finished = Signal(bool, str)

    def start(self):
        threading.Thread(target=self._run, daemon=True, name="sg-update").start()

    def _run(self):
        import urllib.request
        try:
            current = {"yt-dlp": engine_version(), "yt-dlp-ejs": _dist_version("yt-dlp-ejs")}
            try:
                import yt_dlp_ejs
                current["yt-dlp-ejs"] = getattr(yt_dlp_ejs, "__version__", current["yt-dlp-ejs"])
            except Exception:
                pass
            os.makedirs(ENGINE_DIR, exist_ok=True)
            updated = []
            for dist, pkg in (("yt-dlp", "yt_dlp"), ("yt-dlp-ejs", "yt_dlp_ejs")):
                with urllib.request.urlopen(f"https://pypi.org/pypi/{dist}/json", timeout=20) as r:
                    data = json.load(r)
                latest = data["info"]["version"]
                have = _latest_wheel(pkg)
                have_v = max(current[dist], _wheel_version(have) if have else "0", key=_vkey)
                if _vkey(latest) <= _vkey(have_v):
                    continue
                wheel = next(u for u in data["urls"]
                             if u["packagetype"] == "bdist_wheel" and u["filename"].endswith("py3-none-any.whl"))
                dest = os.path.join(ENGINE_DIR, wheel["filename"])
                with urllib.request.urlopen(wheel["url"], timeout=60) as r:
                    blob = r.read()
                if hashlib.sha256(blob).hexdigest() != wheel["digests"]["sha256"]:
                    raise RuntimeError("Download was corrupted, please try again.")
                with open(dest + ".part", "wb") as f:
                    f.write(blob)
                os.replace(dest + ".part", dest)
                for old in glob.glob(os.path.join(ENGINE_DIR, f"{pkg}-*.whl")):
                    if old != dest:
                        try:
                            os.remove(old)
                        except OSError:
                            pass
                updated.append(f"{dist} {latest}")
            if updated:
                self.finished.emit(True, f"Downloaded {', '.join(updated)}. Restart StreamGrab to use it.")
            else:
                self.finished.emit(True, f"You're up to date (yt-dlp {current['yt-dlp']}).")
        except Exception as e:
            self.finished.emit(False, f"Update failed: {friendly_error(str(e))}")
