# src/paths.py
"""
Generic, provider-agnostic filesystem path resolution.

This is intentionally tiny and knows nothing about EXIOBASE or any other
MRIO database — it only answers "where does the app's data directory live",
which is the same question for every provider (dev checkout vs. a
PyInstaller-frozen bundle).
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import platformdirs

# Load environment variables from .env file
load_dotenv()


def get_base_data_path() -> Path:
    """
    Determines the base path for data files.

    - For development: uses `DATA_DIR` from .env, defaulting to './data'.
    - For a packaged app (PyInstaller): returns a **persistent, writable**
      per-user data directory — NOT `sys._MEIPASS`. `_MEIPASS` is a read-only
      temp extraction directory that PyInstaller wipes/recreates every run
      (and on some platforms, on every launch), so anything downloaded there
      (see `src/data_bootstrap.py`) would have to be re-fetched every single
      time the app starts. Instead we use `platformdirs.user_data_dir` (e.g.
      `~/.local/share/VESDIO` on Linux, `~/Library/Application Support/VESDIO`
      on macOS, `%LOCALAPPDATA%\\VESDIO` on Windows), which survives across
      runs and app updates, with a `data/` subdir to match the dev layout.
    - `VESDIO_DATA_DIR` env var overrides the base path in *both* modes, for
      testing or advanced deployments that want a custom location.
    """
    override = os.getenv('VESDIO_DATA_DIR')
    if override:
        return Path(override)

    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle: use a persistent per-user data
        # directory (see docstring above), with a 'data' subdir so the
        # on-disk layout matches the dev DATA_DIR/./data convention exactly
        # (e.g. <user_data_dir>/data/exiobase/2021/EXIOBASE_A.parquet).
        return Path(platformdirs.user_data_dir("VESDIO")) / 'data'
    else:
        # Running in a normal Python environment
        return Path(os.getenv('DATA_DIR', 'data'))
