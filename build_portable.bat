@echo off
REM Makes the portable version: installer\Output\StreamGrab_Portable_<version>.zip
REM Run build.bat first (it creates dist\StreamGrab).
setlocal
cd /d "%~dp0"
if not exist "dist\StreamGrab\StreamGrab.exe" (
    echo dist\StreamGrab\StreamGrab.exe not found - run build.bat first.
    exit /b 1
)
for /f "tokens=2 delims==" %%v in ('findstr /b "APP_VERSION" streamgrab\__init__.py') do set "VER=%%~v"
set "VER=%VER: =%"
set "VER=%VER:"=%"
if "%VER%"=="" (
    echo Couldn't read the version from streamgrab\__init__.py
    exit /b 1
)
set "STAGE=build\portable\StreamGrab"
set "ZIP=installer\Output\StreamGrab_Portable_%VER%.zip"

echo [1/3] Copying the app...
if exist "build\portable" rmdir /s /q "build\portable"
robocopy "dist\StreamGrab" "%STAGE%" /E /NFL /NDL /NJH /NJS /XD data >nul
if errorlevel 8 goto :error
if exist "%STAGE%\StreamGrab.ini" del /q "%STAGE%\StreamGrab.ini"

echo [2/3] Adding the portable marker and instructions...
> "%STAGE%\portable.txt" (
    echo This file turns on portable mode. While it is here, StreamGrab keeps its settings
    echo in StreamGrab.ini and its data ^(queue, engine updates, logs^) in the "data" folder,
    echo all next to StreamGrab.exe - nothing is written to the PC.
    echo Delete this file to use the normal per-user settings instead.
)
copy /y "installer\PORTABLE_README.txt" "%STAGE%\README.txt" >nul || goto :error

echo [3/3] Zipping...
if not exist "installer\Output" mkdir "installer\Output"
if exist "%ZIP%" del /q "%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path 'build\portable\StreamGrab' -DestinationPath '%ZIP%' -CompressionLevel Optimal" || goto :error
powershell -NoProfile -Command "$f=[IO.File]::OpenRead('%ZIP%'); $h=[BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($f)).Replace('-','').ToLower(); $f.Close(); [IO.File]::WriteAllText('%ZIP%.sha256', $h + '  StreamGrab_Portable_%VER%.zip' + [Environment]::NewLine)" || goto :error
echo.
echo Done: %ZIP%
goto :eof
:error
echo Portable build failed.
exit /b 1
