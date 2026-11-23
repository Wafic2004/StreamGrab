import os
import time
import ctypes

from PySide6.QtCore import Qt, QSettings, QUrl, QTimer, QSize, QRectF, QPointF
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QDesktopServices, QGuiApplication, QStandardItemModel
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
                               QPushButton, QFrame, QComboBox, QListView, QCheckBox, QProgressBar, QStackedWidget,
                               QButtonGroup, QFileDialog, QScrollArea, QApplication, QSizePolicy, QMessageBox)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from . import APP_NAME
from . import icons as I
from .engine import FetchJob, DownloadJob, predict_path
from .formats import Analysis
from .settings_dialog import SettingsDialog
from .theme import build_stylesheet, palette
from .utils import (find_tool, default_download_dir, fmt_bytes, fmt_duration, fmt_count, fmt_date,
                    normalize_url, check_link, is_media_link, playlist_kind, reveal_in_explorer)

AV_CONTAINERS = [("MP4   ·   plays everywhere", "mp4"), ("MKV   ·   most flexible", "mkv"), ("WebM", "webm"),
                 ("MOV   ·   Apple & editing", "mov"), ("AVI   ·   legacy, re-encodes", "avi")]
CODECS = [("H.264   ·   most compatible", "h264"), ("VP9   ·   high efficiency", "vp9"),
          ("AV1   ·   smallest files", "av1"), ("Auto   ·   best available", "auto")]
AUDIO_TIERS = [("High   ·   best available", 0), ("Medium   ·   ~128 kbps", 130), ("Low   ·   ~64 kbps", 70)]
AUDIO_FORMATS = [("MP3", "mp3"), ("M4A   ·   AAC", "m4a"), ("AAC", "aac"), ("Opus", "opus"),
                 ("OGG   ·   Vorbis", "vorbis"), ("FLAC   ·   lossless", "flac"), ("WAV   ·   uncompressed", "wav"),
                 ("Original   ·   no re-encode", "original")]
LOSSY_Q = [("320 kbps", 320), ("256 kbps", 256), ("192 kbps", 192), ("128 kbps", 128), ("96 kbps", 96),
           ("Best VBR", 0)]
OPUS_Q = [("256 kbps", 256), ("192 kbps", 192), ("160 kbps", 160), ("128 kbps", 128), ("96 kbps", 96),
          ("64 kbps", 64)]


def make_combo(items=()):
    c = QComboBox()
    c.setView(QListView())
    c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(14)
    for label, data in items:
        c.addItem(label, data)
    return c


def set_combo_data(c, data):
    i = c.findData(data)
    if i >= 0:
        c.setCurrentIndex(i)


def set_item_enabled(c, data, enabled):
    m = c.model()
    if isinstance(m, QStandardItemModel):
        i = c.findData(data)
        if i >= 0:
            m.item(i).setEnabled(enabled)


def label(text, name=None, wrap=False):
    l = QLabel(text)
    if name:
        l.setObjectName(name)
    l.setWordWrap(wrap)
    return l


def card():
    f = QFrame()
    f.setObjectName("card")
    return f


def set_title_bar(widget, dark, color_hex):
    if os.name != "nt":
        return
    try:
        hwnd = int(widget.winId())
        dwm = ctypes.windll.dwmapi
        val = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
        c = QColor(color_hex)
        cref = ctypes.c_int(c.red() | (c.green() << 8) | (c.blue() << 16))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cref), ctypes.sizeof(cref))
        txt = QColor("#FFFFFF" if dark else "#1B1B1F")
        tref = ctypes.c_int(txt.red() | (txt.green() << 8) | (txt.blue() << 16))
        dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(tref), ctypes.sizeof(tref))
        # Windows only repaints the caption on the next frame change; force it now.
        u = ctypes.windll.user32
        if widget.isVisible():
            active = u.GetForegroundWindow() == hwnd
            u.SendMessageW(hwnd, 0x0086, 0 if active else 1, 0)    # WM_NCACTIVATE toggle
            u.SendMessageW(hwnd, 0x0086, 1 if active else 0, 0)
            u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)  # FRAMECHANGED
    except Exception:
        pass


class Thumb(QWidget):
    def __init__(self, w=224, h=126):
        super().__init__()
        self.setFixedSize(w, h)
        self._pix = None
        self._badge = ""
        self.placeholder = "#1c2029"

    def set_image(self, pix):
        self._pix = pix
        self.update()

    def set_badge(self, text):
        self._badge = text
        self.update()

    def clear(self):
        self._pix, self._badge = None, ""
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.setClipPath(path)
        p.fillRect(r, QColor(self.placeholder))
        if self._pix and not self._pix.isNull():
            dpr = self.devicePixelRatioF()
            target = QSize(int(r.width() * dpr), int(r.height() * dpr))
            s = self._pix.scaled(target, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
            s.setDevicePixelRatio(dpr)
            x = (r.width() - s.width() / dpr) / 2
            y = (r.height() - s.height() / dpr) / 2
            p.drawPixmap(QPointF(x, y), s)
        if self._badge:
            f = p.font()
            f.setPointSizeF(8.5)
            f.setBold(True)
            p.setFont(f)
            fm = p.fontMetrics()
            tw, th = fm.horizontalAdvance(self._badge) + 14, fm.height() + 4
            br = QRectF(r.width() - tw - 7, r.height() - th - 7, tw, th)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 200))
            p.drawRoundedRect(br, 6, 6)
            p.setPen(QColor("white"))
            p.drawText(br, Qt.AlignmentFlag.AlignCenter, self._badge)
        p.end()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.s = QSettings(APP_NAME, APP_NAME)
        self.info = None
        self.analysis = None
        self.url = ""
        self.fetcher = None
        self.job = None
        self.last_files = []
        self.busy = False
        self.est = None
        self.missing_tools = []
        self.nam = QNetworkAccessManager(self)
        self.nam.finished.connect(self._thumb_loaded)

        self.setWindowTitle(f"{APP_NAME}  ·  YouTube Downloader")
        self.setWindowIcon(I.app_icon())
        self.setMinimumSize(740, 560)
        scr = QGuiApplication.primaryScreen().availableGeometry()
        self.resize(min(900, scr.width() - 60), min(940, scr.height() - 40))
        self.setAcceptDrops(True)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # not a useful Tab stop
        root = QWidget()
        root.setObjectName("root")
        scroll.setWidget(root)
        self.setCentralWidget(scroll)
        scroll.viewport().setObjectName("root")

        lay = QVBoxLayout(root)
        lay.setContentsMargins(26, 20, 26, 24)
        lay.setSpacing(14)
        lay.addLayout(self._build_header())
        lay.addWidget(self._build_url_card())
        lay.addWidget(self._build_info_card())
        lay.addWidget(self._build_options_card())
        lay.addWidget(self._build_save_card())
        lay.addWidget(self._build_action_card())
        lay.addStretch(1)

        self._load_prefs()
        self._setup_accessibility()
        self.apply_theme()
        self._set_has_info(False)
        self._check_tools()
        QTimer.singleShot(0, self.url_edit.setFocus)

        sh = QGuiApplication.styleHints()
        if hasattr(sh, "colorSchemeChanged"):
            sh.colorSchemeChanged.connect(lambda *_: self.s.value("theme", "dark") == "system" and self.apply_theme())

    # ================================================================== UI
    def _build_header(self):
        h = QHBoxLayout()
        h.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(I.app_icon().pixmap(40, 40))
        h.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label(APP_NAME, "appName"))
        col.addWidget(label("Download YouTube videos and audio in any quality", "appTag"))
        h.addLayout(col)
        h.addStretch(1)
        self.theme_btn = QPushButton()
        self.theme_btn.setObjectName("ghost")
        self.theme_btn.setToolTip("Switch light / dark theme")
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.settings_btn = QPushButton("  Settings")
        self.settings_btn.setObjectName("ghost")
        self.settings_btn.clicked.connect(self.open_settings)
        h.addWidget(self.theme_btn)
        h.addWidget(self.settings_btn)
        return h

    def _build_url_card(self):
        c = card()
        v = QVBoxLayout(c)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)
        v.addWidget(label("VIDEO OR PLAYLIST LINK", "section"))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a YouTube link, e.g. https://www.youtube.com/watch?v=…")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(lambda: self.fetch(force=True))
        self.url_edit.textEdited.connect(self._url_edited)
        self._auto_timer = QTimer(self, singleShot=True, interval=350, timeout=self._auto_fetch)
        self.paste_btn = QPushButton("  Paste")
        self.paste_btn.setToolTip("Paste from clipboard and fetch")
        self.paste_btn.clicked.connect(self.paste_and_fetch)
        self.fetch_btn = QPushButton("  Fetch")
        self.fetch_btn.setObjectName("primary")
        self.fetch_btn.setMinimumWidth(110)
        self.fetch_btn.clicked.connect(lambda: self.fetch(force=True))
        row.addWidget(self.url_edit, 1)
        row.addWidget(self.paste_btn)
        row.addWidget(self.fetch_btn)
        v.addLayout(row)
        self.fetch_bar = QProgressBar()
        self.fetch_bar.setObjectName("thin")
        self.fetch_bar.setRange(0, 0)
        self.fetch_bar.setVisible(False)
        v.addWidget(self.fetch_bar)
        return c

    def _build_info_card(self):
        c = card()
        v = QVBoxLayout(c)
        v.setContentsMargins(18, 18, 18, 18)
        self.info_stack = QStackedWidget()
        self.info_stack.setFixedHeight(130)
        v.addWidget(self.info_stack)

        # 0: empty / error
        empty = QWidget()
        e = QVBoxLayout(empty)
        e.setContentsMargins(0, 4, 0, 4)
        e.setSpacing(6)
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_title = label("Paste a link to get started", "emptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_text = label("Paste a YouTube video or playlist link. It loads automatically. You can also drag a link onto this window.",
                                "emptyText", wrap=True)
        self.empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e.addWidget(self.empty_icon)
        e.addWidget(self.empty_title)
        e.addWidget(self.empty_text)
        self.info_stack.addWidget(empty)

        # 1: loading
        loading = QWidget()
        lo = QVBoxLayout(loading)
        lo.setContentsMargins(0, 30, 0, 30)
        t = label("Fetching video details…", "emptyTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s = label("Reading the available qualities and formats", "emptyText")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lo.addWidget(t)
        lo.addWidget(s)
        self.info_stack.addWidget(loading)

        # 2: details
        det = QWidget()
        h = QHBoxLayout(det)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(18)
        self.thumb = Thumb()
        h.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(6)
        self.title_lbl = label("", "videoTitle", wrap=True)
        self.title_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.meta_lbl = label("", "meta", wrap=True)
        self.badges = QHBoxLayout()
        self.badges.setSpacing(6)
        self.playlist_chk = QCheckBox("Download the entire playlist")
        self.playlist_chk.toggled.connect(self._playlist_toggled)
        col.addWidget(self.title_lbl)
        col.addWidget(self.meta_lbl)
        col.addSpacing(4)
        col.addLayout(self.badges)
        col.addStretch(1)
        col.addWidget(self.playlist_chk)
        h.addLayout(col, 1)
        self.info_stack.addWidget(det)
        return c

    def _build_options_card(self):
        c = card()
        self.options_card = c
        v = QVBoxLayout(c)
        v.setContentsMargins(18, 16, 18, 18)
        v.setSpacing(14)
        v.addWidget(label("WHAT DO YOU WANT TO DOWNLOAD?", "section"))

        seg = QFrame()
        seg.setObjectName("segment")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(4, 4, 4, 4)
        sl.setSpacing(4)
        self.mode_group = QButtonGroup(self)
        self.seg_buttons = []
        for i, text in enumerate(("  Video + Audio", "  Video only", "  Audio only")):
            b = QPushButton(text)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.mode_group.addButton(b, i)
            sl.addWidget(b)
            self.seg_buttons.append(b)
        self.mode_group.idClicked.connect(self._mode_changed)
        v.addWidget(seg)

        self.pages = QStackedWidget()
        # --- Video + Audio
        p = QWidget()
        g = self._grid(p)
        self.av_res = make_combo()
        self.av_cont = make_combo(AV_CONTAINERS)
        self.av_codec = make_combo(CODECS)
        self.av_audio = make_combo(AUDIO_TIERS)
        self._add_field(g, 0, 0, "Resolution", self.av_res)
        self._add_field(g, 0, 1, "Format", self.av_cont)
        self._add_field(g, 1, 0, "Video codec", self.av_codec)
        self._add_field(g, 1, 1, "Audio quality", self.av_audio)
        self.pages.addWidget(p)
        # --- Video only
        p = QWidget()
        g = self._grid(p)
        self.v_res = make_combo()
        self.v_cont = make_combo(AV_CONTAINERS)
        self.v_codec = make_combo(CODECS)
        self._add_field(g, 0, 0, "Resolution", self.v_res)
        self._add_field(g, 0, 1, "Format", self.v_cont)
        self._add_field(g, 1, 0, "Video codec", self.v_codec)
        note = label("The video is saved without any sound track. Handy for editing.", "emptyText", wrap=True)
        g.addWidget(note, 3, 1, Qt.AlignmentFlag.AlignTop)
        self.pages.addWidget(p)
        # --- Audio only
        p = QWidget()
        g = self._grid(p)
        self.a_fmt = make_combo(AUDIO_FORMATS)
        self.a_q = make_combo()
        self.a_embed = QCheckBox("Add cover art and song info (title, artist)")
        self._add_field(g, 0, 0, "Audio format", self.a_fmt)
        self._add_field(g, 0, 1, "Quality", self.a_q)
        g.addWidget(self.a_embed, 2, 0, 1, 2)
        self.pages.addWidget(p)
        v.addWidget(self.pages)

        div = QFrame()
        div.setObjectName("divider")
        v.addWidget(div)

        est = QHBoxLayout()
        est.setSpacing(14)
        self.est_size = label("—", "estimateSize")
        col = QVBoxLayout()
        col.setSpacing(2)
        self.est_desc = label("", "estimateDesc", wrap=True)
        self.est_hint = label("", "hint", wrap=True)
        col.addWidget(label("ESTIMATED SIZE  &  QUALITY", "section"))
        col.addWidget(self.est_desc)
        col.addWidget(self.est_hint)
        est.addLayout(col, 1)
        est.addWidget(self.est_size, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(est)

        for w in (self.av_res, self.av_cont, self.av_codec, self.av_audio, self.v_res, self.v_cont, self.v_codec, self.a_q):
            w.currentIndexChanged.connect(self._options_changed)
        self.a_fmt.currentIndexChanged.connect(self._audio_format_changed)
        self.av_cont.currentIndexChanged.connect(lambda: self._container_changed(self.av_cont, self.av_codec))
        self.v_cont.currentIndexChanged.connect(lambda: self._container_changed(self.v_cont, self.v_codec))
        self.a_embed.toggled.connect(self._options_changed)
        return c

    def _grid(self, parent):
        g = QGridLayout(parent)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(6)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        g.setRowStretch(20, 1)
        return g

    def _add_field(self, g, row, col, text, w):
        g.addWidget(label(text, "fieldLabel"), row * 2, col)
        g.addWidget(w, row * 2 + 1, col)
        if row * 2 + 1 >= 1:
            g.setRowMinimumHeight(row * 2 + 2, 6)

    def _build_save_card(self):
        c = card()
        v = QVBoxLayout(c)
        v.setContentsMargins(18, 16, 18, 16)
        v.setSpacing(10)
        v.addWidget(label("SAVE TO", "section"))
        row = QHBoxLayout()
        row.setSpacing(10)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Choose a folder")
        self.browse_btn = QPushButton("  Browse")
        self.browse_btn.clicked.connect(self.browse)
        self.open_dir_btn = QPushButton()
        self.open_dir_btn.setToolTip("Open this folder")
        self.open_dir_btn.clicked.connect(self.open_folder)
        row.addWidget(self.path_edit, 1)
        row.addWidget(self.browse_btn)
        row.addWidget(self.open_dir_btn)
        v.addLayout(row)
        return c

    def _build_action_card(self):
        c = card()
        v = QVBoxLayout(c)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(12)
        prow = QHBoxLayout()
        prow.setSpacing(12)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.pct_lbl = label("", "pct")
        self.pct_lbl.setMinimumWidth(48)
        self.pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        prow.addWidget(self.progress, 1)
        prow.addWidget(self.pct_lbl)
        v.addLayout(prow)

        row = QHBoxLayout()
        row.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.status_head = label("Ready", "statusHead")
        self.status_detail = label("Fetch a video, pick your options, then press Download.", "statusDetail", wrap=True)
        col.addWidget(self.status_head)
        col.addWidget(self.status_detail)
        row.addLayout(col, 1)
        self.play_btn = QPushButton("  Play")
        self.play_btn.clicked.connect(self.play_file)
        self.show_btn = QPushButton("  Show in folder")
        self.show_btn.clicked.connect(self.show_file)
        self.cancel_btn = QPushButton("  Cancel")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self.cancel)
        self.download_btn = QPushButton("  Download")
        self.download_btn.setObjectName("primary")
        self.download_btn.setMinimumWidth(150)
        self.download_btn.setMinimumHeight(44)
        self.download_btn.clicked.connect(self.start_download)
        for b in (self.play_btn, self.show_btn, self.cancel_btn):
            b.setVisible(False)
        row.addWidget(self.play_btn)
        row.addWidget(self.show_btn)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.download_btn)
        v.addLayout(row)
        return c

    def _setup_accessibility(self):
        """Names for screen readers, and keyboard-only focus on buttons (a mouse click doesn't leave a focus ring)."""
        names = {
            self.url_edit: "Video or playlist link", self.path_edit: "Save folder",
            self.theme_btn: "Switch between light and dark theme",
            self.av_res: "Resolution", self.av_cont: "Format", self.av_codec: "Video codec", self.av_audio: "Audio quality",
            self.v_res: "Resolution", self.v_cont: "Format", self.v_codec: "Video codec",
            self.a_fmt: "Audio format", self.a_q: "Audio quality",
        }
        for w, n in names.items():
            w.setAccessibleName(n)
        for b in self.findChildren(QPushButton) + self.findChildren(QCheckBox):
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            if not b.accessibleName():
                b.setAccessibleName(b.text().strip() or b.toolTip())

    # ================================================================== theme
    def _is_dark(self):
        mode = self.s.value("theme", "dark")
        if mode == "system":
            sh = QGuiApplication.styleHints()
            try:
                return sh.colorScheme() != Qt.ColorScheme.Light
            except AttributeError:
                return True
        return mode != "light"

    def apply_theme(self):
        if getattr(self, "_applying_theme", False):
            return
        self._applying_theme = True
        try:
            self._apply_theme()
        finally:
            self._applying_theme = False

    def _apply_theme(self):
        # Tell Qt which scheme we use; Qt draws the Windows title bar from it (and would otherwise keep
        # re-applying the Windows colour scheme over ours).
        mode = self.s.value("theme", "dark")
        sh = QGuiApplication.styleHints()
        if hasattr(sh, "setColorScheme"):
            want = (Qt.ColorScheme.Unknown if mode == "system"
                    else Qt.ColorScheme.Light if mode == "light" else Qt.ColorScheme.Dark)
            if sh.colorScheme() != want or mode == "system":
                sh.setColorScheme(want)
        dark = self._is_dark()
        self.pal = palette(dark)
        QApplication.instance().setStyleSheet(build_stylesheet(self.pal, dark))
        p = self.pal
        m, t, w = p["muted"], p["text"], p["accent_text"]
        self.theme_btn.setIcon(I.glyph_icon(I.G_SUN if dark else I.G_MOON, t, 16))
        self.settings_btn.setIcon(I.glyph_icon(I.G_SETTINGS, t, 16))
        self.paste_btn.setIcon(I.glyph_icon(I.G_PASTE, t, 15))
        self.fetch_btn.setIcon(I.glyph_icon(I.G_SEARCH, w, 15, disabled_color=m))
        self.browse_btn.setIcon(I.glyph_icon(I.G_BROWSE, t, 15))
        self.open_dir_btn.setIcon(I.glyph_icon(I.G_OPEN, t, 15))
        self.open_dir_btn.setText("  Open")
        self.download_btn.setIcon(I.glyph_icon(I.G_DOWNLOAD, w, 17, disabled_color=m))
        self.cancel_btn.setIcon(I.glyph_icon(I.G_CANCEL, p["danger"], 13))
        self.play_btn.setIcon(I.glyph_icon(I.G_PLAY, t, 14))
        self.show_btn.setIcon(I.glyph_icon(I.G_BROWSE, t, 14))
        for b, g in zip(self.seg_buttons, (I.G_VIDEO, I.G_MUTE, I.G_AUDIO)):
            b.setIcon(I.glyph_icon(g, m, 16, on_color=w))
        self.empty_icon.setPixmap(I.glyph_pixmap(I.G_LINK, p["accent"], 34))
        self.thumb.placeholder = p["surface2"]
        self.thumb.update()
        set_title_bar(self, dark, p["bg"])
        f = self.download_btn.font()
        f.setPointSizeF(11)
        self.download_btn.setFont(f)

    def toggle_theme(self):
        self.s.setValue("theme", "light" if self._is_dark() else "dark")
        self.apply_theme()

    def showEvent(self, e):
        super().showEvent(e)
        set_title_bar(self, self._is_dark(), self.pal["bg"])

    # ================================================================== prefs
    def _load_prefs(self):
        self.path_edit.setText(self.s.value("outdir", default_download_dir()))
        mode = int(self.s.value("mode", 0))
        self.seg_buttons[mode].setChecked(True)
        self.pages.setCurrentIndex(mode)
        set_combo_data(self.av_cont, self.s.value("av_cont", "mp4"))
        set_combo_data(self.av_codec, self.s.value("av_codec", "h264"))
        set_combo_data(self.av_audio, int(self.s.value("av_audio", 0)))
        set_combo_data(self.v_cont, self.s.value("v_cont", "mp4"))
        set_combo_data(self.v_codec, self.s.value("v_codec", "h264"))
        set_combo_data(self.a_fmt, self.s.value("a_fmt", "mp3"))
        self._fill_audio_quality()
        set_combo_data(self.a_q, int(self.s.value("a_q", 192)))
        self.a_embed.setChecked(self.s.value("a_embed", True, type=bool))
        self._container_changed(self.av_cont, self.av_codec)
        self._container_changed(self.v_cont, self.v_codec)

    def _save_prefs(self):
        s = self.s
        s.setValue("outdir", self.path_edit.text().strip())
        s.setValue("mode", self.mode_group.checkedId())
        s.setValue("av_cont", self.av_cont.currentData())
        s.setValue("av_codec", self.av_codec.currentData())
        s.setValue("av_audio", self.av_audio.currentData())
        s.setValue("v_cont", self.v_cont.currentData())
        s.setValue("v_codec", self.v_codec.currentData())
        s.setValue("a_fmt", self.a_fmt.currentData())
        s.setValue("a_q", self.a_q.currentData())
        s.setValue("a_embed", self.a_embed.isChecked())

    def closeEvent(self, e):
        if self.job and self.busy:
            r = QMessageBox.question(self, APP_NAME, "A download is still running. Cancel it and quit?")
            if r != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
            self.job.cancel()
        self._save_prefs()
        super().closeEvent(e)

    def _check_tools(self):
        missing = [n for n in ("ffmpeg", "ffprobe") if not find_tool(n)]
        self.missing_tools = missing
        if missing:
            self._reset_status()
            self._set_has_info(self.analysis is not None)
            self.empty_title.setText("Setup incomplete")
            self.empty_title.setObjectName("errorText")
            self.empty_text.setText(f"Couldn't find {' and '.join(missing)}. Put the .exe files in the 'bin' folder next to the app.")
            self.empty_title.style().polish(self.empty_title)

    # ================================================================== fetch
    def paste_and_fetch(self):
        text = QGuiApplication.clipboard().text().strip()
        self._last_clip = text
        if text:
            self.url_edit.setText(text)
            self.fetch(force=True)
        else:
            self._link_error("Clipboard is empty", "Copy a YouTube link first, then press Paste.")

    def _link_error(self, title, text):
        """Show a link problem without throwing away a video that is already loaded."""
        self.url_edit.setFocus()
        if self.info is not None or self.fetcher is not None:
            self._status(title, text, "error")
        else:
            self._show_empty_error(title, text)

    def _url_edited(self, text):
        self._auto_timer.start()

    def _auto_fetch(self):
        if is_media_link(self.url_edit.text()):
            self.fetch()

    def fetch(self, force=False):
        if self.busy:
            return
        url, err = check_link(self.url_edit.text())
        if err:
            self._link_error(*err)
            return
        if not url:
            self.url_edit.setFocus()
            return
        if not force and url == self.url and (self.fetcher is not None or self.info is not None):
            return   # already loaded / loading this link
        if self.url_edit.text() != url:
            self.url_edit.setText(url)
        kind = playlist_kind(url)
        self._start_fetch(url, playlist=(kind == "playlist"))

    def _start_fetch(self, url, playlist):
        if self.fetcher:
            self.fetcher.abort()
            self.fetcher.deleteLater()
            self.fetcher = None
        self.url = url
        self.info = self.analysis = None
        self._set_has_info(False)
        self.info_stack.setCurrentIndex(1)
        self.fetch_bar.setVisible(True)
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("  Fetching…")
        self._reset_status()
        self.fetcher = FetchJob(url, playlist, self.s.value("cookies", "none"), self)
        self.fetcher.done.connect(self._fetched)
        self.fetcher.failed.connect(self._fetch_failed)
        self.fetcher.start()

    def _end_fetch(self):
        if self.fetcher:
            self.fetcher.deleteLater()
            self.fetcher = None
        self.fetch_bar.setVisible(False)
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("  Fetch")

    def _fetch_failed(self, msg):
        self._end_fetch()
        self._show_empty_error("Couldn't load this link", msg)

    def _show_empty_error(self, title, text):
        self.info_stack.setCurrentIndex(0)
        self.empty_title.setText(title)
        self.empty_title.setObjectName("errorText")
        self.empty_title.style().unpolish(self.empty_title)
        self.empty_title.style().polish(self.empty_title)
        self.empty_text.setText(text)
        self.empty_icon.setPixmap(I.glyph_pixmap(I.G_ERROR, self.pal["danger"], 30))

    def _fetched(self, info):
        self._end_fetch()
        self.info = info
        self.analysis = Analysis(info)
        a = self.analysis
        if not a.is_playlist and not a.videos and not a.audios:
            self._show_empty_error("No downloadable formats", "yt-dlp didn't find any streams. Try updating yt-dlp in Settings.")
            return

        title = info.get("title") or "Untitled"
        self.title_lbl.setText(title if len(title) <= 120 else title[:117] + "…")
        self.title_lbl.setToolTip(title)
        bits = []
        who = info.get("channel") or info.get("uploader")
        if who:
            bits.append(who)
        if info.get("view_count"):
            bits.append(f"{fmt_count(info['view_count'])} views")
        if fmt_date(info.get("upload_date")):
            bits.append(fmt_date(info.get("upload_date")))
        self.meta_lbl.setText("   ·   ".join(bits))

        badges = []
        if a.is_playlist:
            badges.append((f"Playlist  ·  {len(info.get('entries') or [])} videos", True))
        else:
            if a.max_res:
                tag = {4320: "8K", 2160: "4K", 1440: "2K", 1080: "Full HD", 720: "HD"}.get(a.max_res, f"{a.max_res}p")
                badges.append((f"Up to {tag}", True))
            if a.has_hfr:
                badges.append(("60 fps", False))
            if a.best_audio:
                badges.append((f"Audio {int(a.best_audio.get('abr') or a.best_audio.get('tbr') or 0)} kbps", False))
        self._set_badges(badges)

        self.thumb.clear()
        self.thumb.set_badge(fmt_duration(info.get("duration")) if not a.is_playlist else "")
        thumb_url = self._thumb_url(info)
        if thumb_url:
            req = QNetworkRequest(QUrl(thumb_url))
            req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
            self.nam.get(req)

        self.playlist_chk.blockSignals(True)
        self.playlist_chk.setChecked(False)
        self.playlist_chk.blockSignals(False)
        self.playlist_chk.setVisible(playlist_kind(self.url) == "both" and not a.is_playlist)

        self._fill_resolutions()
        self.info_stack.setCurrentIndex(2)
        self._set_has_info(True)
        self._options_changed()

    def _thumb_url(self, info):
        vid = info.get("id")
        if info.get("_type") == "playlist":
            entries = info.get("entries") or []
            vid = entries[0].get("id") if entries and isinstance(entries[0], dict) else None
            if not vid:
                th = info.get("thumbnails") or []
                return th[-1].get("url") if th else None
        if vid and (info.get("extractor_key", "").lower().startswith("youtube") or info.get("_type") == "playlist"):
            return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
        return info.get("thumbnail")

    def _thumb_loaded(self, reply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pix = QPixmap()
            if pix.loadFromData(bytes(reply.readAll())):
                self.thumb.set_image(pix)
        reply.deleteLater()

    def _set_badges(self, items):
        while self.badges.count():
            it = self.badges.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for text, accent in items:
            self.badges.addWidget(label(text, "badgeAccent" if accent else "badge"))
        self.badges.addStretch(1)

    def _fill_resolutions(self):
        a = self.analysis
        use_std = a.is_playlist or self.playlist_chk.isChecked()
        opts = Analysis.standard_res_options() if use_std else a.res_options
        for combo in (self.av_res, self.v_res):
            prev = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for lbl, r, fps in opts:
                combo.addItem(lbl, (r, fps))
            # default: previously used, else 1080p (or the best below it)
            want = prev
            idx = combo.findData(want) if want else -1
            if idx < 0:
                pref = int(self.s.value("res_pref", 1080))
                idx = next((i for i, (_, r, _f) in enumerate(opts) if r <= pref), 0)
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def _playlist_toggled(self, _):
        self._fill_resolutions()
        self._options_changed()

    def _set_has_info(self, has):
        self.options_card.setEnabled(not self.busy)
        self.download_btn.setEnabled(has and not self.busy and not self.missing_tools)
        if not has:
            self.est_size.setText("—")
            self.est_desc.setText("Options appear here once a video is loaded.")
            self.est_hint.setText("")
            self.est_hint.setVisible(False)

    # ================================================================== options
    def _mode_changed(self, i):
        self.pages.setCurrentIndex(i)
        self._options_changed()

    def _container_changed(self, cont, codec):
        webm = cont.currentData() == "webm"
        set_item_enabled(codec, "h264", not webm)
        if webm and codec.currentData() == "h264":
            set_combo_data(codec, "vp9")
        self._options_changed()

    def _fill_audio_quality(self):
        fmt = self.a_fmt.currentData()
        prev = self.a_q.currentData()
        self.a_q.blockSignals(True)
        self.a_q.clear()
        if fmt in ("flac", "wav"):
            self.a_q.addItem("Lossless", 0)
            self.a_q.setEnabled(False)
        elif fmt == "original":
            self.a_q.addItem("Same as source", 0)
            self.a_q.setEnabled(False)
        else:
            for lbl, q in (OPUS_Q if fmt == "opus" else LOSSY_Q):
                self.a_q.addItem(lbl, q)
            self.a_q.setEnabled(True)
            i = self.a_q.findData(prev)
            self.a_q.setCurrentIndex(i if i >= 0 else (1 if fmt != "opus" else 2))
        self.a_q.blockSignals(False)

    def _audio_format_changed(self):
        self._fill_audio_quality()
        self.a_embed.setEnabled(self.a_fmt.currentData() != "wav")
        self._options_changed()

    def current_spec(self):
        mode = ("av", "video", "audio")[max(0, self.mode_group.checkedId())]
        spec = dict(mode=mode, outdir=self.path_edit.text().strip(),
                    template=self.s.value("template", "title"),
                    cookies=self.s.value("cookies", "none"),
                    embed_meta=self.s.value("embed_meta", True, type=bool),
                    playlist_folder=self.s.value("playlist_folder", True, type=bool),
                    playlist=bool(self.analysis and (self.analysis.is_playlist or self.playlist_chk.isChecked())))
        if mode == "av":
            r = self.av_res.currentData() or (None, None)
            spec.update(res=r[0], fps=r[1], container=self.av_cont.currentData(), codec=self.av_codec.currentData(),
                        abr=self.av_audio.currentData() or None)
        elif mode == "video":
            r = self.v_res.currentData() or (None, None)
            spec.update(res=r[0], fps=r[1], container=self.v_cont.currentData(), codec=self.v_codec.currentData())
        else:
            spec.update(afmt=self.a_fmt.currentData(), aq=self.a_q.currentData() or 0,
                        embed_cover=self.a_embed.isChecked())
        return spec

    def _options_changed(self, *_):
        if not self.analysis:
            return
        est = self.analysis.estimate(self.current_spec())
        self.est = est
        size = est.get("size")
        self.est_size.setText(f"≈ {fmt_bytes(size)}" if size else "")
        self.est_desc.setText(est.get("desc", ""))
        w = est.get("warnings") or []
        self.est_hint.setText("\n".join(w))
        self.est_hint.setVisible(bool(w))

    # ================================================================== save location
    def browse(self):
        start = self.path_edit.text().strip() or default_download_dir()
        if not os.path.isdir(start):
            start = os.path.expanduser("~")
        d = QFileDialog.getExistingDirectory(self, "Choose where to save downloads", start)
        if d:
            self.path_edit.setText(os.path.normpath(d))
            self.s.setValue("outdir", self.path_edit.text())

    def open_folder(self):
        d = self.path_edit.text().strip()
        if d:
            os.makedirs(d, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(d))

    # ================================================================== download
    def _set_busy(self, busy):
        self.busy = busy
        for w in (self.url_edit, self.paste_btn, self.fetch_btn, self.path_edit, self.browse_btn, self.playlist_chk):
            w.setEnabled(not busy)
        self.options_card.setEnabled(not busy)
        self.download_btn.setVisible(not busy)
        self.download_btn.setEnabled(not busy and self.analysis is not None and not self.missing_tools)
        self.cancel_btn.setVisible(busy)
        self.cancel_btn.setEnabled(True)
        if busy:
            self.play_btn.setVisible(False)
            self.show_btn.setVisible(False)

    def _reset_status(self):
        if self.missing_tools:
            self._status("Setup incomplete",
                         f"Couldn't find {' and '.join(self.missing_tools)}, which downloads need. Put ffmpeg.exe and "
                         "ffprobe.exe in the 'bin' folder next to StreamGrab.exe, then restart the app.", "error")
        else:
            self._status("Ready", "Pick your options, then press Download.", None)
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.pct_lbl.setText("")
        self.play_btn.setVisible(False)
        self.show_btn.setVisible(False)

    def _status(self, head, detail, state):
        self.status_head.setText(head)
        self.status_head.setProperty("state", state or "")
        self.status_head.style().unpolish(self.status_head)
        self.status_head.style().polish(self.status_head)
        self.status_detail.setText(detail)

    def start_download(self):
        if not self.analysis or self.busy or self.missing_tools:
            return
        outdir = self.path_edit.text().strip()
        if not outdir:
            self.browse()
            outdir = self.path_edit.text().strip()
            if not outdir:
                return
        try:
            os.makedirs(outdir, exist_ok=True)
            probe = os.path.join(outdir, ".streamgrab_write_test")
            with open(probe, "w") as f:
                f.write("ok")
            os.remove(probe)
        except OSError:
            self._status("Can't save here", "That folder isn't writable. Choose another location.", "error")
            return
        self._save_prefs()
        spec = self.current_spec()
        target = predict_path(spec, self.info)
        if target and os.path.exists(target):
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("File already exists")
            box.setText(f"“{os.path.basename(target)}” is already in this folder.")
            box.setInformativeText("Replace it with the new download, or keep both files?")
            rep = box.addButton("Replace", QMessageBox.ButtonRole.AcceptRole)
            both = box.addButton("Keep both", QMessageBox.ButtonRole.ActionRole)
            box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(both)
            box.exec()
            clicked = box.clickedButton()
            if clicked is rep:
                spec["overwrite"] = True
            elif clicked is both:
                n = 2
                while True:
                    spec["name_suffix"] = f" ({n})"
                    p = predict_path(spec, self.info)
                    if not p or not os.path.exists(p):
                        break
                    n += 1
            else:
                return
        streams = (self.est or {}).get("streams", 2 if spec["mode"] == "av" else 1)
        self.last_files = []
        self.job = DownloadJob(self.url, spec, streams, info=self.info, parent=self)
        self.job.progress.connect(self._on_progress)
        self.job.done.connect(self._on_done)
        self._set_busy(True)
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.job.start()

    def cancel(self):
        if self.job:
            self.cancel_btn.setEnabled(False)
            self.job.cancel()

    def _on_progress(self, pct, head, detail):
        if pct < 0:
            self.progress.setRange(0, 0)
            self.pct_lbl.setText("")
        else:
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 1000)
            self.progress.setValue(int(pct * 10))
            self.pct_lbl.setText(f"{int(pct)}%")
        self._status(head, detail, None)

    def _on_done(self, ok, msg, files):
        self._set_busy(False)
        self.progress.setRange(0, 1000)
        job, self.job = self.job, None
        if job:
            job.deleteLater()
        if ok:
            self.progress.setValue(1000)
            self.pct_lbl.setText("100%")
            self.last_files = [f for f in files if os.path.exists(f)] or files
            if len(self.last_files) > 1:
                detail = f"{len(self.last_files)} files saved to {self.path_edit.text()}"
            elif self.last_files:
                detail = os.path.basename(self.last_files[-1])
            else:
                detail = "The file was already downloaded."
            if msg:
                detail += f"\n{msg}"
            self._status("Download complete", detail, "ok")
            self.play_btn.setVisible(len(self.last_files) == 1)
            self.show_btn.setVisible(bool(self.last_files))
            QApplication.alert(self)
        elif msg == "__cancelled__":
            self.progress.setValue(0)
            self.pct_lbl.setText("")
            if files:
                self._status("Download cancelled", "Some partial files couldn't be removed:\n"
                             + "\n".join(os.path.basename(f) for f in files[:3]), "error")
            else:
                self._status("Download cancelled", "Partial files were removed.", None)
        else:
            self.progress.setValue(0)
            self.pct_lbl.setText("")
            self._status("Download failed", msg, "error")

    def play_file(self):
        if self.last_files:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_files[-1]))

    def show_file(self):
        if self.last_files:
            reveal_in_explorer(self.last_files[-1])
        else:
            self.open_folder()

    # ================================================================== settings / misc
    def open_settings(self):
        dlg = SettingsDialog(self.s, self)
        dlg.changed.connect(self.apply_theme)
        QTimer.singleShot(0, lambda: set_title_bar(dlg, self._is_dark(), self.pal["bg"]))
        dlg.changed.connect(lambda: set_title_bar(dlg, self._is_dark(), self.pal["bg"]))
        dlg.exec()
        self._options_changed()

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasUrls() or md.hasText():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        text = md.urls()[0].toString() if md.hasUrls() else md.text()
        if text and not self.busy:
            self.url_edit.setText(text.strip())
            self.fetch(force=True)

    def changeEvent(self, e):
        super().changeEvent(e)
        if e.type() == e.Type.ActivationChange and self.isActiveWindow():
            clip = QGuiApplication.clipboard().text().strip()
            fresh = clip != getattr(self, "_last_clip", None)
            self._last_clip = clip
            # Fill only when the box is empty, nothing is happening, and the clipboard holds a link the
            # user hasn't seen here yet - never replace a link that was cleared or is being typed.
            if (fresh and is_media_link(clip) and not self.url_edit.text() and not self.busy
                    and clip != self.url):
                self.url_edit.setText(clip)
                self.url_edit.selectAll()
                self.fetch()
