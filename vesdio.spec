# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from pathlib import Path
from dotenv import load_dotenv
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

# Load .env file to get DATA_DIR for the build process
load_dotenv()

block_cipher = None

# --- Data files to be bundled ---
# It bundles the directory specified by DATA_DIR in your .env file (or 'data' by default).
# The destination inside the package will always be 'data'.
datas = [ (os.getenv('DATA_DIR', 'data'), 'data') ]

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
    'pyarrow'
]

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