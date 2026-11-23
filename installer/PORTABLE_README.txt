StreamGrab - portable version
=============================

No installation needed.

1. Unzip this folder anywhere you can write to: Desktop, Documents, a USB stick...
   (Not inside "Program Files": that folder is read-only, so portable mode can't save there.)
2. Double-click StreamGrab.exe.

Everything StreamGrab needs is in this folder: the download engine, FFmpeg and Deno.

Where things are kept
- Settings:                  StreamGrab.ini (next to StreamGrab.exe)
- Download queue, engine
  updates and logs:          the "data" folder
- Your downloaded videos:    wherever you choose in the app (Downloads\StreamGrab by default)

Nothing is written to the PC's registry or AppData. To remove StreamGrab, delete this folder.
To carry it to another PC, copy the whole folder: your settings and queue come along.

If Windows SmartScreen says "Windows protected your PC", click "More info" then "Run anyway".
This happens because the app isn't code-signed; it's open source:
https://github.com/Wafic2004/StreamGrab
