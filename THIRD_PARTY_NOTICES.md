# Third-party software

StreamGrab's own code is MIT-licensed (see `LICENSE`). The Windows build and the setup file also
contain the programs below. Each keeps its own license; StreamGrab runs FFmpeg, FFprobe and Deno as
separate programs and does not modify them.

| Component | Version in 1.0.1 | License | Source / home page |
|---|---|---|---|
| yt-dlp | 2026.10.26 | The Unlicense (public domain) | https://github.com/yt-dlp/yt-dlp |
| yt-dlp-ejs | 0.8.0 | The Unlicense | https://github.com/yt-dlp/ejs |
| FFmpeg / FFprobe (gyan.dev "full" build) | 9.0.2 | GPL-3.0 (this build includes GPL components) | https://ffmpeg.org/download.html#get-sources · build: https://www.gyan.dev/ffmpeg/builds/ |
| Deno | 2.9.8 | MIT | https://github.com/denoland/deno |
| Qt for Python (PySide6, Shiboken6) | 6.12.0 | LGPL-3.0 | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| Qt 6 libraries | 6.12 | LGPL-3.0 | https://download.qt.io/archive/qt/ |
| Python | 3.13.7 | PSF License | https://www.python.org/downloads/source/ |
| mutagen | 1.48.1 | GPL-2.0-or-later (used only by the test scripts, not shipped) | https://github.com/quodlibet/mutagen |
| certifi, requests, urllib3, websockets, brotli, pycryptodomex | see `requirements.txt` | MPL-2.0 / Apache-2.0 / MIT / BSD | PyPI |
| PyInstaller (build tool, bootloader is shipped) | 6.22.3 | GPL-2.0 with bootloader exception | https://github.com/pyinstaller/pyinstaller |
| Inno Setup (installer builder) | 6 | Inno Setup License | https://jrsoftware.org/isinfo.php |
| Inter / Segoe UI fonts | — | not bundled; system fonts are used | — |

**FFmpeg source:** the setup file ships unmodified FFmpeg binaries. Their complete corresponding source code
is available from https://ffmpeg.org/download.html#get-sources (FFmpeg 9.0.2) and the build
configuration from https://www.gyan.dev/ffmpeg/builds/. If you cannot get it there, open an issue in this
repository and a copy will be provided.

**Qt (LGPL):** Qt is used through its unmodified shared libraries (`_internal\PySide6\*.dll`). You may
replace them with your own build of the same version.
