"""Shown when several links are pasted or dropped at once: pick one set of options for all of them."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QPushButton,
                               QFrame, QListView, QWidget, QCheckBox)

from .utils import playlist_kind

MODES = [("Video + Audio", "av"), ("Video only", "video"), ("Audio only", "audio")]
RESOLUTIONS = [("Best available", None), ("2160p · 4K", 2160), ("1440p · 2K", 1440), ("1080p · Full HD", 1080),
               ("720p · HD", 720), ("480p", 480), ("360p", 360)]
CONTAINERS = [("MP4 · plays everywhere", "mp4"), ("MKV · most flexible", "mkv"), ("WebM", "webm")]
AUDIO_FORMATS = [("MP3", "mp3"), ("M4A · AAC", "m4a"), ("Opus", "opus"), ("FLAC · lossless", "flac"),
                 ("Original · no re-encode", "original")]
AUDIO_Q = [("320 kbps", 320), ("256 kbps", 256), ("192 kbps", 192), ("128 kbps", 128), ("Best VBR", 0)]


def _combo(items, current=None):
    c = QComboBox()
    c.setView(QListView())
    for label, data in items:
        c.addItem(label, data)
    i = c.findData(current)
    c.setCurrentIndex(max(0, i))
    return c


class BatchDialog(QDialog):
    def __init__(self, links, settings, parent=None):
        super().__init__(parent)
        self.links = links
        self.s = settings
        n = len(links)
        pls = sum(1 for u in links if playlist_kind(u) == "playlist")
        self.setWindowTitle("Add several links")
        self.setModal(True)
        self.setMinimumWidth(500)
        root = QWidget(self)
        root.setObjectName("dialogRoot")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(20, 20, 20, 16)
        v.setSpacing(14)

        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(18, 16, 18, 18)
        cv.setSpacing(10)
        t = QLabel(f"{n} LINK{'S' if n != 1 else ''} FOUND")
        t.setObjectName("section")
        cv.addWidget(t)
        what = f"{n} video{'s' if n != 1 else ''}" if not pls else \
            f"{n - pls} video{'s' if n - pls != 1 else ''} and {pls} playlist{'s' if pls != 1 else ''}"
        head = QLabel(f"Add {what} to the queue with these options:")
        head.setObjectName("statusHead")
        head.setWordWrap(True)
        cv.addWidget(head)
        preview = "\n".join(links[:6]) + (f"\n… and {n - 6} more" if n > 6 else "")
        p = QLabel(preview)
        p.setObjectName("meta")
        p.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cv.addWidget(p)
        v.addWidget(card)

        card2 = QFrame()
        card2.setObjectName("card")
        g = QGridLayout(card2)
        g.setContentsMargins(18, 16, 18, 18)
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        mode = {0: "av", 1: "video", 2: "audio"}.get(int(settings.value("mode", 0)), "av")
        self.mode = _combo(MODES, mode)
        self.res = _combo(RESOLUTIONS, int(settings.value("res_pref", 1080)))
        self.cont = _combo(CONTAINERS, settings.value("av_cont", "mp4"))
        self.afmt = _combo(AUDIO_FORMATS, settings.value("a_fmt", "mp3"))
        self.aq = _combo(AUDIO_Q, int(settings.value("a_q", 192)))
        self.lbl_res, self.lbl_cont = QLabel("Quality"), QLabel("Format")
        self.lbl_afmt, self.lbl_aq = QLabel("Audio format"), QLabel("Audio quality")
        rows = [(QLabel("Download"), self.mode), (self.lbl_res, self.res), (self.lbl_cont, self.cont),
                (self.lbl_afmt, self.afmt), (self.lbl_aq, self.aq)]
        for i, (lab, w) in enumerate(rows):
            lab.setObjectName("fieldLabel")
            g.addWidget(lab, i, 0)
            g.addWidget(w, i, 1)
        g.setColumnStretch(1, 1)
        self.pl_folder = QCheckBox("Save each playlist into its own folder")
        self.pl_folder.setChecked(settings.value("playlist_folder", True, type=bool))
        self.pl_folder.setVisible(pls > 0)
        g.addWidget(self.pl_folder, len(rows), 0, 1, 2)
        v.addWidget(card2)

        note = QLabel("If a file with the same name is already in the folder: "
                      + {"ask": "a copy is kept (you can change this in Settings).", "keep": "a copy is kept.",
                         "replace": "it is replaced.", "skip": "the link is skipped."}.get(
                          settings.value("exists", "ask"), "a copy is kept."))
        note.setObjectName("emptyText")
        note.setWordWrap(True)
        v.addWidget(note)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton(f"  Add {n} to queue")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        ok.setDefault(True)
        bottom.addWidget(cancel)
        bottom.addWidget(ok)
        v.addLayout(bottom)

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.afmt.currentIndexChanged.connect(self._mode_changed)
        self._mode_changed()
        for w in (self.mode, self.res, self.cont, self.afmt, self.aq):
            w.setAccessibleName(next(l.text() for l, x in rows if x is w))
        for b in self.findChildren(QPushButton) + self.findChildren(QCheckBox):
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def _mode_changed(self):
        audio = self.mode.currentData() == "audio"
        for w in (self.lbl_res, self.res, self.lbl_cont, self.cont):
            w.setVisible(not audio)
        for w in (self.lbl_afmt, self.afmt, self.lbl_aq, self.aq):
            w.setVisible(audio)
        self.aq.setEnabled(self.afmt.currentData() not in ("flac", "original"))

    def spec(self, outdir):
        """Download options for every link (same shape as the main window's spec)."""
        s = self.s
        mode = self.mode.currentData()
        exists = s.value("exists", "ask")
        spec = dict(mode=mode, outdir=outdir, template=s.value("template", "title"),
                    cookies=s.value("cookies", "none"), embed_meta=s.value("embed_meta", True, type=bool),
                    exists="keep" if exists == "ask" else exists)
        if mode == "audio":
            fmt = self.afmt.currentData()
            spec.update(afmt=fmt, aq=0 if fmt in ("flac", "original") else (self.aq.currentData() or 0),
                        embed_cover=s.value("a_embed", True, type=bool))
        else:
            spec.update(res=self.res.currentData(), fps=None, container=self.cont.currentData(),
                        codec="h264" if self.cont.currentData() in ("mp4", "mov") else "auto",
                        abr=None)
        return spec

    def playlist_folder(self):
        return self.pl_folder.isChecked()
