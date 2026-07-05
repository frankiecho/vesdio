"""
Ecosystem-service -> production shock layer.

Historically every EXIOBASE sector flagged "material" for an ENCORE ecosystem
service received the *identical* percentage shock, regardless of how strongly that
sector actually depends on the service (VH vs. H vs. M) or how physically exposed it
is (finding A2 in the codebase accuracy review). This module differentiates that
shock per sector by combining:

1. A per-(sector, service) **dependency intensity** in [0, 1], computed from the
   underlying ENCORE/ISIC ratings (see `ingest_encore.build_encore_materiality` /
   `compute_dependency_intensity`).
2. An optional per-sector **physical exposure intensity** in [0, 1] (e.g. a
   normalized EXIOBASE satellite resource-use intensity such as water or land use).
   Full satellite export is a follow-up (see `exposure_intensity_stub`); until that
   data is wired up this factor defaults to a neutral 1.0 so behavior is unchanged.

Everything here is pure and framework-agnostic so it can be unit tested without the
real ENCORE/EXIOBASE datasets.
"""

from __future__ import annotations

from typing import Callable, Dict, Iterable, Optional, Union


def _clamp01(value: float) -> float:
    """Clamp a numeric value into the [0, 1] range."""
    if value is None:
        return 0.0
    return max(0.0, min(1.0, float(value)))


def effective_magnitude(user_magnitude: float,
                         dependency_intensity: float,
                         exposure_intensity: Optional[float] = None) -> float:
    """
    Combine a user-specified shock magnitude with a sector-specific ecosystem-service
    dependency intensity (and, optionally, a physical exposure intensity) into a
    single differentiated, per-sector effective shock magnitude.

    `user_magnitude` is on whatever scale the caller uses for shock magnitudes
    elsewhere in the app (e.g. 0-100 for a percentage shock); `dependency_intensity`
    and `exposure_intensity` are expected in [0, 1] and are clamped defensively so an
    out-of-range or malformed value cannot silently invert or blow up the shock.

    Combination is multiplicative (v1, tunable later):

        effective = user_magnitude * dependency_intensity * exposure_intensity

    with `exposure_intensity` defaulting to a neutral 1.0 (no-op) when not supplied,
    so a sector with dependency_intensity == 1.0 and no exposure data reproduces the
    old uniform-magnitude behavior exactly, while a sector with a lower dependency
    intensity receives a proportionally smaller shock.
    """
    dependency_factor = _clamp01(dependency_intensity)
    exposure_factor = 1.0 if exposure_intensity is None else _clamp01(exposure_intensity)
    return user_magnitude * dependency_factor * exposure_factor


def exposure_intensity_stub(sector: str, satellite_intensities: Optional[Dict[str, float]] = None) -> float:
    """
    Scaffold for the EXIOBASE physical-exposure factor (benchmark 4, part 2 of the
    plan): a normalized resource-use intensity (e.g. water-use or land-use satellite
    account value) per sector, in [0, 1].

    Full satellite export from `ingest_exiobase.py` is a follow-up. Until
    `satellite_intensities` is supplied, this returns a neutral 1.0 so
    `effective_magnitude` is unaffected (equivalent to omitting the exposure factor
    entirely) and nothing breaks for datasets that haven't been re-ingested with
    satellite data.
    """
    if not satellite_intensities:
        return 1.0
    return _clamp01(satellite_intensities.get(sector, 1.0))


def linear_dose_response(es_decline_pct: float, elasticity: float = 1.0) -> float:
    """
    Default dose-response function: maps a physical ecosystem-service decline
    (0-100 %) linearly onto a production-loss fraction (0-1), scaled by an
    `elasticity` (production-loss-per-unit-ES-decline) that can vary per service.

    `es_decline_pct` is clamped to [0, 100] and the result is clamped to [0, 1] so a
    large elasticity cannot push the output outside a valid loss fraction.
    """
    decline_fraction = max(0.0, min(100.0, float(es_decline_pct))) / 100.0
    return _clamp01(decline_fraction * elasticity)


def dose_response(es_decline_pct: float,
                   service: Optional[str] = None,
                   elasticity_by_service: Optional[Dict[str, float]] = None,
                   response_fn: Optional[Callable[..., float]] = None) -> float:
    """
    Pluggable dose-response hook: maps a physical ES-decline percentage to a
    production-loss fraction for a given `service`.

    This is intentionally a thin dispatcher so v1 can ship with `linear_dose_response`
    while leaving room to swap in a non-linear/service-specific curve later without
    touching call sites. `elasticity_by_service` lets different services have
    different sensitivities (e.g. pollination-dependent crops vs. water-intensive
    manufacturing) while defaulting to elasticity 1.0 (1:1 decline -> loss) when a
    service isn't listed.
    """
    fn = response_fn or linear_dose_response
    elasticity = 1.0
    if elasticity_by_service and service in elasticity_by_service:
        elasticity = elasticity_by_service[service]
    return fn(es_decline_pct, elasticity=elasticity)


SectorEntry = Union[str, Dict[str, object]]


def extract_sector_intensities(service_data: Optional[Dict[str, object]]) -> Dict[str, float]:
    """
    Normalize one service's entry from `encore_materiality.json` into a
    `{sector_name: dependency_intensity}` dict, tolerating BOTH JSON schemas:

    - legacy schema: `service_data['sectors']` is a list of sector-name strings
      (binary materiality only) -- each is treated as full intensity 1.0, which
      reproduces the old uniform-shock behavior exactly for data that hasn't been
      re-ingested yet.
    - enriched schema: `service_data['sectors']` is a list of
      `{"sector": name, "intensity": value}` dicts (see
      `ingest_encore.build_encore_materiality`).

    Returns an empty dict if `service_data` is falsy or has no sectors.
    """
    if not service_data:
        return {}

    sectors: Iterable[SectorEntry] = service_data.get('sectors', []) or []
    intensities: Dict[str, float] = {}

    for entry in sectors:
        if isinstance(entry, dict):
            sector = entry.get('sector')
            intensity = entry.get('intensity', 1.0)
        else:
            # Legacy schema: a bare sector-name string implies full materiality.
            sector = entry
            intensity = 1.0

        if sector is None:
            continue

        intensities[sector] = _clamp01(intensity)

    return intensities
