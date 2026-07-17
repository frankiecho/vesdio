# Packaging VESDIO as a desktop app

VESDIO ships as a native-feeling desktop app rather than "a web page you have
to keep a browser tab open for": the Dash/Flask server still does all the
work, but it runs on a background thread and is displayed inside a native
[`pywebview`](https://pywebview.flowrl.com/) window instead of a browser tab.

**As of this workstream, the executable no longer bundles the EXIOBASE
dataset.** A single ingested reference year (with the dense Leontief/Ghosh
inverse matrices) is well over a gigabyte even at float32, which made for a
bloated, slow-to-download, hard-to-host executable (the only prior release
was a single 4.2 GB file, too big for a GitHub release asset). Instead, the
packaged app downloads the reference-year data **once, on first run**, from
per-matrix files attached to a GitHub Release, into a small, persistent
per-user data directory — see "First-run behavior" (§4) below. After that
first download, the app runs fully offline exactly as before.

This document covers:

1. How the pywebview launcher works (and its browser-tab fallback).
2. How to build the offline data bundle, and how to cut a **data release**
   for the first-run downloader to fetch from.
3. How to build the PyInstaller executable on Windows/macOS/Linux (now
   automated by `.github/workflows/build.yml`).
4. First-run behavior and troubleshooting.

---

## 1. The native window (`app.py` `__main__`)

The `if __name__ == '__main__':` block in `app.py` does the following:

- Starts `app.run(...)` (the Dash/Flask server) on a **background thread**,
  bound to `127.0.0.1:8050`, with the reloader and debug mode off (both are
  incompatible with owning a native window on the main thread).
- Imports `webview` and opens `webview.create_window("VESDIO", url, ...)`,
  then calls `webview.start()` on the main thread. `webview.start()` blocks
  until the window is closed, at which point the process exits (the server
  thread is a daemon thread, so it doesn't keep the process alive).

```python
import webview

def run_server():
    app.run(host=host, port=port, debug=False, use_reloader=False)

server_thread = Thread(target=run_server, daemon=True)
server_thread.start()
webview.create_window("VESDIO", url, width=1400, height=900, min_size=(1024, 700))
webview.start()
```

**Fallback:** if `pywebview` isn't installed, or isn't usable (e.g. no GUI
backend available, as in this repo's dev/CI sandbox), the `import webview`
raises `ImportError` and the app falls back to the previous behavior exactly:
open the default web browser at `http://127.0.0.1:8050` via
`webbrowser.open_new`, with the debug-mode/reloader guard preserved so a
`flask` debug-reload doesn't spawn two browser tabs. Nothing else about the
app changes in this mode — it's the same experience VESDIO had before
pywebview was added, so plain `python app.py` still works everywhere,
including headless dev containers.

pywebview needs a native GUI toolkit under the hood depending on OS. See
"Platform GUI backend dependencies" below.

---

## 2. Building the offline data bundle

The real blocker to "offline" isn't the UI — it's that `ingest_exiobase.py`
downloads tens of GB from Zenodo and takes significant time/CPU to compute
the dense Leontief (`L`) and Ghosh (`G`) inverses via `pymrio.calc_all()`.
Shipping the app with a pre-processed **reference year** (2021 by default)
avoids this entirely for most users; power users who want additional years
can still run the full ingestion pipeline themselves after install.

### What ships in the bundle

For a given reference `year`, the minimal offline bundle is:

```
data/
  exiobase/
    <year>/
      EXIOBASE_A.parquet        # technical coefficients
      EXIOBASE_L.parquet        # Leontief inverse (dense, largest file)
      EXIOBASE_G.parquet        # Ghosh inverse (dense, largest file; optional)
      EXIOBASE_Y.parquet        # final demand
      EXIOBASE_E.parquet        # land-use / environmental extension
      EXIOBASE_X.parquet        # gross output
      labels.json               # country/sector labels + default scenario
    production_history.parquet  # optional, powers the Historical tab
  ENCORE_data/
    encore_materiality.json     # optional, powers ecosystem-service shocks
```

This is exactly the `DATA_DIR` layout `vesdio.spec` already bundles under
`data/` inside the packaged app (see `get_base_data_path()` in
`src/data_loader.py`, which resolves `sys._MEIPASS/data` when frozen).

### `ingest_exiobase.py` — `build_distributable_bundle()`

`ingest_exiobase.py` now provides a helper that assembles the above layout
from an already-ingested year:

```python
from ingest_exiobase import ingest_and_save_exiobase, build_distributable_bundle

# 1. One-time, requires network + significant disk/CPU (unchanged behavior):
ingest_and_save_exiobase(year=2021)

# 2. Assemble the shippable bundle (float32 L/G by default):
build_distributable_bundle(year=2021)
```

`build_distributable_bundle(year=2021, output_dir=None, float32=True,
include_ghosh=True)`:

- Does **not** re-run the download/parse pipeline — it expects
  `ingest_and_save_exiobase(year)` to have already produced
  `data/exiobase/<year>/*.parquet` and `labels.json`.
- Copies `A`, `Y`, `E`, `X`, and `labels.json` unchanged.
- Re-saves `L` (and `G`, unless `include_ghosh=False`) at the requested
  dtype — by default downcast to **float32**, regardless of what dtype the
  source year directory was saved with.
- Copies `production_history.parquet` and `ENCORE_data/encore_materiality.json`
  if present (both optional; the app degrades gracefully without them).
- Writes everything under `output_dir` (default: `<DATA_DIR>/bundle/<year>`),
  in the same layout PyInstaller/`DATA_DIR` expects — point `DATA_DIR` (or
  `vesdio.spec`'s `datas` bundling) at this output directory to build the
  installer from it.

### float32 bundle size note

`L` and `G` are dense `N x N` matrices over the full EXIOBASE region-sector
space (~9,800 rows/columns for the `ixi` system), so each is roughly
**~512 MB at float64**. Storing them as **float32** halves that to
**~256 MB each** with negligible precision loss for this app's purposes
(percentage shocks and relative attribution, not audited financial figures).

This float32 behavior is also available directly in `ingest_and_save_exiobase`
(useful if you want the *ingested* year directory itself to already be
float32, not just the bundle copy):

```bash
BUNDLE_FLOAT32=1 python ingest_exiobase.py
```

or programmatically: `ingest_and_save_exiobase(year=2021, float32=True)`.
**Default behavior is unchanged** (float64) unless this flag is set
explicitly — existing ingested data and any other consumers of the parquet
files are unaffected.

### Optionally dropping G

If the packaged app is expected to primarily run Leontief (demand-side)
scenarios, pass `include_ghosh=False` to `build_distributable_bundle()` to
omit `G` entirely, roughly halving the bundle again. Supply-side ("ghosh")
scenarios will be unavailable offline in that build; this is a per-bundle
tradeoff, not a code-level restriction — `G` is still computed and saved
normally by `ingest_and_save_exiobase`.

### Bottom line on size

| Bundle contents                    | Approx. size (per year) |
|-------------------------------------|--------------------------|
| float64 L + G (current default)     | ~1.0 GB+                 |
| float32 L + G                       | ~500 MB                  |
| float32 L only (G dropped)          | ~250 MB                  |

(`A`, `Y`, `E`, `X`, labels, ENCORE materiality, and production history are
all comparatively small — low tens of MB combined.)

### Cutting a data release (for the first-run downloader)

Once you have an assembled bundle (above), `ingest_exiobase.py` provides a
second helper, `build_release_manifest()`, that turns it into the flat set
of files + `manifest.json` that `src/data_bootstrap.py`
(`ensure_reference_data()`) expects to find attached to a GitHub Release:

```python
from ingest_exiobase import build_distributable_bundle, build_release_manifest

bundle_dir = build_distributable_bundle(year=2021)      # as above
release_dir = build_release_manifest(bundle_dir, year=2021)  # -> bundle_dir/release/
```

This produces, in `release_dir`:

- `EXIOBASE_2021_A.parquet`, `..._L.parquet`, `..._G.parquet` (optional),
  `..._Y.parquet`, `..._E.parquet`, `..._X.parquet` — the per-year matrices,
  flat-renamed (GitHub release assets can't be nested in folders).
- `labels_2021.json` — the year's labels/defaults.
- `production_history.parquet`, `encore_materiality.json` — optional extras,
  kept under their original names.
- `manifest.json` — maps each of the above back to its on-disk target path
  (`exiobase/2021/EXIOBASE_A.parquet`, etc.), with a sha256 + byte size for
  verification and a `required` flag (false for `G`, `production_history`,
  `encore_materiality` — the app degrades gracefully without them).

**To publish:** create (or reuse) a GitHub Release on the `vesdio` repo and
upload every file `build_release_manifest()` printed, including
`manifest.json` itself, as release assets — e.g.:

```bash
gh release upload <tag> release/*.parquet release/*.json
```

The default downloader URL (`DATA_RELEASE_BASE_URL` in `src/config.py`) is
`https://github.com/frankiecho/vesdio/releases/latest/download/`, so
uploading to whichever release is currently tagged "latest" is sufficient
for the default configuration; pin a specific tag instead by overriding
`DATA_RELEASE_BASE_URL` (env var) if you need release/data versions to move
independently.

> **TODO before shipping a build**: the release named above must actually
> exist with these assets uploaded, or first-run users will see a failed
> download and fall back to the synthetic dummy dataset. See the `TODO` left
> in `src/config.py`.

---

## 3. Building the PyInstaller executable

`vesdio.spec` bundles `assets/` (icons, `design-system.css`, etc.) and the
metadata/hidden imports needed by pandas/pyarrow/dask/plotly/pywebview —
**it no longer bundles any EXIOBASE data** (the `(DATA_DIR, 'data')` `datas`
entry was removed; see §1 and §4). This is what keeps the executable itself
small; the reference dataset is fetched separately on first run.

### Steps (any platform)

```bash
# 1. Install build dependencies (in your build venv)
pip install -r requirements.txt pyinstaller

# 2. Build
pyinstaller vesdio.spec

# Output: dist/vesdio_dist/  (contains the vesdio executable + assets, no data/)
```

Distribute the whole `vesdio_dist/` directory (PyInstaller's `--onedir`
style, as configured via `COLLECT` in `vesdio.spec`) — the executable
depends on the sibling files/folders next to it.

**Automated builds:** `.github/workflows/build.yml` runs exactly this, on a
`windows-latest`/`macos-latest`/`ubuntu-latest` matrix, on
`workflow_dispatch` or a `v*` tag push (installing the right pywebview
native backend per OS first — see the table below). It uploads each OS's
zipped `vesdio_dist/` as a workflow artifact, and additionally attaches
them to the GitHub Release when triggered by a tag push. It does **not**
produce the data release (§2) — that's the maintainer's separate,
one-time-per-year step, uploaded to the same release as the executables.

### Platform GUI backend dependencies

`pywebview` needs a native GUI toolkit per OS; PyInstaller must be run
**on the target platform** (cross-compilation isn't supported), and the
right backend + its Python bindings must be installed **in the build venv**
so PyInstaller can discover and bundle them:

| Platform | Backend                         | Extra dependency               |
|----------|----------------------------------|---------------------------------|
| Windows  | WinForms (via `pythonnet`/`clr`) | `pip install pythonnet`         |
| macOS    | Cocoa/WebKit (via `pyobjc`)       | `pip install pyobjc`            |
| Linux    | GTK (WebKit2) or Qt (QtWebEngine) | `apt install python3-gi gir1.2-webkit2-4.0` (GTK) or `pip install PyQt5 PyQtWebEngine` (Qt) |

`vesdio.spec` picks the matching hidden-import set automatically based on
`sys.platform` at build time (see the `hiddenimports` block). If the packaged
app fails to open a window (but the server thread starts fine — check the
console/log output), it's almost always a missing native backend; install
the dependency above for your OS and rebuild.

### Icon / metadata

The spec already sets `icon='assets/favicon.ico'` and produces a
console-visible executable (`console=True`) for now, which is useful while
diagnosing packaging issues (e.g. missing GUI backend). Set `console=False`
once packaging is verified stable if a windowed (no console) build is
preferred.

---

## 4. First-run behavior

- **Persistent data directory.** `get_base_data_path()` (`src/paths.py`) now
  resolves to a per-user, persistent directory when frozen —
  `platformdirs.user_data_dir("VESDIO")` + a `data` subdir (e.g.
  `~/.local/share/VESDIO/data` on Linux, `~/Library/Application
  Support/VESDIO/data` on macOS, `%LOCALAPPDATA%\VESDIO\data` on Windows) —
  **not** `sys._MEIPASS`, which is a read-only temp extraction directory
  PyInstaller re-creates on every launch and would make any downloaded data
  disappear immediately. In a normal dev environment this is unchanged
  (`DATA_DIR`/`./data`). `VESDIO_DATA_DIR` overrides the base path in either
  mode.
- **First-run download.** Before starting the Flask server, a frozen build
  (`getattr(sys, 'frozen', False)`, or `VESDIO_FETCH_DATA=1` for local
  testing without building an executable) calls
  `src.data_bootstrap.ensure_reference_data()`. This:
  1. Checks whether the reference year's files already exist locally — if
     so, it does nothing (no network call at all on subsequent launches).
  2. Otherwise fetches `manifest.json` from `DATA_RELEASE_BASE_URL` (default
     `https://github.com/frankiecho/vesdio/releases/latest/download/`, both
     configurable via `src/config.py`/env vars).
  3. Downloads each file the manifest lists (streamed to a `.part` temp file,
     retried up to 4 times with exponential backoff on network errors),
     verifying sha256 + byte size before renaming it into place.
  4. Non-fatally skips any file flagged `"required": false` in the manifest
     (e.g. `G`, `production_history`, `encore_materiality`) if it fails —
     those already have graceful fallbacks in `src/providers/exiobase.py`.
  Progress is printed to the console (`[data setup] ...` lines); if the
  download fails entirely (no network, or the release isn't published yet),
  the app still starts, using the synthetic dummy dataset generated by
  `src.providers.exiobase._generate_dummy_data` (unchanged from before this
  workstream) so it's never left in a broken state.
- Dev/CI invocations of `python app.py` never trigger a download — the
  downloader import and call are gated behind `is_frozen or
  VESDIO_FETCH_DATA`, so `create_dummy_data.py` + the dummy fallback remain
  the dev-loop path with zero network dependency.
- If a user wants a year that wasn't shipped in the data release, they can
  still run `ingest_exiobase.py` themselves (this requires network access
  and significant disk space/time) to add it under their local data
  directory — the packaged app and the dev pipeline share the same on-disk
  layout, so no code changes are needed to pick up additional years.
- Closing the pywebview window ends the process (the Flask server thread is
  a daemon thread and stops with it) — there is no separate "quit" step
  needed, and no orphaned server process is left listening on 127.0.0.1.
