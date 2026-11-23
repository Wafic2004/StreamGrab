"""The Queue tab: one row per download, plus Pause/Resume, Retry failed and Clear finished."""
import os

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar,
                               QScrollArea)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from . import icons as I
from .utils import fmt_bytes, fmt_duration, reveal_in_explorer

AUDIO_NAMES = {"mp3": "MP3", "m4a": "M4A", "aac": "AAC", "opus": "Opus", "vorbis": "OGG", "flac": "FLAC",
               "wav": "WAV", "original": "Original audio"}


def describe_spec(spec):
    mode = spec.get("mode")
    if mode in ("av", "video"):
        bits = [(spec.get("container") or "mp4").upper()]
        if spec.get("res"):
            fps = spec.get("fps")
            bits.append(f"{spec['res']}p{fps if fps and fps > 30 else ''}")
        else:
            bits.append("best quality")
        if mode == "video":
            bits.append("no sound")
        return "  ·  ".join(bits)
    fmt = spec.get("afmt", "mp3")
    q = spec.get("aq") or 0
    if fmt in ("flac", "wav"):
        qs = "lossless"
    elif fmt == "original":
        qs = "no re-encode"
    else:
        qs = f"{q} kbps" if q else "best quality"
    return f"{AUDIO_NAMES.get(fmt, fmt.upper())}  ·  {qs}"


class ElideLabel(QLabel):
    def __init__(self, text="", name=None):
        super().__init__()
        if name:
            self.setObjectName(name)
        self._full = text
        self.setMinimumWidth(40)
        self.setText(text)

    def setText(self, text):
        self._full = text or ""
        self.setToolTip(self._full)
        self._elide()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._elide()

    def _elide(self):
        w = max(40, self.width())
        super().setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, w))


class QueueRow(QFrame):
    def __init__(self, page, iid):
        super().__init__()
        self.page, self.iid = page, iid
        self.setObjectName("qrow")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(14)
        self.thumb = QLabel()
        self.thumb.setObjectName("qthumb")
        self.thumb.setFixedSize(112, 63)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        h.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)

        col = QVBoxLayout()
        col.setSpacing(3)
        self.title = ElideLabel("", "qtitle")
        self.sub = ElideLabel("", "qsub")
        prow = QHBoxLayout()
        prow.setSpacing(10)
        self.bar = QProgressBar()
        self.bar.setObjectName("thin")
        self.bar.setRange(0, 1000)
        self.pct = QLabel("")
        self.pct.setObjectName("qpct")
        self.pct.setMinimumWidth(36)
        self.pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        prow.addWidget(self.bar, 1)
        prow.addWidget(self.pct)
        self.status = ElideLabel("", "qstatus")
        col.addWidget(self.title)
        col.addWidget(self.sub)
        col.addSpacing(2)
        col.addLayout(prow)
        col.addWidget(self.status)
        h.addLayout(col, 1)

        self.btns = {}
        bl = QHBoxLayout()
        bl.setSpacing(4)
        for key, tip in (("play", "Play"), ("folder", "Show in folder"), ("retry", "Retry"),
                         ("resume", "Resume"), ("cancel", "Cancel"), ("remove", "Remove from list")):
            b = QPushButton()
            b.setObjectName("icon")
            b.setFixedSize(32, 32)
            b.setToolTip(tip)
            b.setAccessibleName(tip)
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            b.clicked.connect(lambda _=False, k=key: self.page.row_action(self.iid, k))
            bl.addWidget(b)
            self.btns[key] = b
        h.addLayout(bl)

    def apply_icons(self, pal):
        t, d = pal["text"], pal["danger"]
        glyphs = {"play": (I.G_PLAY, t), "folder": (I.G_BROWSE, t), "retry": (I.G_REFRESH, t),
                  "resume": (I.G_PLAY, pal["accent"]), "cancel": (I.G_CANCEL, d), "remove": (I.G_DELETE, t)}
        for k, (g, c) in glyphs.items():
            self.btns[k].setIcon(I.glyph_icon(g, c, 14))

    def update_from(self, it):
        self.title.setText(it.get("title") or it.get("url"))
        bits = [describe_spec(it.get("spec") or {})]
        if it.get("size"):
            bits.append(f"≈ {fmt_bytes(it['size'])}")
        if it.get("duration"):
            bits.append(fmt_duration(it["duration"]))
        if it.get("group"):
            bits.append(it["group"])
        self.sub.setText("   ·   ".join(bits))
        st = it["status"]
        pct = it.get("pct") or 0
        if st in ("starting", "downloading") and pct < 0:
            self.bar.setRange(0, 0)
            self.pct.setText("")
        else:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(max(0, min(100, pct if st != "done" else 100)) * 10))
            self.pct.setText(f"{int(pct)}%" if st in ("downloading", "paused") and pct > 0 else
                             ("100%" if st == "done" else ""))
        head, detail = it.get("head", ""), it.get("detail", "")
        text = head + (f"   ·   {detail.splitlines()[0]}" if detail else "")
        self.status.setText(text)
        self.status.setProperty("state", {"done": "ok", "skipped": "ok", "failed": "error"}.get(st, ""))
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        files = [f for f in it.get("files") or [] if f]
        one_file = len(files) == 1 and os.path.isfile(files[0])
        self.btns["play"].setVisible(st in ("done", "skipped") and one_file)
        self.btns["folder"].setVisible(st in ("done", "skipped") and bool(files))
        self.btns["retry"].setVisible(st in ("failed", "cancelled"))
        self.btns["resume"].setVisible(st == "paused")
        self.btns["cancel"].setVisible(st in ("waiting", "starting", "downloading", "paused"))
        self.btns["remove"].setVisible(st not in ("starting", "downloading"))

    def set_thumb(self, pix):
        if pix is None or pix.isNull():
            return
        dpr = self.devicePixelRatioF()
        w, h = int(112 * dpr), int(63 * dpr)
        scaled = pix.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                            Qt.TransformationMode.SmoothTransformation)
        x, y = (scaled.width() - w) // 2, (scaled.height() - h) // 2
        out = scaled.copy(x, y, w, h)
        out.setDevicePixelRatio(dpr)
        self.thumb.setPixmap(out)


class QueuePage(QWidget):
    count_changed = Signal(int)

    def __init__(self, queue, parent=None):
        super().__init__(parent)
        self.q = queue
        self.rows = {}
        self.pal = None
        self._thumbs = {}
        self._pending = {}
        self.nam = QNetworkAccessManager(self)
        self.nam.finished.connect(self._thumb_loaded)

        v = QVBoxLayout(self)
        v.setContentsMargins(26, 6, 26, 24)
        v.setSpacing(12)

        bar = QFrame()
        bar.setObjectName("card")
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(18, 12, 12, 12)
        bh.setSpacing(8)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("DOWNLOAD QUEUE")
        t.setObjectName("section")
        self.summary = QLabel("Nothing in the queue yet")
        self.summary.setObjectName("statusHead")
        col.addWidget(t)
        col.addWidget(self.summary)
        bh.addLayout(col, 1)
        self.pause_btn = QPushButton("  Pause all")
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.retry_btn = QPushButton("  Retry failed")
        self.retry_btn.clicked.connect(self._retry_failed)
        self.clear_btn = QPushButton("  Clear finished")
        self.clear_btn.clicked.connect(self.q.clear_finished)
        for b in (self.pause_btn, self.retry_btn, self.clear_btn):
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            bh.addWidget(b)
        v.addWidget(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        holder = QWidget()
        holder.setObjectName("root")
        self.list = QVBoxLayout(holder)
        self.list.setContentsMargins(0, 0, 4, 0)
        self.list.setSpacing(8)
        self.empty = QLabel("Downloads you start appear here.\nYou can add several at once: paste a few links "
                            "(one per line) or a playlist.")
        self.empty.setObjectName("emptyText")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setMinimumHeight(160)
        self.list.addWidget(self.empty)
        self.list.addStretch(1)
        self.scroll.setWidget(holder)
        self.scroll.viewport().setObjectName("root")
        v.addWidget(self.scroll, 1)

        self.q.item_added.connect(self._added)
        self.q.item_changed.connect(self._changed)
        self.q.item_removed.connect(self._removed)
        self.q.summary_changed.connect(self._summary)
        self._summary()

    # ---------------------------------------------------------------- theme
    def apply_theme(self, pal):
        self.pal = pal
        t = pal["text"]
        self.retry_btn.setIcon(I.glyph_icon(I.G_REFRESH, t, 14))
        self.clear_btn.setIcon(I.glyph_icon(I.G_CLEAR, t, 14))
        self._summary()
        for r in self.rows.values():
            r.apply_icons(pal)
            if r.thumb.pixmap() is None or r.thumb.pixmap().isNull():
                r.thumb.setPixmap(I.glyph_pixmap(I.G_VIDEO, pal["muted"], 22))

    # ---------------------------------------------------------------- rows
    def _added(self, iid):
        it = self.q.item(iid)
        if not it or iid in self.rows:
            return
        row = QueueRow(self, iid)
        if self.pal:
            row.apply_icons(self.pal)
            row.thumb.setPixmap(I.glyph_pixmap(I.G_VIDEO, self.pal["muted"], 22))
        row.update_from(it)
        self.list.insertWidget(self.list.count() - 1, row)      # before the stretch at the end
        self.rows[iid] = row
        self._load_thumb(iid, it.get("thumb"))
        self._summary()

    def _changed(self, iid):
        it, row = self.q.item(iid), self.rows.get(iid)
        if it and row:
            row.update_from(it)
            if it.get("thumb") and self._pending.get(iid) is None and iid not in self._thumbs:
                self._load_thumb(iid, it["thumb"])

    def _removed(self, iid):
        row = self.rows.pop(iid, None)
        if row:
            row.setParent(None)
            row.deleteLater()
        self._thumbs.pop(iid, None)
        self._summary()

    def _load_thumb(self, iid, url):
        if not url or iid in self._thumbs:
            return
        req = QNetworkRequest(QUrl(url))
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        reply = self.nam.get(req)
        reply.setProperty("iid", iid)
        self._pending[iid] = reply

    def _thumb_loaded(self, reply):
        iid = reply.property("iid")
        self._pending.pop(iid, None)
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pix = QPixmap()
            if pix.loadFromData(bytes(reply.readAll())):
                self._thumbs[iid] = True
                row = self.rows.get(iid)
                if row:
                    row.set_thumb(pix)
        reply.deleteLater()

    # ---------------------------------------------------------------- actions
    def row_action(self, iid, key):
        it = self.q.item(iid)
        if not it:
            return
        files = [f for f in it.get("files") or [] if f]
        if key == "cancel":
            self.q.cancel(iid)
        elif key == "resume":
            self.q.resume(iid)
        elif key == "retry":
            self.q.retry(iid)
            if self.q.paused_all:
                self.q.resume_all()
        elif key == "remove":
            self.q.remove(iid)
        elif key == "play" and files:
            QDesktopServices.openUrl(QUrl.fromLocalFile(files[-1]))
        elif key == "folder":
            if files and os.path.exists(files[-1]):
                reveal_in_explorer(files[-1])
            else:
                d = (it.get("spec") or {}).get("outdir")
                if d and os.path.isdir(d):
                    QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    def _toggle_pause(self):
        if self.q.paused_all:
            self.q.resume_all()
        else:
            self.q.pause_all()
        self._summary()

    def _retry_failed(self):
        for iid in self.q.failed_ids():
            self.q.retry(iid)
        if self.q.paused_all:
            self.q.resume_all()

    def _summary(self):
        c = self.q.counts()
        parts = []
        if c["running"]:
            parts.append(f"{c['running']} downloading")
        if c["waiting"]:
            parts.append(f"{c['waiting']} waiting")
        if c["paused"]:
            parts.append(f"{c['paused']} paused")
        if c["done"] + c["skipped"]:
            parts.append(f"{c['done'] + c['skipped']} done")
        if c["failed"]:
            parts.append(f"{c['failed']} failed")
        self.summary.setText("   ·   ".join(parts) if parts else "Nothing in the queue yet")
        self.empty.setVisible(not self.q.items)
        paused = self.q.paused_all
        self.pause_btn.setText("  Resume all" if paused else "  Pause all")
        self.pause_btn.setEnabled(c["active"] > 0)
        if self.pal:
            self.pause_btn.setIcon(I.glyph_icon(I.G_PLAY if paused else I.G_PAUSE, self.pal["text"], 14))
        self.retry_btn.setVisible(c["failed"] > 0)
        self.clear_btn.setEnabled(c["done"] + c["skipped"] + c["cancelled"] > 0)
        self.count_changed.emit(c["active"])
