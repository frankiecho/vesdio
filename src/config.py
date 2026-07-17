# src/config.py

"""
Generic, provider-agnostic static configuration: the shared color palette
used across all charts.

As of Workstream 5 (swappable IO-database core), region/country name maps,
ISO3 codes, and region groupings are EXIOBASE-specific and have moved to
`src.providers.exiobase_config` (owned by `ExiobaseProvider`), since a
different MRIO provider (OECD ICIO, GLORIA, WIOD, ...) would have its own
region vocabulary. They are re-exported here for backward compatibility,
since `app.py` and other modules import them directly from `src.config`.
"""

import os

from src.design_tokens import COLORS

# --- First-run reference-data download config (see src/data_bootstrap.py) ---
# The packaged executable no longer bundles the EXIOBASE reference-year data
# (vesdio.spec no longer includes DATA_DIR in `datas`); instead it downloads
# per-matrix files from a GitHub Release on first run, described by a
# `manifest.json` asset. Both are env-overridable so the data host can move
# (e.g. a pinned version tag instead of `latest`, or a mirror) without a
# code change.
#
# TODO(release): the `frankiecho/vesdio` release named here must actually
# have `manifest.json` + the EXIOBASE_<year>_*.parquet / labels_<year>.json
# assets uploaded (via `ingest_exiobase.build_release_manifest`) before
# shipping a build that relies on this default URL — see docs/PACKAGING.md.
DATA_RELEASE_BASE_URL = os.getenv(
    'DATA_RELEASE_BASE_URL',
    'https://github.com/frankiecho/vesdio/releases/latest/download/',
)
DATA_MANIFEST_NAME = os.getenv('DATA_MANIFEST_NAME', 'manifest.json')

# Color Palette for consistent styling across all charts
# Okabe-Ito colorblind-friendly palette. Derived from src/design_tokens.py
# (single source of truth, shared with assets/design-system.css) so charts
# and CSS never drift; keys/values are unchanged from before the refactor.
COLOR_PALETTE = {
    'blue': COLORS['brand']['blue'],    # Neutral/Base color (Okabe-Ito Blue)
    'red': COLORS['brand']['red'],      # Impact/Negative color (Okabe-Ito Vermillion)
    'amber': COLORS['brand']['amber'],  # Highlight color for scales (Okabe-Ito Orange)
    'beige': COLORS['brand']['beige'],  # Secondary highlight for scales (Okabe-Ito Yellow)
    'green': COLORS['brand']['green'],  # Positive change color (Okabe-Ito Bluish Green)
    'grey': COLORS['brand']['grey'],    # For "Others" category (Grey)
}

# --- Backward-compatible re-exports (moved to src/providers/exiobase_config.py) ---
from src.providers.exiobase_config import (  # noqa: E402,F401
    country_mapping,
    COUNTRY_CODES_3_LETTER,
    REGION_GROUPS,
    get_valid_region_groups,
)
