@echo off
REM Builds dist\StreamGrab\StreamGrab.exe (portable folder; yt-dlp is built in, FFmpeg + Deno go in bin\)
cd /d "%~dp0"
echo [1/3] Generating icon...
".venv\Scripts\python.exe" tools\make_icon.py || goto :error
echo [2/3] Building app...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean StreamGrab.spec || goto :error
echo [3/3] Copying helper tools...
robocopy bin "dist\StreamGrab\bin" ffmpeg.exe ffprobe.exe deno.exe /NFL /NDL /NJH /NJS >nul
if errorlevel 8 goto :error
echo.
echo Done!  Run: dist\StreamGrab\StreamGrab.exe
goto :eof
:error
echo Build failed.
exit /b 1
