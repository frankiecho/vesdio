# src/data_loader.py
"""
Thin, backward-compatible facade over the MRIO provider registry
(src/providers/).

Historically this module *was* the EXIOBASE loader. As of Workstream 5
(swappable IO-database core), the actual loading logic lives in
`src.providers.exiobase.ExiobaseProvider`, and this module just delegates to
the default provider (EXIOBASE) via `src.providers.get_provider()`. Every
function below has the exact same name/signature/behavior as before, so
`app.py`, `src/callbacks.py`, and `src/scenario_modeler.py` need no changes.

To load data from a different provider, use `src.providers.get_provider(id)`
directly and call its `load_*` methods — this module intentionally only
exposes the default-provider convenience functions that existing code
already relies on.
"""
from src.paths import get_base_data_path
from src.providers import get_provider, DEFAULT_PROVIDER_ID

# Re-exported for backward compatibility: some callers/tests may reference
# these path constants directly off `src.data_loader`.
_default_provider = get_provider(DEFAULT_PROVIDER_ID)
BASE_DATA_PATH = get_base_data_path()
EXIOBASE_DIR = _default_provider.data_dir
ENCORE_DATA_DIR = _default_provider.encore_data_dir

# Re-exported for backward compatibility with any code that imported the
# dummy-data generator directly off `src.data_loader`.
from src.providers.exiobase import _generate_dummy_data  # noqa: E402,F401


def load_labels_data(year=2021):
    """
    Loads labels and metadata for a specific year, from the default
    (EXIOBASE) MRIO provider.
    """
    return get_provider(DEFAULT_PROVIDER_ID).load_labels(year=year)


def load_mrio_matrices(year=2021, matrices_to_load=None, use_dask=False):
    """
    Loads specified MRIO matrices for a specific year, from the default
    (EXIOBASE) MRIO provider. Handles loading the 'A' matrix from multiple
    parts.
    """
    return get_provider(DEFAULT_PROVIDER_ID).load_matrices(
        year=year, matrices_to_load=matrices_to_load, use_dask=use_dask
    )


def load_production_history():
    """
    Loads the aggregated production history data from the default
    (EXIOBASE) MRIO provider.
    """
    return get_provider(DEFAULT_PROVIDER_ID).load_production_history()


def load_encore_materiality():
    """
    Loads the ENCORE materiality JSON data from the default (EXIOBASE) MRIO
    provider.
    """
    return get_provider(DEFAULT_PROVIDER_ID).load_encore_materiality()
