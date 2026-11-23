from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QCheckBox,
                               QPushButton, QFrame, QListView, QWidget, QScrollArea)

from . import APP_NAME, APP_VERSION
import time

from .engine import EngineUpdater, engine_version, engine_state, newest_good_engine
from .utils import find_tool, portable_state, app_dir

THEMES = [("Dark", "dark"), ("Light", "light"), ("Match Windows", "system")]
FILENAMES = [
    ("Title", "title"),
    ("Title [1080p]", "title_res"),
    ("Channel - Title", "channel_title"),
    ("Upload date - Title", "date_title"),
]
PARALLEL = [("1 at a time", 1), ("2 at a time", 2), ("3 at a time", 3), ("4 at a time", 4)]
EXISTS = [("Ask me", "ask"), ("Keep both (add a number)", "keep"), ("Replace the old file", "replace"),
          ("Skip the download", "skip")]
BROWSERS = [("Off", "none"), ("Firefox", "firefox"), ("Chrome", "chrome"), ("Edge", "edge"),
            ("Brave", "brave"), ("Opera", "opera")]


def combo(items, current):
    c = QComboBox()
    c.setView(QListView())
    for label, data in items:
        c.addItem(label, data)
    i = c.findData(current)
    c.setCurrentIndex(max(0, i))
    return c


def card(title):
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(18, 16, 18, 18)
    lay.setSpacing(12)
    t = QLabel(title.upper())
    t.setObjectName("section")
    lay.addWidget(t)
    return f, lay


def field(text):
    l = QLabel(text)
    l.setObjectName("fieldLabel")
    return l


class SettingsDialog(QDialog):
    changed = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s = settings
        self.installed = []
        self.setWindowTitle(f"{APP_NAME} Settings")
        self.setModal(True)
        self.setMinimumWidth(520)
        root = QWidget(self)
        root.setObjectName("dialogRoot")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 16)
        lay.setSpacing(12)
        # Cards scroll when the screen is short (small laptops, 125-150% scaling); Done stays visible.
        content = QWidget()
        content.setObjectName("dialogRoot")
        body = QVBoxLayout(content)
        body.setContentsMargins(20, 20, 20, 4)
        body.setSpacing(14)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        scroll.setWidget(content)
        scroll.viewport().setObjectName("dialogRoot")
        lay.addWidget(scroll, 1)

        # Appearance + files
        c, cl = card("General")
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        self.theme = combo(THEMES, self.s.value("theme", "dark"))
        self.fname = combo(FILENAMES, self.s.value("template", "title"))
        g.addWidget(field("Theme"), 0, 0)
        g.addWidget(self.theme, 0, 1)
        g.addWidget(field("File name"), 1, 0)
        g.addWidget(self.fname, 1, 1)
        g.setColumnStretch(1, 1)
        cl.addLayout(g)
        self.pl_folder = QCheckBox("Save playlists into their own folder")
        self.pl_folder.setChecked(self.s.value("playlist_folder", True, type=bool))
        self.meta = QCheckBox("Embed title, channel and date into video files")
        self.meta.setChecked(self.s.value("embed_meta", True, type=bool))
        cl.addWidget(self.pl_folder)
        cl.addWidget(self.meta)
        body.addWidget(c)

        # Downloads / queue
        c, cl = card("Downloads")
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        self.parallel = combo(PARALLEL, int(self.s.value("parallel", 2)))
        self.exists = combo(EXISTS, self.s.value("exists", "ask"))
        g.addWidget(field("Downloads at the same time"), 0, 0)
        g.addWidget(self.parallel, 0, 1)
        g.addWidget(field("If the file already exists"), 1, 0)
        g.addWidget(self.exists, 1, 1)
        g.setColumnStretch(1, 1)
        cl.addLayout(g)
        hint = QLabel("More than 2–3 at once rarely makes things faster and can make YouTube ask "
                      "“confirm you're not a bot”.")
        hint.setObjectName("emptyText")
        hint.setWordWrap(True)
        cl.addWidget(hint)
        body.addWidget(c)

        # Cookies
        c, cl = card("Sign-in")
        row = QHBoxLayout()
        row.addWidget(field("Use cookies from browser"))
        row.addStretch(1)
        self.cookies = combo(BROWSERS, self.s.value("cookies", "none"))
        self.cookies.setMinimumWidth(160)
        row.addWidget(self.cookies)
        cl.addLayout(row)
        hint = QLabel("Fixes age-restricted videos and “confirm you're not a bot” errors. You need to be signed in "
                      "to YouTube in that browser. Chrome and Edge must be fully closed while downloading.")
        hint.setObjectName("emptyText")
        hint.setWordWrap(True)
        cl.addWidget(hint)
        body.addWidget(c)

        # Engine
        c, cl = card("Download engine")
        self.ver = QLabel(f"yt-dlp: {engine_version()}   ·   fast mode on")
        self.ver.setObjectName("meta")
        tools = []
        for name in ("ffmpeg", "deno"):
            tools.append(f"{name}: {'found ✓' if find_tool(name) else 'missing ✗'}")
        self.tools = QLabel("   ·   ".join(tools))
        self.tools.setObjectName("meta")
        row = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(self.ver)
        col.addWidget(self.tools)
        row.addLayout(col, 1)
        self.update_btn = QPushButton("Check for updates")
        self.update_btn.clicked.connect(self.update_ytdlp)
        row.addWidget(self.update_btn)
        cl.addLayout(row)
        self.update_status = QLabel(self._last_check_text())
        self.update_status.setObjectName("emptyText")
        self.update_status.setWordWrap(True)
        cl.addWidget(self.update_status)
        self.auto_engine = QCheckBox("Update the download engine automatically (recommended)")
        self.auto_engine.setChecked(self.s.value("auto_engine", True, type=bool))
        self.app_updates = QCheckBox("Tell me when a new version of StreamGrab is out")
        self.app_updates.setChecked(self.s.value("notify_app_updates", True, type=bool))
        cl.addWidget(self.auto_engine)
        cl.addWidget(self.app_updates)
        body.addWidget(c)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(20, 0, 20, 0)
        mode = {"on": "   ·   portable", "readonly": "   ·   portable mode off (read-only folder)"}.get(
            portable_state(), "")
        about = QLabel(f"{APP_NAME} {APP_VERSION}{mode}   ·   powered by yt-dlp and FFmpeg")
        if portable_state() == "on":
            about.setToolTip(f"Settings and data are kept in {app_dir()}")
        about.setObjectName("meta")
        bottom.addWidget(about)
        bottom.addStretch(1)
        done = QPushButton("Done")
        done.setObjectName("primary")
        done.clicked.connect(self.accept)
        bottom.addWidget(done)
        lay.addLayout(bottom)

        for b in self.findChildren(QPushButton) + self.findChildren(QCheckBox):
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.theme.setAccessibleName("Theme")
        self.fname.setAccessibleName("File name")
        self.cookies.setAccessibleName("Use cookies from browser")
        self.parallel.setAccessibleName("Downloads at the same time")
        self.exists.setAccessibleName("If the file already exists")
        scr = (parent.screen() if parent is not None else None) or QGuiApplication.primaryScreen()
        avail = scr.availableGeometry().height()
        scroll.setMinimumHeight(min(content.sizeHint().height() + 2, max(220, avail - 150)))

        for w in (self.theme, self.fname, self.cookies, self.parallel, self.exists):
            w.currentIndexChanged.connect(self._save)
        for w in (self.pl_folder, self.meta, self.auto_engine, self.app_updates):
            w.toggled.connect(self._save)

    def _save(self):
        self.s.setValue("theme", self.theme.currentData())
        self.s.setValue("template", self.fname.currentData())
        self.s.setValue("cookies", self.cookies.currentData())
        self.s.setValue("playlist_folder", self.pl_folder.isChecked())
        self.s.setValue("embed_meta", self.meta.isChecked())
        self.s.setValue("parallel", self.parallel.currentData())
        self.s.setValue("exists", self.exists.currentData())
        self.s.setValue("auto_engine", self.auto_engine.isChecked())
        self.s.setValue("notify_app_updates", self.app_updates.isChecked())
        self.changed.emit()

    def _last_check_text(self):
        last = engine_state().get("last_check")
        if not last:
            return "YouTube changes often. StreamGrab checks for a newer engine once a day."
        mins = int((time.time() - last) / 60)
        when = "just now" if mins < 1 else f"{mins} min ago" if mins < 60 else \
            f"{mins // 60} h ago" if mins < 48 * 60 else f"{mins // 1440} days ago"
        newest = newest_good_engine()
        extra = f"  ·  {newest} downloaded, used after a restart" if newest != engine_version() else ""
        return f"Last checked {when}.{extra}"

    def update_ytdlp(self):
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Checking…")
        self.update_status.setText("Looking for the latest yt-dlp release…")
        self._upd = EngineUpdater(self)
        self._upd.finished.connect(self._updated)
        self._upd.start()

    def _updated(self, ok, msg, installed):
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Check for updates")
        self.update_status.setText(msg)
        self.installed += installed
