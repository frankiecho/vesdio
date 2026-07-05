# src/providers/base.py
"""
Abstract interface for pluggable Multi-Regional Input-Output (MRIO) database
providers (Workstream 5 — "swappable IO-database core").

VESDIO's core linear-algebra model (src/scenario_modeler.py) only needs a
handful of things from whatever IO database backs it: the technical
coefficients matrix A, the Leontief/Ghosh inverses L/G, gross output X,
final demand Y, an environmental/satellite extension E, label metadata for
regions/sectors, sensible scenario defaults, region groupings for the UI,
and an ENCORE (natural-capital dependency) crosswalk onto that database's
own sector classification.

This module defines that contract as an abstract base class so the rest of
the app (app.py, src/callbacks.py, src/data_loader.py) can be written once
against `MRIOProvider` and stay agnostic to which underlying database is
active. EXIOBASE 3 is the only fully-implemented provider today
(src/providers/exiobase.py) and remains the default; see
src/providers/__init__.py for the registry and for stub manifests
documenting how OECD ICIO / GLORIA / WIOD would plug in.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ProviderManifest:
    """
    Static metadata describing an MRIO data provider. This is what a future
    UI database-selector dropdown would render, and what governs whether a
    provider is safe to expose at all (only genuinely open-licensed
    databases should ever be surfaced to users).
    """
    id: str
    name: str
    license: str
    reference_years: Tuple[int, ...]
    source_url: str
    sector_classification: str
    # Whether this provider has a real, working implementation (loads real
    # data) as opposed to being a documented placeholder for future work.
    implemented: bool = True
    notes: str = ""


class MRIOProvider(ABC):
    """
    Abstract base class for an MRIO database backend.

    A concrete provider is responsible for:
      - loading the core system matrices (A, L, G, X, Y, E) for a given
        reference year, in the generic (region, sector) MultiIndex layout
        already used throughout the app;
      - loading region/sector label metadata and a sensible default
        scenario (home region/sector, shock region/sector);
      - loading a long-run production history for the "Historical" tab;
      - exposing region groupings (for "shock a whole region" UX), filtered
        to the regions actually present in the loaded dataset;
      - exposing human-readable country names and ISO3 codes for maps;
      - exposing an ENCORE-materiality crosswalk mapping this provider's own
        sector classification to ENCORE natural-capital dependency ratings
        (produced at ingest time from an ISIC <-> <this DB's classification>
        crosswalk table — see ingest_encore.py for the EXIOBASE case).

    Concrete providers implement this against their own on-disk layout /
    ingestion pipeline. `ExiobaseProvider` wraps VESDIO's existing loader
    behavior unchanged; it is the reference implementation new providers
    should follow.
    """

    #: Set by subclasses (or their __init__) to a ProviderManifest instance.
    manifest: ProviderManifest

    @abstractmethod
    def load_labels(self, year: int) -> Tuple[List[str], List[str], List[str], Optional[dict]]:
        """
        Return (labels, countries, sectors, defaults) for `year`.

        - labels: list of "REGION-Sector" combined row/column labels
        - countries: list of region codes present in the dataset
        - sectors: list of sector names present in the dataset
        - defaults: dict with home_region/home_sector/shock_region/shock_sector,
          or None if no default scenario could be determined
        """
        raise NotImplementedError

    @abstractmethod
    def load_matrices(
        self,
        year: int,
        matrices_to_load: Optional[Sequence[str]] = None,
        use_dask: bool = False,
    ):
        """
        Return the requested subset of {A, L, G, X, Y, E} for `year`, in the
        same order as `matrices_to_load` (default: ['A', 'Y', 'E', 'X', 'L']).
        Returns a single DataFrame if only one matrix was requested, else a
        tuple, mirroring the existing `load_mrio_matrices` behavior.
        """
        raise NotImplementedError

    @abstractmethod
    def load_production_history(self):
        """Return a long-run gross-output history dataframe, or None if unavailable."""
        raise NotImplementedError

    @abstractmethod
    def load_encore_materiality(self) -> Optional[dict]:
        """
        Return the ENCORE materiality crosswalk for this provider's sector
        classification (i.e. the ISIC-derived ENCORE ratings already joined
        onto this database's own sectors at ingest time), or None if it
        hasn't been generated yet.
        """
        raise NotImplementedError

    @abstractmethod
    def region_groups(self, all_countries: Sequence[str]) -> Dict[str, List[str]]:
        """Return {group_name: [region_codes]}, filtered to `all_countries`."""
        raise NotImplementedError

    @abstractmethod
    def country_names(self) -> Dict[str, str]:
        """Return {region_code: full country/region name}."""
        raise NotImplementedError

    def country_iso3(self) -> Dict[str, str]:
        """
        Return {region_code: ISO 3166-1 alpha-3 code} for choropleth maps.
        Optional — providers without a natural 2-letter country axis (or
        that haven't populated this yet) may return an empty dict.
        """
        return {}
