# Packaging VESDIO as an offline desktop app

VESDIO ships as a native-feeling desktop app rather than "a web page you have
to keep a browser tab open for": the Dash/Flask server still does all the
work, but it runs on a background thread and is displayed inside a native
[`pywebview`](https://pywebview.flowrl.com/) window instead of a browser tab.
Combined with a bundled, pre-processed reference-year dataset, the packaged
app requires **no network access** and **no separate EXIOBASE download** to
run.

This document covers:

1. How the pywebview launcher works (and its browser-tab fallback).
2. How to build the offline data bundle.
3. How to build the PyInstaller executable on Windows/macOS/Linux.
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

---

## 3. Building the PyInstaller executable

`vesdio.spec` already bundles whatever directory `DATA_DIR` points to (via
`.env`, default `data/`) as `data/` inside the packaged app, plus `assets/`
and the metadata/hidden imports needed by pandas/pyarrow/dask/plotly. It now
also declares `pywebview` as a hidden import.

### Steps (any platform)

```bash
# 1. Install build dependencies (in your build venv)
pip install -r requirements.txt pyinstaller

# 2. Point DATA_DIR at your assembled offline bundle (see section 2), e.g. in .env:
echo "DATA_DIR=data/bundle/2021" > .env
# (or copy/rename data/bundle/2021 to ./data before building)

# 3. Build
pyinstaller vesdio.spec

# Output: dist/vesdio_dist/  (contains the vesdio executable + bundled data/assets)
```

Distribute the whole `vesdio_dist/` directory (PyInstaller's `--onedir`
style, as configured via `COLLECT` in `vesdio.spec`) — the executable
depends on the sibling files/folders next to it.

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

- On launch, VESDIO starts the Flask server on a background thread and opens
  the pywebview window pointed at `http://127.0.0.1:8050`. No external
  network call is made by the app itself at startup.
- Data is loaded per-year from `get_base_data_path()` (`src/data_loader.py`),
  which resolves to `sys._MEIPASS/data` in a frozen/packaged build, or
  `DATA_DIR`/`./data` in a normal dev environment. If the bundled reference
  year's files are present, the app works fully offline immediately.
- If a user wants a year that wasn't bundled, they can still run
  `ingest_exiobase.py` themselves (this requires network access and
  significant disk space/time) to add it under their local `data/`
  directory — the packaged app and the dev pipeline share the same data
  layout, so no code changes are needed to pick up additional years.
- Closing the pywebview window ends the process (the Flask server thread is
  a daemon thread and stops with it) — there is no separate "quit" step
  needed, and no orphaned server process is left listening on 127.0.0.1.
