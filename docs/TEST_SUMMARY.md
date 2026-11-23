# StreamGrab test summary

Full details: [StreamGrab_Test_Cases.xlsx](StreamGrab_Test_Cases.xlsx) · Plan: [StreamGrab Test Plan.pdf](StreamGrab%20Test%20Plan.pdf)

Test environment: Windows 10 22H2 (build 19045), 1366×768, yt-dlp 2026.10.26, FFmpeg 9.0.2, Deno 2.9.8.
Test data: public Blender Foundation videos (Big Buck Bunny 4K60, Blender HQ playlist) and "Me at the zoo".

## Results by cycle

| Cycle | Build | Executed | Pass | Fail | Blocked | Not run | Defects found | Open at end |
|---|---|---|---|---|---|---|---|---|
| 1 | 1.0.0 | 83 | 78 | 4 | 1 | 18 | 9 | 9 |
| 2 | 1.0.1 | 101 | **94** | **0** | 7 | **0** | 7 | **0** |

All 16 defects are fixed in 1.0.1 and were retested.

## Results by area (1.0.1)

| Area | Cases | Pass | Blocked |
|---|---|---|---|
| Loading links | 15 | 15 | 0 |
| Video + Audio | 10 | 10 | 0 |
| Video only | 4 | 4 | 0 |
| Audio only | 12 | 12 | 0 |
| Save location | 9 | 9 | 0 |
| Progress | 7 | 7 | 0 |
| Cancel | 5 | 5 | 0 |
| Playlists | 7 | 7 | 0 |
| Settings | 9 | 7 | 2 |
| Error handling | 8 | 6 | 2 |
| Performance | 7 | 7 | 0 |
| Compatibility | 5 | 3 | 2 |
| Usability | 3 | 2 | 1 |
| **Total** | **101** | **94** | **7** |

## Defects (all closed)

| ID | Severity | Problem | Fix in 1.0.1 |
|---|---|---|---|
| BUG-001 | Low | Non-link text became "https://…" with a technical error | Plain "That doesn't look like a link" message |
| BUG-002 | Low | Audio quality ignored for M4A/AAC/Opus | Chosen bitrate is now really used |
| BUG-003 | Medium | Re-download silently kept the old file | "File already exists": Replace / Keep both / Cancel |
| BUG-004 | Low | Title bar didn't follow theme until restart | Repaints immediately |
| BUG-005 | Medium | Clipboard auto-fill could replace a typed link | Only fills links that are new on the clipboard |
| BUG-006 | Low | Raw "unavailable video" error text | Friendly message |
| BUG-007 | Low | "Clipboard is empty" hid the loaded video | Shown in the status area |
| BUG-008 | Medium | Cancel during merge/convert left temp files | Everything the job created is removed |
| BUG-009 | Low | AVI conversion labelled "Merging" | "Converting to AVI" |
| BUG-010 | Medium | No visible keyboard focus | Focus outline on every control |
| BUG-011 | Low | Controls unnamed for screen readers | Accessible names added |
| BUG-012 | Medium | FFmpeg-missing warning hidden; Download still enabled | Persistent warning, Download disabled |
| BUG-013 | Low | Focus started on the theme button | Starts in the link box |
| BUG-014 | Low | Raw WinError text when update check is offline | "No internet connection" |
| BUG-015 | High | Lost connection mid-download reported as "complete" | Reported as failed; retry resumes |
| BUG-016 | Medium | Settings taller than the screen at 125% scaling | Settings scrolls; Done always visible |

## Highlights

- Every download mode and format verified with ffprobe, including 4K60 AV1; size estimates within 1%.
- Link loading about 2.3 s (median); downloads run at full line speed (5.3 MB/s vs 4.4–6.4 MB/s speed test).
- 20 downloads in one session: no failures, memory flat at ~87 MB.
- Network loss and offline tests were simulated with a local proxy (`tests/netsim.py`).

## Still blocked (need other hardware or a person)

| Case | Needs |
|---|---|
| CP-01 (Critical) | A clean PC / VM without Python |
| CP-02 (High) | A real Windows 11 high-DPI screen (125% scaling was simulated and passes) |
| ST-02 | Changing the Windows theme |
| ST-08 | Browser fully closed while signed in to YouTube (cookie test) |
| ER-03 | A private test video |
| ER-06 | A nearly full USB drive |
| US-01 | A first-time human tester |

## Installer (StreamGrab_Setup_1.0.1.exe)

Checked on the same PC: fresh install (per-user, no admin), app runs with nothing else on PATH, upgrade while the
app is open (closes it automatically), and uninstall while the app is open (offers to close it; removes all program
files and shortcuts; settings kept on request; downloads never touched).
