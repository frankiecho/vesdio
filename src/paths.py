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

# Load environment variables from .env file
load_dotenv()


def get_base_data_path() -> Path:
    """
    Determines the base path for data files.
    - For a packaged app (PyInstaller), it's a folder named 'data' inside the bundle.
    - For development, it uses the DATA_DIR from .env, defaulting to './data'.
    """
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        return Path(sys._MEIPASS) / 'data'
    else:
        # Running in a normal Python environment
        return Path(os.getenv('DATA_DIR', 'data'))
