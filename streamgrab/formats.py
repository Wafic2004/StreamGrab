"""Turns yt-dlp's raw format list into friendly choices and size estimates."""

RES_TAGS = {4320: "8K", 2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD", 480: "SD"}
STANDARD_RES = [2160, 1440, 1080, 720, 480, 360, 240, 144]

CODEC_NAMES = {"h264": "H.264", "vp9": "VP9", "av1": "AV1", "h265": "H.265", "other": "Other", "auto": "Auto"}
AUTO_RANK = {"av1": 4, "vp9": 3, "h265": 2, "h264": 1, "other": 0}

AUDIO_FORMAT_LABELS = {
    "mp3": "MP3", "m4a": "M4A", "aac": "AAC", "opus": "Opus", "vorbis": "OGG",
    "flac": "FLAC", "wav": "WAV", "original": "Original",
}


def codec_family(vc):
    vc = (vc or "").lower()
    if vc.startswith(("avc", "h264")):
        return "h264"
    if vc.startswith(("vp09", "vp9")):
        return "vp9"
    if vc.startswith("av01"):
        return "av1"
    if vc.startswith(("hev", "hvc", "h265")):
        return "h265"
    return "other"


def acodec_name(ac):
    ac = (ac or "").lower()
    if ac.startswith("opus"):
        return "Opus"
    if ac.startswith(("mp4a", "aac")):
        return "AAC"
    if ac.startswith("vorbis"):
        return "Vorbis"
    if ac.startswith("mp3"):
        return "MP3"
    return ac.upper() or "Audio"


def res_of(f):
    w, h = f.get("width"), f.get("height")
    if w and h:
        return min(w, h)
    return h or 0


def size_of(f, duration):
    if not f:
        return None
    s = f.get("filesize") or f.get("filesize_approx")
    if s:
        return s
    tbr = f.get("tbr") or ((f.get("vbr") or 0) + (f.get("abr") or 0))
    if tbr and duration:
        return tbr * 1000 / 8 * duration
    return None


def res_label(r, fps=None):
    s = f"{r}p" + (str(fps) if fps and fps > 30 else "")
    tag = RES_TAGS.get(r)
    return f"{s}   ·   {tag}" if tag else s


class Analysis:
    def __init__(self, info):
        self.info = info
        self.is_playlist = info.get("_type") == "playlist"
        self.duration = info.get("duration")
        fm = [] if self.is_playlist else (info.get("formats") or [])
        fm = [f for f in fm if f.get("ext") != "mhtml" and "storyboard" not in (f.get("format_note") or "").lower()]
        self.videos = [f for f in fm if f.get("vcodec") not in (None, "none") and res_of(f) > 0]
        self.audios = [f for f in fm if f.get("vcodec") == "none" and f.get("acodec") not in (None, "none")]

        self.codecs_at = {}
        by_res = {}
        for f in self.videos:
            r = res_of(f)
            by_res.setdefault(r, set()).add(int(round(f.get("fps") or 30)))
            self.codecs_at.setdefault(r, set()).add(codec_family(f.get("vcodec")))

        self.max_res = max(by_res) if by_res else None
        self.has_hfr = any(x > 30 for s in by_res.values() for x in s)
        self.best_audio = self.pick_audio()

        # (label, res, fps)
        self.res_options = []
        for r in sorted(by_res, reverse=True):
            fpss = sorted(by_res[r], reverse=True)
            hi = [x for x in fpss if x > 30]
            lo = [x for x in fpss if x <= 30]
            if hi:
                self.res_options.append((res_label(r, hi[0]), r, hi[0]))
            if lo:
                self.res_options.append((res_label(r), r, 30))

    @staticmethod
    def standard_res_options():
        return [(res_label(r), r, None) for r in STANDARD_RES]

    # ---- selection mimicking yt-dlp's sort order (res, fps, codec, ext, abr) ----
    def pick_video(self, res, fps, codec, prefer_ext=None, strict_ext=False):
        cands = self.videos
        if strict_ext and prefer_ext:
            cands = [f for f in cands if f.get("ext") == prefer_ext] or cands

        def key(f):
            r = res_of(f)
            fr = f.get("fps") or 30
            k_res = (1, r) if (not res or r <= res) else (0, -r)
            k_fps = (1, fr) if (not fps or fr <= fps + 1) else (0, -fr)
            fam = codec_family(f.get("vcodec"))
            k_codec = 1 if (codec in (None, "auto") or fam == codec) else 0
            k_ext = 1 if (prefer_ext and f.get("ext") == prefer_ext) else 0
            proto = f.get("protocol") or ""
            k_proto = 1 if proto.startswith("http") and "m3u8" not in proto else 0
            k_sep = 1 if f.get("acodec") in (None, "none") else 0   # yt-dlp prefers separate video streams
            return (k_res, k_fps, k_codec, k_ext, k_sep, AUTO_RANK.get(fam, 0), k_proto, f.get("tbr") or 0)

        return max(cands, key=key, default=None)

    def pick_audio(self, cap=None, prefer_ext=None, strict_ext=False):
        cands = self.audios
        if strict_ext and prefer_ext:
            cands = [f for f in cands if f.get("ext") == prefer_ext] or cands

        def key(f):
            br = f.get("abr") or f.get("tbr") or 0
            k_ext = 1 if (prefer_ext and f.get("ext") == prefer_ext) else 0
            k_cap = (1, br) if (not cap or br <= cap + 2) else (0, -br)
            k_ch = 1 if (f.get("audio_channels") or 2) <= 2 else 0
            k_drc = 0 if "drc" in str(f.get("format_id", "")) else 1
            return (k_ch, k_ext, k_cap, k_drc)

        return max(cands, key=key, default=None)

    # ---- estimate shown under the options ----
    def estimate(self, spec):
        mode = spec["mode"]
        warn = []
        if self.is_playlist or spec.get("playlist"):
            n = len(self.info.get("entries") or []) if self.is_playlist else 0
            what = f"{n} videos" if n else "Entire playlist"
            return dict(size=None, desc=f"{what}   ·   these settings are applied to every video",
                        warnings=[], streams=2 if mode == "av" else 1)

        dur = self.duration
        if mode in ("av", "video"):
            cont, codec = spec["container"], spec["codec"]
            vext = "mp4" if cont in ("mp4", "mov") else ("webm" if cont == "webm" else None)
            v = self.pick_video(spec.get("res"), spec.get("fps"), codec, vext, strict_ext=(cont == "webm"))
            if not v:
                return dict(size=None, desc="No downloadable video streams were found.", warnings=[], streams=1)
            a = None
            if mode == "av" and v.get("acodec") in (None, "none"):
                aext = "m4a" if cont in ("mp4", "mov") else ("webm" if cont == "webm" else None)
                a = self.pick_audio(spec.get("abr"), aext, strict_ext=(cont == "webm"))
            size = (size_of(v, dur) or 0) + ((size_of(a, dur) or 0) if a else 0)
            fam = codec_family(v.get("vcodec"))
            parts = []
            if v.get("width") and v.get("height"):
                parts.append(f"{v['width']}×{v['height']}")
            parts.append(f"{int(round(v.get('fps') or 30))} fps")
            parts.append(CODEC_NAMES.get(fam, fam))
            desc = "   ·   ".join(parts)
            if a:
                desc += f"   +   {acodec_name(a.get('acodec'))} {int(a.get('abr') or a.get('tbr') or 0)} kbps"
            elif mode == "video":
                desc += "   ·   no audio track"
            if codec not in (None, "auto") and fam != codec:
                warn.append(f"{CODEC_NAMES[codec]} isn't offered at this resolution, so {CODEC_NAMES.get(fam, fam)} will be used instead.")
            if cont == "avi":
                warn.append("AVI needs a full re-encode, which can take a long time. MP4 or MKV is much faster.")
            if cont == "mov" and fam in ("vp9", "av1"):
                warn.append(f"{CODEC_NAMES[fam]} inside MOV may not play in QuickTime. Pick H.264 for best compatibility.")
            return dict(size=size or None, desc=desc, warnings=warn, streams=2 if a else 1)

        # audio only
        fmt, q = spec["afmt"], spec.get("aq") or 0
        aext = "m4a" if fmt in ("m4a", "aac") else ("webm" if fmt in ("opus", "vorbis") else None)
        if q and fmt in ("m4a", "aac", "opus"):
            aext = "webm" if fmt in ("m4a", "aac") else "m4a"   # same as engine: re-encode at the chosen bitrate
        src = self.pick_audio(None, aext)
        if not src:
            return dict(size=None, desc="No audio stream was found.", warnings=[], streams=1)
        sbr = int(src.get("abr") or src.get("tbr") or 0)
        sname = acodec_name(src.get("acodec"))
        label = AUDIO_FORMAT_LABELS.get(fmt, fmt.upper())
        if fmt == "original":
            size = size_of(src, dur)
            desc = f"{sname} {sbr} kbps   ·   original stream, no re-encoding"
        elif fmt in ("flac", "wav"):
            kbps = 1536 if fmt == "wav" else 1350
            size = kbps * 125 * dur if dur else None
            desc = f"{sname} {sbr} kbps source   →   {label} (lossless)"
            warn.append(f"{label} keeps the source exactly, but YouTube audio is already compressed (~{sbr} kbps).")
        elif not q and fmt in ("m4a", "aac") and sname == "AAC":
            size = size_of(src, dur)
            desc = f"{sname} {sbr} kbps   ·   original AAC stream kept (no quality loss)"
        else:
            qq = q or 192
            size = qq * 125 * dur if dur else None
            desc = f"{sname} {sbr} kbps source   →   {label} {q} kbps" if q else f"{sname} {sbr} kbps source   →   {label} (best VBR)"
            if q and sbr and q > sbr * 1.6:
                warn.append(f"The source is ~{sbr} kbps, so {q} kbps won't sound better than that. It only makes the file bigger.")
        return dict(size=size, desc=desc, warnings=warn, streams=1)
