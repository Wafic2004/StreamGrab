@echo off
REM Runs StreamGrab from source (no build needed)
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" run_streamgrab.py
