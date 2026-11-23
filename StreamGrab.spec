# PyInstaller build spec for StreamGrab  ->  dist\StreamGrab\StreamGrab.exe
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

YTDLP_DATAS = collect_data_files("yt_dlp_ejs") + copy_metadata("yt-dlp") + copy_metadata("yt-dlp-ejs")
YTDLP_HIDDEN = collect_submodules("yt_dlp") + collect_submodules("yt_dlp_ejs")

EXCLUDES = [
    "tkinter", "unittest", "pydoc_data", "test",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech", "PySide6.QtWebSockets", "PySide6.QtHttpServer",
]

a = Analysis(
    ["run_streamgrab.py"],
    pathex=[],
    binaries=[],
    datas=YTDLP_DATAS,
    hiddenimports=YTDLP_HIDDEN,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StreamGrab",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon="assets/streamgrab.ico",
    version=None,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="StreamGrab")
