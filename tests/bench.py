"""In-process yt-dlp benchmark: python tests/bench.py URL"""
import os, sys, time, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
t0 = time.time()
import yt_dlp
print(f"import yt_dlp: {time.time()-t0:.1f}s", flush=True)

url = sys.argv[1]
deno = os.path.join(ROOT, "bin", "deno.exe")
configs = sys.argv[2].split(";") if len(sys.argv) > 2 else ["default", "default", "skiphls", "visionos", "android_vr", "tv", "web_safari", "tv,visionos"]

class L:
    def debug(self, m): pass
    def info(self, m): pass
    def warning(self, m): print("   WARN", m[:140], flush=True)
    def error(self, m): print("   ERR", m[:200], flush=True)

base = dict(quiet=True, no_warnings=False, skip_download=True, noplaylist=True, logger=L(),
            js_runtimes={"deno": {"path": deno}}, ffmpeg_location=os.path.join(ROOT, "bin"))
t = time.time(); y0 = yt_dlp.YoutubeDL(dict(base)); print(f"create YoutubeDL: {time.time()-t:.1f}s", flush=True)

for c in configs:
    opts = dict(base)
    ea = {}
    if c == "skiphls":
        ea = {"youtube": {"skip": ["hls"]}}
    elif c != "default":
        ea = {"youtube": {"player_client": c.split(","), "skip": ["hls"]}}
    if ea:
        opts["extractor_args"] = ea
    t = time.time()
    try:
        with yt_dlp.YoutubeDL(opts) as y:
            info = y.extract_info(url, download=False)
        fm = info.get("formats") or []
        vids = [f for f in fm if f.get("vcodec") not in (None, "none")]
        auds = [f for f in fm if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]
        mh = max((min(f.get("width") or 0, f.get("height") or 0) or (f.get("height") or 0) for f in vids), default=0)
        print(f"{c:14s} {time.time()-t:5.1f}s  formats={len(fm)} video={len(vids)} audio={len(auds)} max={mh}p "
              f"protos={sorted(set(f.get('protocol') for f in fm))}", flush=True)
    except Exception as e:
        print(f"{c:14s} {time.time()-t:5.1f}s  FAILED {str(e)[:150]}", flush=True)
