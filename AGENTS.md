# AGENTS.md

## Cursor Cloud specific instructions

### What this project is
A Flask web app (Korean UI) for virtual clothing-fit visualization. The user enters
height/weight and (optionally) garment measurements + fabric mix; the backend picks an
avatar size (S/M/L), generates fit-analysis text, and runs a headless **Blender** pipeline
(shape-key export → cloth simulation → 4-view silhouette render) to produce PNGs that the
result page shows. There is a single service (the Flask app). Blender is invoked as a
subprocess, not a separate long-running service.

### Environment already set up by the update script
- Python deps live in the local virtualenv `.venv` (created/refreshed by the update script from `requirements.txt`). `requirements.txt` is not in the original repo — it was added during setup; the code also needs `numpy` and `scipy`, which the committed Windows `venv/` does not contain.
- The committed `venv/` is a **Windows** virtualenv and is unusable on Linux — ignore it; always use `.venv`.

### Non-obvious gotchas
- **`config.py` is gitignored and required.** `services/blender_runner.py` does `from config import ...`, and because the repo root is first on `sys.path` when running `app.py`, a root-level `config.py` overrides the committed `blender/config.py` (which hardcodes a Windows `BLENDER_PATH`). Setup created a root `config.py` pointing `BLENDER_PATH` to `/opt/blender/blender` (overridable via the `BLENDER_PATH` env var). If this file is missing the app will fall back to the Windows path and Blender calls fail. Recreate it if absent.
- **Blender must be installed at `/opt/blender/blender`** (Blender 4.4.x). It is NOT installed by the update script (large binary). If missing, download the Linux build (the official `download.blender.org` is behind a Cloudflare challenge that blocks scripted downloads — use a mirror such as `https://mirrors.ocf.berkeley.edu/blender/release/Blender4.4/blender-4.4.3-linux-x64.tar.xz`) and extract to `/opt/blender`. The `.blend` assets were authored in 4.4, so match that major version.
- **Headless rendering works without a GPU** via Blender's software renderer (llvmpipe). No `xvfb`/display is needed. It is slow: EEVEE renders ~15-25s per view, so a full fit request (4 views) takes ~60-90s end to end. `services/blender_runner.py` sets a 120s render timeout — keep that in mind when testing.

### Run / test
- Run the app (dev mode): `.venv/bin/python app.py` → serves on `http://127.0.0.1:5000` (Flask debug server; `use_reloader=False`).
- There is no lint config or automated test suite in the repo.
- Manual end-to-end check: `POST /api/fit/analyze` returns immediately with `job_id`, `avatar_size`, and fit text; the Blender pipeline runs in a background thread and streams progress over SSE at `/api/fit/progress/<job_id>`; rendered PNGs land in `outputs/<job_id>/` and are served at `/outputs/...`. The `outputs/` dir is gitignored and auto-cleaned (folders older than 30 min are deleted on each new request).
- Subprocess stdout from the Blender steps is only printed after each step completes, so the Flask console stays quiet during a run — watch `outputs/<job_id>/` for progress instead.
