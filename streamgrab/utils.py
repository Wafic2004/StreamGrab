import os
import sys
import shutil
import subprocess
from urllib.parse import urlparse, parse_qs


def app_dir():
    """Folder that contains the app (the .exe when frozen, the project root otherwise)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_tool(name):
    """Locate a helper executable: bundled bin/ folder first, then PATH."""
    exe = name + ".exe" if os.name == "nt" else name
    bases = [os.path.join(app_dir(), "bin")]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(os.path.join(meipass, "bin"))
    for base in bases:
        p = os.path.join(base, exe)
        if os.path.isfile(p):
            return p
    return shutil.which(name)


def data_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "StreamGrab")
    os.makedirs(d, exist_ok=True)
    return d


def default_download_dir():
    return os.path.join(os.path.expanduser("~"), "Downloads", "StreamGrab")


def fmt_bytes(n):
    if n is None:
        return "—"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit in ("B", "KB"):
                return f"{n:.0f} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_duration(sec):
    if not sec:
        return ""
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_eta(sec):
    if sec is None:
        return ""
    sec = int(sec)
    if sec < 60:
        return f"{sec}s"
    m, s = divmod(sec, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def fmt_count(n):
    if n is None:
        return ""
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            v = f"{n / div:.1f}".rstrip("0").rstrip(".")
            return v + suf
    return str(n)


def fmt_date(d):
    """yt-dlp upload_date (YYYYMMDD) -> '12 Mar 2024'."""
    if not d or len(d) != 8:
        return ""
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    try:
        return f"{int(d[6:8])} {months[int(d[4:6]) - 1]} {d[0:4]}"
    except (ValueError, IndexError):
        return ""


def to_num(s):
    if s in (None, "", "NA", "None", "none"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def normalize_url(text):
    url = (text or "").strip().strip('"').strip("'")
    if not url:
        return ""
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


def check_link(text):
    """Return (url, error). url is normalised; error is a friendly message when the text isn't a web link."""
    raw = (text or "").strip().strip('"').strip("'")
    if not raw:
        return "", None
    bad = ("That doesn't look like a link",
           "Paste a YouTube video or playlist link, for example https://www.youtube.com/watch?v=…")
    if any(c.isspace() for c in raw):
        return "", bad
    url = normalize_url(raw)
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return "", bad
    if "." not in host or host.startswith(".") or host.endswith("."):
        return "", bad
    return url, None


def looks_like_url(text):
    t = (text or "").strip().lower()
    return t.startswith(("http://", "https://", "www.", "youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com"))


def is_media_link(text):
    t = (text or "").strip().lower()
    if " " in t or len(t) < 12:
        return False
    return any(k in t for k in ("youtube.com/watch", "youtu.be/", "youtube.com/shorts/", "youtube.com/playlist",
                                "youtube.com/live/", "music.youtube.com/"))


def playlist_kind(url):
    """Return 'playlist' (pure playlist link), 'both' (video inside a playlist) or None."""
    try:
        u = urlparse(url)
    except ValueError:
        return None
    qs = parse_qs(u.query)
    has_list = "list" in qs
    has_video = "v" in qs or "youtu.be" in u.netloc or "/shorts/" in u.path
    if u.path.rstrip("/").endswith("/playlist") and has_list:
        return "playlist"
    if has_list and has_video:
        return "both"
    if has_list:
        return "playlist"
    return None


def reveal_in_explorer(path):
    if os.name == "nt":
        if os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(path)  # noqa
    else:
        subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)])
