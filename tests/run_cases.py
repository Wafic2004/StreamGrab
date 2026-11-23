"""StreamGrab QA runner: executes download-mode test cases through the app's engine and verifies output with ffprobe.

Usage:  python tests/run_cases.py OUTROOT CASE_ID[,CASE_ID...]
Writes one JSON line per case to OUTROOT/results.jsonl
"""
import os, sys, json, time, glob, subprocess
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from PySide6.QtCore import QCoreApplication, QTimer  # noqa
from streamgrab.engine import FetchJob, DownloadJob, ytdlp, activate_engine_updates  # noqa
from streamgrab.formats import Analysis  # noqa

FFPROBE = os.path.join(ROOT, "bin", "ffprobe.exe")
TD1 = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
TD2 = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


def probe(path):
    out = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    try:
        return json.loads(out)
    except Exception:
        return {}


def summarize(path):
    d = probe(path)
    st = d.get("streams", [])
    v = [s for s in st if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
    a = [s for s in st if s.get("codec_type") == "audio"]
    pic = [s for s in st if s.get("disposition", {}).get("attached_pic")]
    fmt = d.get("format", {})
    tags = {k.lower(): v_ for k, v_ in (fmt.get("tags") or {}).items()}
    if a and a[0].get("tags"):
        tags.update({k.lower(): v_ for k, v_ in a[0]["tags"].items()})
    fps = None
    if v:
        n, _, dd = (v[0].get("avg_frame_rate") or "0/1").partition("/")
        try:
            fps = round(float(n) / float(dd or 1), 2)
        except ZeroDivisionError:
            fps = None
    return dict(
        ext=os.path.splitext(path)[1].lower().lstrip("."), size=os.path.getsize(path),
        vcodec=v[0]["codec_name"] if v else None, width=v[0].get("width") if v else None,
        height=v[0].get("height") if v else None, fps=fps,
        acodec=a[0]["codec_name"] if a else None, channels=a[0].get("channels") if a else None,
        abr=int(a[0].get("bit_rate") or fmt.get("bit_rate") or 0) // 1000 if a else None,
        cover=bool(pic) or ("metadata_block_picture" in tags), title=tags.get("title"),
        artist=tags.get("artist"), streams=len(st), format=fmt.get("format_name"))


def human(s):
    if not s:
        return "no file"
    parts = [f".{s['ext']}", f"{s['size']/1048576:.1f} MB"]
    if s["vcodec"]:
        parts.append(f"{s['vcodec']} {s['width']}x{s['height']} {s['fps']} fps")
    else:
        parts.append("no video")
    if s["acodec"]:
        parts.append(f"{s['acodec']} {s['channels']}ch ~{s['abr']} kbps")
    else:
        parts.append("no audio")
    if s["cover"]:
        parts.append("cover art")
    if s["title"]:
        parts.append(f"title tag '{s['title'][:30]}'")
    return ", ".join(parts)


# case id -> (url, spec, check(summary, est, extra) -> (ok, note))
def av(res, fps, cont, codec, abr=None):
    return dict(mode="av", res=res, fps=fps, container=cont, codec=codec, abr=abr)


def vo(res, fps, cont, codec):
    return dict(mode="video", res=res, fps=fps, container=cont, codec=codec)


def ao(fmt, q, cover=True):
    return dict(mode="audio", afmt=fmt, aq=q, embed_cover=cover)


CASES = {
    "VA-01": (TD1, av(1080, 60, "mp4", "h264"), lambda s, e: s["ext"] == "mp4" and s["vcodec"] == "h264" and s["height"] == 1080 and s["fps"] and s["fps"] > 50 and s["acodec"] == "aac" and s["channels"] == 2),
    "VA-02": (TD1, av(480, 30, "mkv", "vp9"), lambda s, e: s["ext"] == "mkv" and s["vcodec"] == "vp9" and s["height"] == 480 and s["acodec"] is not None),
    "VA-03": (TD1, av(360, 30, "webm", "vp9"), lambda s, e: s["ext"] == "webm" and s["vcodec"] in ("vp9", "av1") and s["acodec"] == "opus"),
    "VA-04": (TD1, av(720, 60, "mov", "h264"), lambda s, e: s["ext"] == "mov" and s["vcodec"] == "h264" and s["acodec"] == "aac"),
    "VA-05": (TD2, av(240, 30, "avi", "h264"), lambda s, e: s["ext"] == "avi" and s["vcodec"] is not None and s["acodec"] is not None and any("AVI" in w for w in e["warnings"])),
    "VA-06": (TD1, av(1080, 60, "mp4", "av1"), lambda s, e: s["vcodec"] == "av1" and s["height"] == 1080),
    "VA-07": (TD1, av(2160, 60, "mkv", "auto"), lambda s, e: s["height"] == 2160 and s["width"] == 3840 and s["fps"] and s["fps"] > 50),
    "VA-09L": (TD1, av(360, 30, "mp4", "h264", 70), lambda s, e: s["abr"] and s["abr"] < 80),
    "VA-09H": (TD1, av(360, 30, "mp4", "h264", None), lambda s, e: s["abr"] and s["abr"] > 100),
    "VO-01": (TD1, vo(360, 30, "mp4", "h264"), lambda s, e: s["ext"] == "mp4" and s["vcodec"] == "h264" and s["acodec"] is None),
    "VO-02a": (TD1, vo(360, 30, "mkv", "h264"), lambda s, e: s["ext"] == "mkv" and s["vcodec"] and s["acodec"] is None),
    "VO-02b": (TD1, vo(360, 30, "mov", "h264"), lambda s, e: s["ext"] == "mov" and s["vcodec"] and s["acodec"] is None),
    "VO-02c": (TD1, vo(360, 30, "webm", "vp9"), lambda s, e: s["ext"] == "webm" and s["vcodec"] and s["acodec"] is None),
    "VO-03": (TD1, vo(720, 60, "mp4", "h264"), lambda s, e: s["fps"] and s["fps"] > 50 and s["acodec"] is None),
    "AO-01": (TD1, ao("mp3", 192), lambda s, e: s["ext"] == "mp3" and s["acodec"] == "mp3" and 180 <= (s["abr"] or 0) <= 200 and s["channels"] == 2 and s["cover"] and s["title"]),
    "AO-02": (TD1, ao("mp3", 320), lambda s, e: 300 <= (s["abr"] or 0) <= 330 and any("129" in w for w in e["warnings"])),
    "AO-03": (TD1, ao("m4a", 192), lambda s, e: s["ext"] == "m4a" and s["acodec"] == "aac" and 170 <= (s["abr"] or 0) <= 215 and abs(s["size"] - e["size"]) / e["size"] < 0.12),
    "AO-04": (TD1, ao("aac", 192), lambda s, e: s["acodec"] == "aac" and 170 <= (s["abr"] or 0) <= 215),
    "AO-05": (TD1, ao("opus", 128), lambda s, e: s["ext"] == "opus" and s["acodec"] == "opus" and s["channels"] == 2 and s["cover"] and 110 <= (s["abr"] or 0) <= 145),
    "AO-05L": (TD1, ao("opus", 64), lambda s, e: s["acodec"] == "opus" and 50 <= (s["abr"] or 0) <= 80),
    "AO-03B": (TD1, ao("m4a", 0), lambda s, e: s["acodec"] == "aac" and abs(s["size"] - e["size"]) / e["size"] < 0.05),
    "AO-06": (TD1, ao("vorbis", 192), lambda s, e: s["ext"] == "ogg" and s["acodec"] == "vorbis"),
    "AO-07": (TD1, ao("flac", 0), lambda s, e: s["ext"] == "flac" and s["acodec"] == "flac" and s["channels"] == 2),
    "AO-08": (TD1, ao("wav", 0, cover=True), lambda s, e: s["ext"] == "wav" and s["acodec"].startswith("pcm")),
    "AO-09": (TD1, ao("original", 0), lambda s, e: s["ext"] in ("m4a", "opus", "webm") and s["acodec"] in ("aac", "opus")),
    "AO-10": (TD1, ao("mp3", 192, cover=False), lambda s, e: s["ext"] == "mp3" and not s["cover"]),
    "AO-11": (TD1, ao("mp3", 0), lambda s, e: s["ext"] == "mp3"),
}


def mp3_mode(path):
    try:
        from mutagen.mp3 import MP3, BitrateMode
        m = MP3(path)
        return str(m.info.bitrate_mode).split(".")[-1]
    except Exception as ex:
        return f"unknown ({ex})"


def main():
    outroot, ids = sys.argv[1], sys.argv[2].split(",")
    os.makedirs(outroot, exist_ok=True)
    app = QCoreApplication(sys.argv)
    log = open(os.path.join(outroot, "results.jsonl"), "a", encoding="utf-8")
    infos = {}
    queue = list(ids)

    def record(rec):
        log.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log.flush()
        print(json.dumps(rec, ensure_ascii=False), flush=True)

    def next_case():
        if not queue:
            app.quit()
            return
        cid = queue.pop(0)
        url, spec, check = CASES[cid]
        if url in infos:
            run(cid, url, spec, check, infos[url])
            return
        t0 = time.time()
        f = FetchJob(url, False)

        def ok(info):
            infos[url] = info
            run(cid, url, spec, check, info, fetch_s=time.time() - t0)

        def bad(msg):
            record(dict(case=cid, status="Fail", actual=f"Fetch failed: {msg}"))
            QTimer.singleShot(50, next_case)
        f.done.connect(ok)
        f.failed.connect(bad)
        f._keep = f
        app._f = f
        f.start()

    def run(cid, url, spec, check, info, fetch_s=None):
        outdir = os.path.join(outroot, cid)
        spec = dict(spec, outdir=outdir, template="title", embed_meta=True)
        est = Analysis(info).estimate(spec)
        t0 = time.time()
        st = {"first": None}
        job = DownloadJob(url, spec, est["streams"], info=info)

        def prog(p, h, d):
            if st["first"] is None and p > 0:
                st["first"] = round(time.time() - t0, 1)

        def done(okk, msg, files):
            dur = round(time.time() - t0, 1)
            rec = dict(case=cid, est_size=est.get("size"), est_desc=est.get("desc"), warnings=est.get("warnings"),
                       first_progress_s=st["first"], total_s=dur, fetch_s=round(fetch_s, 1) if fetch_s else None)
            if not okk:
                rec.update(status="Fail", actual=f"Download failed: {msg}")
            elif not files or not os.path.exists(files[-1]):
                rec.update(status="Fail", actual="Reported success but no output file")
            else:
                s = summarize(files[-1])
                rec["probe"] = s
                passed = bool(check(s, est))
                extra = ""
                if cid == "AO-11":
                    mode = mp3_mode(files[-1])
                    extra = f", bitrate mode {mode}"
                    passed = passed and mode == "VBR"
                rec.update(status="Pass" if passed else "Fail", actual=human(s) + extra, file=files[-1])
                left = [p for p in glob.glob(os.path.join(outdir, "*")) if p not in files]
                if left:
                    rec["leftovers"] = left
            record(rec)
            QTimer.singleShot(50, next_case)

        job.progress.connect(prog)
        job.done.connect(done)
        app._j = job
        job.start()

    QTimer.singleShot(0, next_case)
    app.exec()


if __name__ == "__main__":
    activate_engine_updates()
    ytdlp()
    main()
