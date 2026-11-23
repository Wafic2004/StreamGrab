"""Engine auto-update checks (v1.1).

Run with an OLDER yt-dlp installed than the newest on PyPI, e.g.
    .venv\\Scripts\\python.exe -m pip install yt-dlp==2026.10.21
    .venv\\Scripts\\python.exe tests\\test_engine_update.py OUTDIR [path\\to\\StreamGrab.exe]

Everything happens in a sandboxed %LOCALAPPDATA%, so the real app data is not touched.
With an exe path, the self-test checks are repeated against the packaged app (the case that matters:
PyInstaller's importer must not keep serving the bundled yt-dlp).
"""
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "qa_runs/engine")
EXE = sys.argv[2] if len(sys.argv) > 2 else None
SANDBOX = os.path.join(OUT, "_appdata")
shutil.rmtree(SANDBOX, ignore_errors=True)
os.makedirs(SANDBOX, exist_ok=True)
os.environ["LOCALAPPDATA"] = SANDBOX
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from streamgrab import engine  # noqa: E402

RESULTS = os.path.join(OUT, "engine_results.jsonl")
app = QCoreApplication([])


def record(case, ok, actual):
    row = {"case": case, "status": "Pass" if ok else "Fail", "actual": actual}
    print(json.dumps(row), flush=True)
    with open(RESULTS, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def run_updater():
    res = {}
    up = engine.EngineUpdater(silent=True)
    up.finished.connect(lambda ok, msg, inst: (res.update(ok=ok, msg=msg, inst=inst), app.quit()))
    up.start()
    QTimer.singleShot(240000, app.quit)
    app.exec()
    return res


def selftest_with(cmd):
    out = os.path.join(OUT, f"st_{int(time.time() * 1000)}.json")
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    subprocess.run(cmd + ["--engine-selftest", out], env=env, timeout=120)
    try:
        with open(out, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        return {"ok": False, "error": f"no result ({e})"}


def make_broken_wheel(version):
    path = os.path.join(engine.ENGINE_DIR, f"yt_dlp-{version}-py3-none-any.whl")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("yt_dlp/__init__.py", "raise ImportError('deliberately broken engine for testing')\n")
        z.writestr("yt_dlp/version.py", f"__version__ = '{version}'\n")
    return path


src_cmd = [sys.executable, "-m", "streamgrab"]
bundled = engine._bundled_version("yt_dlp", "yt-dlp")
print("bundled yt-dlp:", bundled, "| sandbox:", SANDBOX, flush=True)

# EU-01: the updater fetches the newer yt-dlp, checks its hash, self-tests it and records the check
t0 = time.time()
r = run_updater()
wheels = sorted(os.listdir(engine.ENGINE_DIR))
st = engine.engine_state()
newest = engine.newest_good_engine()
ok = r.get("ok") and any(w.startswith("yt_dlp-") and w.endswith(".whl") for w in wheels) \
    and engine._vkey(newest) > engine._vkey(bundled) and st.get("last_result") == "updated"
record("EU-01", ok, f"bundled {bundled} -> updater: ok={r.get('ok')} '{r.get('msg')}' in {time.time() - t0:.0f}s; "
                    f"engine folder {wheels}; state last_result={st.get('last_result')}")

# EU-02: a new process (download worker / next app start) loads the downloaded engine, not the bundled one
for label, cmd in (("source", src_cmd),) + ((("exe", [EXE]),) if EXE else ()):
    res = selftest_with(cmd)
    record(f"EU-02 ({label})", res.get("ok") and res.get("version") == newest and ".whl" in res.get("source", ""),
           f"self-test loaded yt-dlp {res.get('version')} from {res.get('source')}; ejs {res.get('ejs', res.get('ejs_error'))}")

# EU-03: running the updater again does nothing (already up to date) and keeps working
r = run_updater()
record("EU-03", r.get("ok") and not r.get("inst"), f"second check: ok={r.get('ok')} '{r.get('msg')}'")

# EU-04: a broken newer engine is caught by the self-test ...
broken = make_broken_wheel("2099.1.1")
for label, cmd in (("source", src_cmd),) + ((("exe", [EXE]),) if EXE else ()):
    res = selftest_with(cmd)
    record(f"EU-04 ({label})", not res.get("ok") and "deliberately broken" in res.get("error", ""),
           f"self-test with broken 2099.1.1 wheel: ok={res.get('ok')} error={res.get('error')}")

# EU-05: ... and once it's on the bad list it is skipped, falling back to the last good engine
st = engine.engine_state()
st.setdefault("bad", []).append(os.path.basename(broken))
engine.save_engine_state(st)
for label, cmd in (("source", src_cmd),) + ((("exe", [EXE]),) if EXE else ()):
    res = selftest_with(cmd)
    record(f"EU-05 ({label})", res.get("ok") and res.get("version") == newest,
           f"broken wheel marked bad -> self-test loaded {res.get('version')} (expected {newest})")
os.remove(broken)

# EU-06: breakage detection - errors that mean "YouTube changed something" trigger the repair check
samples = {
    "ERROR: [youtube] abc: Unable to extract initial player response; please report this issue": True,
    "ERROR: [youtube] abc: Signature extraction failed: Some formats may be missing": True,
    "ERROR: [youtube] abc: Video unavailable. This video is private": False,
    "ERROR: unable to download video data: HTTP Error 404: Not Found": False,
}
wrong = [s for s, want in samples.items() if engine.looks_like_engine_breakage(s) != want]
record("EU-06", not wrong, "all classified correctly" if not wrong else f"misclassified: {wrong}")
print("finished", flush=True)
