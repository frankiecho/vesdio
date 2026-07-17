# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path
from dotenv import load_dotenv
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

# .env is no longer needed for DATA_DIR (data isn't bundled anymore, see
# below), but is still loaded in case future build-time toggles want it.
load_dotenv()

block_cipher = None

# --- Data files to be bundled ---
# The EXIOBASE reference dataset is intentionally NOT bundled here anymore
# (it previously was, via a `(DATA_DIR, 'data')` entry) — a single ingested
# year is well over a gigabyte even at float32, which made for a bloated,
# slow-to-download executable. Instead, `src/data_bootstrap.py` fetches it
# from a GitHub Release into a persistent per-user data directory on first
# run (see `src/paths.py: get_base_data_path()` and docs/PACKAGING.md). The
# packaged app therefore only needs `assets/` (icons, design-system CSS,
# etc.), which stays small.
datas = [ (str(Path(__name__).parent / 'assets'), 'assets') ]

# Add data files from pandas, plotly, and dask to ensure they are bundled correctly.
datas += collect_data_files('plotly')
datas += collect_data_files('dask')
datas += collect_data_files('pandas')

# Explicitly include package metadata that dask checks for at runtime.
datas += copy_metadata('pandas')
datas += copy_metadata('pyarrow')

# --- Hidden Imports ---
# PyInstaller sometimes fails to detect imports from certain libraries.
# We list them here to ensure they are included.
hiddenimports = [
    'pandas._libs.tslibs.np_datetime',
    'pandas._libs.tslibs.nattype',
    'pandas._libs.skiplist',
    'plotly.graph_objs.*',
    'dask.array',
    'dask.dataframe',
    'dask.bag',
    'pyarrow',
    'webview',
    # Resolves the persistent per-user data dir (src/paths.py); PyInstaller's
    # static analysis can miss it since it's imported deep inside src.paths.
    'platformdirs',
]

# pywebview picks its native GUI backend at import time, and PyInstaller
# needs it as an explicit hidden import per platform (its imports are
# conditional, so static analysis misses them). Builds are done per-OS, so
# pick the backend for whichever platform this spec is being built on.
# See docs/PACKAGING.md for the required system/backend dependencies.
if sys.platform.startswith('win'):
    hiddenimports += ['webview.platforms.winforms', 'clr']
elif sys.platform == 'darwin':
    hiddenimports += ['webview.platforms.cocoa']
else:
    hiddenimports += ['webview.platforms.gtk', 'webview.platforms.qt']

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, name='vesdio', debug=False, strip=False, upx=True, console=True, icon='assets/favicon.ico')
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=True, upx_exclude=[], name='vesdio_dist')