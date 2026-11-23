"""Unit checks for the v1.0.1 defect fixes (no network)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from streamgrab.utils import check_link
from streamgrab.engine import friendly_error, build_download_args, DownloadJob

ok = True


def check(name, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + name)
    ok &= bool(cond)


# BUG-001
check("BUG-001 'hello world' rejected", check_link("hello world")[1] is not None)
check("BUG-001 'hello' rejected", check_link("hello")[1] is not None)
check("BUG-001 bare domain link accepted", check_link("youtu.be/aqz-KE-bpKQ")[0] == "https://youtu.be/aqz-KE-bpKQ")
check("BUG-001 full link accepted", check_link("https://www.youtube.com/watch?v=jNQXAC9IVRw")[1] is None)
check("BUG-001 empty -> nothing", check_link("   ") == ("", None))

# BUG-006
m = friendly_error("ERROR: [youtube] aaaaaaaaaaa: This video is unavailable")
check(f"BUG-006 friendly unavailable -> {m!r}", m.startswith("This video is unavailable."))
m = friendly_error("ERROR: [youtube] abcdefghijk: Some new message")
check(f"BUG-006 id prefix stripped -> {m!r}", m == "Some new message")

# BUG-002
base = dict(mode="audio", outdir="C:/x", template="title")
a = build_download_args(dict(base, afmt="m4a", aq=192))
check("BUG-002 M4A 192 starts from Opus source", "channels:2,aext:webm" in a)
a = build_download_args(dict(base, afmt="opus", aq=128))
check("BUG-002 Opus 128 starts from AAC source", "channels:2,aext:m4a" in a)
a = build_download_args(dict(base, afmt="m4a", aq=0))
check("BUG-002 M4A Best keeps AAC copy", "channels:2,aext:m4a" in a)
a = build_download_args(dict(base, afmt="mp3", aq=192))
check("BUG-002 MP3 unchanged", "channels:2" in a)

# BUG-003
a = build_download_args(dict(mode="av", outdir="C:/x", template="title", container="mp4", codec="h264", overwrite=True))
check("BUG-003 replace -> --force-overwrites", "--force-overwrites" in a)
a = build_download_args(dict(mode="av", outdir="C:/x", template="title", container="mp4", codec="h264", name_suffix=" (2)"))
check("BUG-003 keep both -> suffix", a[a.index("-o") + 1] == "%(title)s (2).%(ext)s")

# BUG-008 stems
check("BUG-008 stem of stream", DownloadJob._stem(r"D:\T\My [x] Video.f137.mp4") == "My [x] Video")
check("BUG-008 stem of drc stream", DownloadJob._stem(r"D:\T\Song.f251-drc.webm") == "Song")
check("BUG-008 stem of single file", DownloadJob._stem(r"D:\T\Song.webm") == "Song")

# BUG-009
j = DownloadJob("u", dict(mode="av", outdir="C:/x", container="avi", codec="auto"))
check(f"BUG-009 AVI convert label -> {j.convert_text!r}", j.convert_text.startswith("Converting to AVI"))
check("BUG-009 merge label", j.finish_text == "Merging video and audio")

print("ALL PASS" if ok else "SOME FAILED")
sys.exit(0 if ok else 1)
