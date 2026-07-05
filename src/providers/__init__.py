# src/providers/__init__.py
"""
Manifest-driven registry of MRIO (multi-regional input-output) database
providers.

EXIOBASE 3 is the only fully-implemented provider and remains the default
(`get_provider()` with no argument). The other entries below are STUB
manifests: they document the license and status of other open MRIO
databases so the swap architecture (registry -> MRIOProvider -> app code)
is demonstrated end-to-end, without pretending to have built real ingest
pipelines for them. Attempting to actually load data from a stub raises a
clear NotImplementedError.

Only providers with a genuinely open (or free-for-use) license are ever
registered here — see each ProviderManifest.license.

To add a real new provider:
  1. Add `ingest_<db>.py` (generalize the parse -> save pattern documented
     in `ingest_exiobase.py`'s module docstring) producing the same
     per-year parquet/JSON layout as the EXIOBASE provider, plus its own
     ENCORE materiality crosswalk (ISIC <-> that DB's sector classification).
  2. Add `src/providers/<db>.py` with a class implementing `MRIOProvider`
     (see `src/providers/exiobase.py` as the reference implementation).
  3. Register it below with `implemented=True` in its manifest.
  4. Nothing in app.py / src/callbacks.py / src/scenario_modeler.py needs to
     change — they consume providers only through `src.data_loader`'s thin
     wrappers, which delegate to `get_provider(DEFAULT_PROVIDER_ID)`.
"""
from typing import List

from .base import MRIOProvider, ProviderManifest
from .exiobase import ExiobaseProvider

DEFAULT_PROVIDER_ID = "exiobase"


class _StubProvider(MRIOProvider):
    """
    Placeholder for a provider whose manifest/license is documented but
    whose ingest + loading implementation doesn't exist yet. Lets the
    registry (and a future UI database-selector) list the provider — e.g.
    to show it as "coming soon" — without any risk of it being mistaken for
    a working backend.
    """

    def __init__(self, manifest: ProviderManifest):
        self.manifest = manifest

    def _not_implemented(self):
        raise NotImplementedError(
            f"MRIO provider '{self.manifest.id}' ({self.manifest.name}) is a "
            f"documented stub, not an implementation. See {self.manifest.source_url} "
            f"and src/providers/__init__.py for what's needed to implement it."
        )

    def load_labels(self, year):
        self._not_implemented()

    def load_matrices(self, year, matrices_to_load=None, use_dask=False):
        self._not_implemented()

    def load_production_history(self):
        self._not_implemented()

    def load_encore_materiality(self):
        self._not_implemented()

    def region_groups(self, all_countries):
        self._not_implemented()

    def country_names(self):
        self._not_implemented()


# --- Stub manifests: open/free-licensed MRIO databases not yet implemented ---

_STUB_MANIFESTS = [
    ProviderManifest(
        id="oecd_icio",
        name="OECD Inter-Country Input-Output (ICIO) Tables",
        license="OECD open data terms of use (free to use, redistribute, and adapt with attribution)",
        reference_years=(),
        source_url="https://www.oecd.org/en/data/datasets/inter-country-input-output-tables.html",
        sector_classification="ISIC Rev.4-based, ~45 industries x 76 economies + RoW",
        implemented=False,
        notes=(
            "Not yet implemented. pymrio.parse_oecd() already exists as a "
            "parser; would need an OECD-ICIO-sector <-> ISIC crosswalk for "
            "ENCORE materiality (ICIO's own classification is already close "
            "to ISIC, so this crosswalk should be the thinnest of the three)."
        ),
    ),
    ProviderManifest(
        id="gloria",
        name="GLORIA (Global Resource Input-Output database)",
        license="Free for academic / non-commercial research use (University of Sydney, ISA)",
        reference_years=(),
        source_url="https://ielab.info/analyse/gloria",
        sector_classification="GLORIA sector classification, 120 sectors x 164 regions",
        implemented=False,
        notes=(
            "Not yet implemented. No built-in pymrio parser as of writing; "
            "would need a custom ingest reading GLORIA's native matrix "
            "export format, plus a GLORIA-sector <-> ISIC crosswalk for "
            "ENCORE materiality."
        ),
    ),
    ProviderManifest(
        id="wiod",
        name="World Input-Output Database (WIOD)",
        license="Free, open license (WIOD Consortium, released under a Creative Commons-style open license)",
        reference_years=(),
        source_url="http://www.wiod.org/database/wiots16",
        sector_classification="ISIC Rev.4, 56 sectors x 43 countries + Rest of World",
        implemented=False,
        notes=(
            "Not yet implemented. pymrio.parse_wiod() already exists as a "
            "parser; would need a WIOD-sector <-> ISIC crosswalk for ENCORE "
            "materiality (WIOD is already ISIC-based, so this should also "
            "be relatively thin)."
        ),
    ),
]

_REGISTRY = {DEFAULT_PROVIDER_ID: ExiobaseProvider()}
_REGISTRY.update({m.id: _StubProvider(m) for m in _STUB_MANIFESTS})


def get_provider(provider_id: str = DEFAULT_PROVIDER_ID) -> MRIOProvider:
    """
    Look up a registered MRIOProvider by id. Defaults to EXIOBASE.
    Raises ValueError for an unknown id, and NotImplementedError (lazily,
    only when you actually try to load data) for a registered-but-stub
    provider like 'oecd_icio', 'gloria', or 'wiod'.
    """
    try:
        return _REGISTRY[provider_id]
    except KeyError:
        raise ValueError(
            f"Unknown MRIO provider '{provider_id}'. Available: {sorted(_REGISTRY)}"
        )


def list_providers() -> List[ProviderManifest]:
    """
    Return the manifests of all registered providers (implemented and
    stub). All of them carry an open/free-for-use license by construction —
    this registry only ever registers open-licensed providers.
    """
    return [p.manifest for p in _REGISTRY.values()]


__all__ = [
    "MRIOProvider",
    "ProviderManifest",
    "ExiobaseProvider",
    "DEFAULT_PROVIDER_ID",
    "get_provider",
    "list_providers",
]
