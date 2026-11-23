"""Check visionos formats detail + download reuse (no second extraction). python tests/bench2.py URL OUTDIR"""
import os, sys, time
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import yt_dlp

url, out = sys.argv[1], sys.argv[2]
clients = sys.argv[3].split(",") if len(sys.argv) > 3 else ["visionos"]
deno = os.path.join(ROOT, "bin", "deno.exe")
opts = dict(quiet=True, noplaylist=True, js_runtimes={"deno": {"path": deno}},
            ffmpeg_location=os.path.join(ROOT, "bin"),
            extractor_args={"youtube": {"player_client": clients, "skip": ["hls"]}})
y = yt_dlp.YoutubeDL(opts)
t = time.time()
info = y.extract_info(url, download=False)
print(f"extract {time.time()-t:.1f}s  title={info.get('title')!r} views={info.get('view_count')} date={info.get('upload_date')} ch={info.get('channel')}")
seen = {}
for f in info["formats"]:
    if f.get("vcodec") not in (None, "none"):
        k = (f.get("height"), int(f.get("fps") or 0))
        seen.setdefault(k, set()).add((f.get("vcodec") or "")[:4])
print("video:", sorted(((k, sorted(v)) for k, v in seen.items()), reverse=True))
print("audio:", [(f["format_id"], f.get("acodec"), f.get("abr")) for f in info["formats"] if f.get("vcodec") == "none"])

# reuse info for the download (same YoutubeDL session): 360p h264 + audio, merged to mp4
t = time.time()
dl = yt_dlp.YoutubeDL(dict(opts, format="bv*[height<=360][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=360]+ba",
                           merge_output_format="mp4", paths={"home": out}, outtmpl="%(title)s.%(ext)s",
                           quiet=False, noprogress=True))
try:
    dl.process_ie_result(dict(info), download=True)
    print(f"reuse download OK {time.time()-t:.1f}s -> {os.listdir(out)}")
except Exception as e:
    print(f"reuse download FAILED {time.time()-t:.1f}s: {e}")
