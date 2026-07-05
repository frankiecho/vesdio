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

# Color Palette for consistent styling across all charts
# Okabe-Ito colorblind-friendly palette
COLOR_PALETTE = {
    'blue': "#0072B2",      # Neutral/Base color (Okabe-Ito Blue)
    'red': "#D55E00",       # Impact/Negative color (Okabe-Ito Vermillion)
    'amber': "#E69F00",     # Highlight color for scales (Okabe-Ito Orange)
    'beige': "#F0E442",     # Secondary highlight for scales (Okabe-Ito Yellow)
    'green': "#009E73",      # Positive change color (Okabe-Ito Bluish Green)
    'grey': "#999999",      # For "Others" category (Grey)
}

# --- Backward-compatible re-exports (moved to src/providers/exiobase_config.py) ---
from src.providers.exiobase_config import (  # noqa: E402,F401
    country_mapping,
    COUNTRY_CODES_3_LETTER,
    REGION_GROUPS,
    get_valid_region_groups,
)
