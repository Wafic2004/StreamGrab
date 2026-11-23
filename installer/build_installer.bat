@echo off
REM Builds installer\Output\StreamGrab_Setup_<version>.exe from dist\StreamGrab.
REM Run build.bat first (or pass /full to do both).
setlocal
cd /d "%~dp0"

if /i "%~1"=="/full" (
  call ..\build.bat || goto :error
)

if not exist "..\dist\StreamGrab\StreamGrab.exe" (
  echo dist\StreamGrab\StreamGrab.exe not found. Run build.bat first.
  goto :error
)
for %%T in (ffmpeg ffprobe deno) do (
  if not exist "..\dist\StreamGrab\bin\%%T.exe" (
    echo dist\StreamGrab\bin\%%T.exe is missing. Run build.bat first.
    goto :error
  )
)

REM Version comes from streamgrab\__init__.py
for /f "tokens=2 delims==" %%V in ('findstr /b "APP_VERSION" ..\streamgrab\__init__.py') do set "VER=%%~V"
set "VER=%VER: =%"
set "VER=%VER:"=%"

set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup 6 not found. Install it with:  winget install JRSoftware.InnoSetup
  goto :error
)

echo Building StreamGrab %VER% installer...
"%ISCC%" /Qp /DAppVersion=%VER% StreamGrab.iss || goto :error
echo.
echo Done!  installer\Output\StreamGrab_Setup_%VER%.exe
exit /b 0

:error
echo Installer build failed.
exit /b 1
