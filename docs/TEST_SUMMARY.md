# StreamGrab test summary

Full details: [StreamGrab_Test_Cases.xlsx](StreamGrab_Test_Cases.xlsx) · Plan: [StreamGrab Test Plan.pdf](StreamGrab%20Test%20Plan.pdf)

Test environment: Windows 10 22H2 (build 19045), 1366×768, yt-dlp 2026.10.26 (2026.10.21 for the engine-update tests), FFmpeg 9.0.2, Deno 2.9.8.
Test data: public Blender Foundation videos (Big Buck Bunny 4K60, Blender HQ playlist), "Me at the zoo" and a Blender Short.

## Results by cycle

| Cycle | Build | Executed | Pass | Fail | Blocked | Not run | Defects found | Open at end |
|---|---|---|---|---|---|---|---|---|
| 1 | 1.0.0 | 83 | 78 | 4 | 1 | 18 | 9 | 9 |
| 2 | 1.0.1 | 101 | 94 | 0 | 7 | 0 | 7 | 0 |
| 3 | 1.1.0 | 129 | **121** | **0** | 8 | 1 | 9 | **0** |

Cycle 3 added 29 cases for the three new features (download queue, engine updates, portable mode) and re-ran every
existing case the changes touch: all download modes, progress, cancel, playlists, the existing-file prompt, settings,
error handling and performance. Cases the changes don't touch keep their 1.0.1 result (marked as such in the workbook).

## New in 1.1.0: what was tested

| Area | Cases | How |
|---|---|---|
| Download queue | QU-01 … QU-14 | App (UI) and `tests/test_queue.py`: 2 at a time, cancel one, pause/resume from the partial file, closing and reopening mid-download, worker killed, file-exists rules, playlists split per video, two downloads into the same name, restore then add more |
| Engine updates | EU-01 … EU-09 | `tests/test_engine_update.py` with an older yt-dlp bundled, from source **and in the packaged exe**: update downloaded, SHA-256 checked, self-tested, used by new downloads; broken engine rejected and skipped; YouTube-change errors detected. Daily check + "Restart now" tested in the app |
| Portable mode | PT-01 … PT-06 | Portable zip run from a test folder: settings in `StreamGrab.ini`, data in `data\`, registry and AppData unchanged; read-only folder falls back to normal mode; engine updates stay in the folder |

## Defects found in cycle 3 (all fixed in 1.1.0)

| ID | Severity | Problem | Fix |
|---|---|---|---|
| BUG-017 | Medium | A download finishing while the app closed was downloaded again after restart ("(2)" duplicate) | Late messages after closing are ignored; real state saved |
| BUG-018 | Low | Paused download lost its progress bar | Last progress kept |
| BUG-019 | Medium | No way to resume one paused download | Resume button on each row |
| BUG-020 | Medium | Several copied links auto-filled as one "link" at start | Auto-fill ignores text with line breaks |
| BUG-021 | Low | "Didn't finish last time" notice stayed after opening the Queue tab | Notice closes there |
| BUG-022 | Low | Audio size estimate left out the cover art (since 1.0.0; 4–26% low) | Cover counted; estimates within 2% |
| BUG-023 | Medium | Two downloads started together picked the same "(2)" name; resume picked a new one | Names reserved while downloading; chosen name saved |
| BUG-024 | Medium | Downloads took 7–9 s to start (target 3 s) | Only the named thumbnail fetched + a worker kept ready: 1.6–1.9 s |
| BUG-025 | Medium | After restoring unfinished downloads, new ones never started | Pausing is per item; new downloads always start |

## Highlights

- Every download mode and format re-verified with ffprobe (27 runner cases), including 4K60 and AV1.
- Size estimates: video within 1%, audio within 2% (was up to 26% low).
- Downloads start in 1.6–1.9 s and run at full line speed (6.0–6.2 MB/s); links load in about 2.2 s.
- 9 automated queue scenarios and 9 engine-update checks pass on the final code.
- The packaged exe loads an updated engine from its data folder, so YouTube changes can be fixed without a new release.

## Still blocked (need other hardware or a person)

| Case | Needs |
|---|---|
| QU-13 (Low) | A person to watch for the Windows notification when downloads finish (the taskbar flash was verified) |
| CP-01 (Critical) | A clean PC / VM without Python |
| CP-02 (High) | A real Windows 11 high-DPI screen (125% scaling was simulated and passes) |
| ST-02 | Changing the Windows theme |
| ST-08 | Browser fully closed while signed in to YouTube (cookie test) |
| ER-03 | A private test video |
| ER-06 | A nearly full USB drive |
| US-01 | A first-time human tester |

## Installer and portable zip (1.1.0)

- **StreamGrab_Setup_1.1.0.exe** (184 MB): 1.0.1 installed, then upgraded to 1.1.0 while 1.0.1 was running (closed
  automatically). Uninstall entry shows 1.1.0; settings kept; the installed app passes the engine self-test; uninstalls cleanly.
- **StreamGrab_Portable_1.1.0.zip** (268 MB): unzipped and run from a test folder; settings in `StreamGrab.ini`, data in
  `data\`; registry and AppData unchanged; folder moved and settings came along; deleting `portable.txt` switches back to
  normal mode. From a read-only folder it runs in normal mode with a notice.

Not run yet: EU-09 (new-version notice) needs the 1.1.0 release to be published first.

## Earlier cycles

Cycle 2 (1.0.1) closed all 16 defects from 1.0.0 (BUG-001 … BUG-016); see the Defect Log sheet.
