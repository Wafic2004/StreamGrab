# bin\ — helper programs (not stored in Git)

Put these three files here before running `build.bat` or `Run StreamGrab (dev).bat`.
They are too large for GitHub (FFmpeg is ~217 MB), so they are not committed.

| File | Where to get it |
|---|---|
| `ffmpeg.exe`, `ffprobe.exe` | https://www.gyan.dev/ffmpeg/builds/ → **ffmpeg-release-full.7z** (or essentials), copy both from its `bin` folder |
| `deno.exe` | https://github.com/denoland/deno/releases → **deno-x86_64-pc-windows-msvc.zip** |

The app looks here first and then on your `PATH`.
