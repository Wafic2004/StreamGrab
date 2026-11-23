# StreamGrab

A clean, modern Windows app for downloading YouTube videos, playlists and audio in the quality you choose. Powered by **yt-dlp** and **FFmpeg**. Free, no ads, no account.

![StreamGrab main window](docs/images/streamgrab.png)

## Download

**[⬇ Download the latest version](https://github.com/Wafic2004/StreamGrab/releases/latest)**. There are two ways to get it:

| | File | How |
|---|---|---|
| **Installer** (recommended) | `StreamGrab_Setup_1.1.0.exe` | Run it and click **Next → Next → Install**. No administrator password needed. Adds Start menu / desktop shortcuts and an uninstaller. |
| **Portable** | `StreamGrab_Portable_1.1.0.zip` | Unzip anywhere you can write to (Desktop, a USB stick…) and run `StreamGrab.exe`. Nothing is installed; settings, the queue and engine updates stay inside that folder. Delete the folder to remove it. |

If Windows shows *"Windows protected your PC"*, click **More info → Run anyway** (StreamGrab isn't code-signed).

Everything StreamGrab needs is included (FFmpeg, Deno and the Python/Qt runtime), so nothing else has to be installed.
Requires 64-bit Windows 10 or 11 and about 670 MB of disk space.

## Features

| Mode | What you get | Formats | Quality choices |
|---|---|---|---|
| **Video + Audio** | Normal video with sound | MP4, MKV, WebM, MOV, AVI | Every resolution the video offers (144p to 4K/8K, 60 fps), codec (H.264 / VP9 / AV1), audio quality |
| **Video only** | Picture only, no sound track | MP4, MKV, WebM, MOV, AVI | Resolution, fps, codec |
| **Audio only** | Music / podcast file | MP3, M4A, AAC, Opus, OGG, FLAC, WAV, Original | 320 to 64 kbps, lossless, or untouched original |

New in 1.1:
- **Download queue**: keep adding videos while others download (2 at a time by default, up to 4). Pause, resume,
  cancel or retry each one; the **Queue** tab shows them all. Paste several links at once (Ctrl+V) to add them in one go.
  Playlists become one item per video. Unfinished downloads continue after closing the app, from where they stopped.
- **Automatic engine updates**: YouTube changes often and breaks downloaders. StreamGrab checks once a day for a new
  yt-dlp, tests it before using it (a broken update is never used), and checks straight away when an error looks like a
  YouTube change. New downloads use the update immediately; no reinstall needed.
- **Portable version**: see above.

Also:
- **Live size estimate** with the exact streams before you download, plus warnings (e.g. "H.264 isn't offered at 4K").
- **Save-to folder** (remembered) with Open folder, Show in folder and Play buttons. If the file already exists: ask, keep both, replace or skip (your choice in Settings).
- **Progress** with speed and time left; **Cancel** removes partial files.
- **Playlists**: paste a playlist link, or tick "Download the entire playlist" on a video inside one; files are numbered in a folder named after the playlist.
- **Cover art and tags** embedded into audio files.
- **Dark / light / match-Windows theme**, drag-and-drop links, clipboard detection, full keyboard support.
- **Settings**: file-name pattern, playlist subfolders, downloads at the same time, browser cookies (for age-restricted videos), automatic or one-click **engine update**.
- **Fast**: links load in about 2 s and downloads start in about 1–2 s.

**If downloads start failing** (YouTube changes often): StreamGrab normally fixes this itself. You can also press
Settings → **Check for updates**.

Please only download videos you have the right to save (your own uploads, Creative Commons, etc.) and respect YouTube's Terms of Service.

## Test documentation

StreamGrab went through three test cycles (1.0.0, 1.0.1 and 1.1.0). See [docs/TEST_SUMMARY.md](docs/TEST_SUMMARY.md).

| Document | Contents |
|---|---|
| [StreamGrab Test Plan.pdf](docs/StreamGrab%20Test%20Plan.pdf) | Scope, approach, environments, entry/exit criteria |
| [StreamGrab_Test_Cases.xlsx](docs/StreamGrab_Test_Cases.xlsx) | 130 test cases with results, defect log (25 defects, all closed), test data and cycle summary |
| [TEST_SUMMARY.md](docs/TEST_SUMMARY.md) | Results at a glance |

## Building from source

Requirements: Windows 10/11 x64, Python 3.13, and the three helper programs in `bin\` (see [bin/README.md](bin/README.md)).

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
"Run StreamGrab (dev).bat"          &REM run from source
build.bat                           &REM build dist\StreamGrab\StreamGrab.exe (portable folder)
installer\build_installer.bat       &REM build installer\Output\StreamGrab_Setup_<version>.exe
build_portable.bat                  &REM build installer\Output\StreamGrab_Portable_<version>.zip
```

The installer needs Inno Setup 6 (`winget install JRSoftware.InnoSetup`). `installer\build_installer.bat /full`
rebuilds the app first. The version number comes from `streamgrab\__init__.py`.

### Tests

```bat
.venv\Scripts\python tests\test_fixes.py                       &REM fast unit checks, no network
.venv\Scripts\python tests\run_cases.py OUT VA-01,AO-01,VO-01  &REM real downloads checked with ffprobe
.venv\Scripts\python tests\run_extra.py OUT CN-02,SV-09,ER-02  &REM cancel, existing file, network drop...
.venv\Scripts\python tests\test_queue.py OUT                    &REM queue: parallel, cancel, pause, restart, crash...
.venv\Scripts\python tests\test_engine_update.py OUT [exe]      &REM engine auto-update (install an older yt-dlp first)
```

`tests\netsim.py` is a tiny local proxy used to simulate the network dropping mid-download.

## Project layout

```
streamgrab\
  main.py              app start-up (fonts, icon, taskbar id); --worker / --engine-selftest modes
  window.py            main window UI
  downloads.py         download queue: runs each download in its own worker process, saves/restores the queue
  worker.py            the worker process (one download) and the engine self-test
  queue_view.py        Queue tab
  batch_dialog.py      "Add several links" window
  settings_dialog.py   settings window
  engine.py            runs yt-dlp in-process (fast client + fallback), progress, cancel, cleanup, updater
  formats.py           turns yt-dlp's format list into friendly options + size estimates
  theme.py             dark / light stylesheet
  icons.py             app logo + Windows Fluent glyph icons
  utils.py             link checks, formatting, file helpers, portable mode
installer\             Inno Setup script, wizard images, build script
tests\                 unit checks, download test runners, network simulator
docs\                  test plan, test cases workbook, test summary
bin\                   ffmpeg.exe, ffprobe.exe, deno.exe (not in Git, see bin\README.md)
```

## How it's fast

yt-dlp is loaded once and kept warm inside the app for loading links; each download runs in its own small worker
process, so several can run side by side and one failing can't take the app down. Fetches use YouTube's lightweight "visionos" client, which
needs no JavaScript challenge, and fall back to yt-dlp's full client set if that fails. Downloads reuse the fetched
info instead of asking YouTube again, and refresh the links automatically if they've expired. `deno.exe` is the
JavaScript runtime yt-dlp needs for the fallback path.

## License

StreamGrab is released under the [MIT License](LICENSE). Bundled third-party programs (FFmpeg, Deno, yt-dlp, Qt,
Python) keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Changes to this repository are made only by the maintainer. Bug reports and suggestions are welcome as
[issues](https://github.com/Wafic2004/StreamGrab/issues).
