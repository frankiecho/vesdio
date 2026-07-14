import sys
import os

import pandas as pd
import pytest

# Add the project root to the Python path to allow imports from 'src' and the
# top-level ingest_encore.py script.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.es_shock import (
    effective_magnitude,
    exposure_intensity_stub,
    linear_dose_response,
    dose_response,
    extract_sector_intensities,
)
from ingest_encore import (
    RATING_WEIGHTS,
    compute_dependency_intensity,
    is_material,
    build_encore_materiality,
)


# --- effective_magnitude (the combiner) -------------------------------------------

def test_effective_magnitude_scales_by_dependency_intensity():
    """A higher dependency intensity should produce a proportionally larger shock."""
    user_magnitude = 40  # e.g. a 40% shock, on the app's 0-100 scale
    low = effective_magnitude(user_magnitude, dependency_intensity=0.1)
    high = effective_magnitude(user_magnitude, dependency_intensity=1.0)

    assert low == pytest.approx(4.0)
    assert high == pytest.approx(40.0)
    assert low < high


def test_effective_magnitude_two_sectors_differentiated():
    """
    Regression test for finding A2: two sectors with different dependency
    intensities must receive different effective magnitudes for the same user
    input, instead of the old uniform-shock behavior.
    """
    user_magnitude = 25
    sector_a_intensity = 0.3   # e.g. "Medium" ENCORE rating
    sector_b_intensity = 0.9   # e.g. "Very High" ENCORE rating

    mag_a = effective_magnitude(user_magnitude, sector_a_intensity)
    mag_b = effective_magnitude(user_magnitude, sector_b_intensity)

    assert mag_a != mag_b
    assert mag_a == pytest.approx(user_magnitude * sector_a_intensity)
    assert mag_b == pytest.approx(user_magnitude * sector_b_intensity)


def test_effective_magnitude_zero_intensity_yields_zero_shock():
    assert effective_magnitude(50, dependency_intensity=0.0) == 0.0


def test_effective_magnitude_full_intensity_no_exposure_matches_legacy_behavior():
    """
    With intensity == 1.0 and no exposure factor, effective_magnitude must equal the
    old uniform behavior exactly (user_magnitude unchanged) so legacy/un-reingested
    data still behaves as before.
    """
    assert effective_magnitude(37.5, dependency_intensity=1.0) == pytest.approx(37.5)


def test_effective_magnitude_clamps_out_of_range_intensity():
    # Values outside [0, 1] should be clamped rather than inverting/blowing up the shock.
    assert effective_magnitude(50, dependency_intensity=5.0) == pytest.approx(50.0)
    assert effective_magnitude(50, dependency_intensity=-3.0) == pytest.approx(0.0)


def test_effective_magnitude_applies_optional_exposure_factor():
    user_magnitude = 100
    dependency_intensity = 0.5
    without_exposure = effective_magnitude(user_magnitude, dependency_intensity)
    with_exposure = effective_magnitude(user_magnitude, dependency_intensity, exposure_intensity=0.4)

    assert without_exposure == pytest.approx(50.0)
    assert with_exposure == pytest.approx(20.0)
    assert with_exposure < without_exposure


# --- exposure_intensity_stub (scaffolded, satellite data optional) ----------------

def test_exposure_intensity_stub_defaults_to_neutral_without_satellite_data():
    assert exposure_intensity_stub('Cultivation of wheat') == 1.0
    assert exposure_intensity_stub('Cultivation of wheat', satellite_intensities=None) == 1.0
    assert exposure_intensity_stub('Cultivation of wheat', satellite_intensities={}) == 1.0


def test_exposure_intensity_stub_reads_supplied_satellite_data():
    satellite = {'Cultivation of wheat': 0.7}
    assert exposure_intensity_stub('Cultivation of wheat', satellite) == pytest.approx(0.7)
    # Unlisted sector falls back to neutral 1.0
    assert exposure_intensity_stub('Mining of coal', satellite) == 1.0


# --- dose_response hook ------------------------------------------------------------

def test_linear_dose_response_default_elasticity():
    assert linear_dose_response(0) == 0.0
    assert linear_dose_response(50) == pytest.approx(0.5)
    assert linear_dose_response(100) == pytest.approx(1.0)


def test_linear_dose_response_scales_with_elasticity():
    assert linear_dose_response(50, elasticity=0.5) == pytest.approx(0.25)
    assert linear_dose_response(50, elasticity=2.0) == pytest.approx(1.0)  # clamped to 1.0


def test_dose_response_dispatches_per_service_elasticity():
    elasticities = {'Pollination': 2.0, 'Water supply': 0.5}
    pollination_loss = dose_response(50, service='Pollination', elasticity_by_service=elasticities)
    water_loss = dose_response(50, service='Water supply', elasticity_by_service=elasticities)
    unknown_service_loss = dose_response(50, service='Something else', elasticity_by_service=elasticities)

    assert pollination_loss == pytest.approx(1.0)   # 0.5 decline_fraction * 2.0, clamped
    assert water_loss == pytest.approx(0.25)
    assert unknown_service_loss == pytest.approx(0.5)  # default elasticity of 1.0


def test_dose_response_accepts_custom_response_fn():
    def step_response(es_decline_pct, elasticity=1.0):
        return 1.0 if es_decline_pct > 0 else 0.0

    assert dose_response(10, response_fn=step_response) == 1.0
    assert dose_response(0, response_fn=step_response) == 0.0


# --- extract_sector_intensities: backward compatibility with the old JSON schema --

def test_extract_sector_intensities_handles_enriched_schema():
    service_data = {
        "service": "Pollination",
        "sectors": [
            {"sector": "Cultivation of fruits", "intensity": 0.9},
            {"sector": "Cultivation of vegetables", "intensity": 0.4},
        ],
    }
    result = extract_sector_intensities(service_data)
    assert result == {
        "Cultivation of fruits": pytest.approx(0.9),
        "Cultivation of vegetables": pytest.approx(0.4),
    }


def test_extract_sector_intensities_handles_legacy_schema():
    """
    The old encore_materiality.json schema is a plain list of sector-name strings
    (binary materiality, no intensity). Nothing should break if the data hasn't been
    re-ingested with the enriched schema -- each legacy sector should be treated as
    full intensity 1.0, exactly reproducing the old uniform shock.
    """
    service_data = {
        "service": "Pollination",
        "sectors": ["Cultivation of fruits", "Cultivation of vegetables"],
    }
    result = extract_sector_intensities(service_data)
    assert result == {
        "Cultivation of fruits": 1.0,
        "Cultivation of vegetables": 1.0,
    }


def test_extract_sector_intensities_handles_missing_or_empty_data():
    assert extract_sector_intensities(None) == {}
    assert extract_sector_intensities({"service": "Pollination"}) == {}
    assert extract_sector_intensities({"service": "Pollination", "sectors": []}) == {}


def test_extract_sector_intensities_clamps_out_of_range_values():
    service_data = {
        "service": "Pollination",
        "sectors": [{"sector": "Weird sector", "intensity": 5.0}],
    }
    assert extract_sector_intensities(service_data) == {"Weird sector": 1.0}


# --- end-to-end: legacy vs. enriched schema feeding effective_magnitude -----------

def test_wire_through_legacy_and_enriched_schema_both_produce_valid_shocks():
    """
    Simulates the app.py ecosystem-shock branch: build per-sector shock magnitudes
    from a service's materiality entry, for both JSON schemas.
    """
    user_magnitude = 30

    legacy_service_data = {"service": "Water supply", "sectors": ["Manufacture of textiles"]}
    enriched_service_data = {
        "service": "Water supply",
        "sectors": [{"sector": "Manufacture of textiles", "intensity": 0.6}],
    }

    legacy_shocks = {
        sector: effective_magnitude(user_magnitude, intensity)
        for sector, intensity in extract_sector_intensities(legacy_service_data).items()
    }
    enriched_shocks = {
        sector: effective_magnitude(user_magnitude, intensity)
        for sector, intensity in extract_sector_intensities(enriched_service_data).items()
    }

    # Legacy schema (no graded intensity) reproduces the old uniform magnitude.
    assert legacy_shocks == {"Manufacture of textiles": pytest.approx(30.0)}
    # Enriched schema differentiates the magnitude down from the uniform value.
    assert enriched_shocks == {"Manufacture of textiles": pytest.approx(18.0)}
    assert enriched_shocks["Manufacture of textiles"] < legacy_shocks["Manufacture of textiles"]


# --- ingest_encore.py: dependency intensity computation from synthetic ratings ----

def test_compute_dependency_intensity_all_very_high():
    ratings = pd.Series(['VH', 'VH', 'VH'])
    assert compute_dependency_intensity(ratings) == pytest.approx(1.0)


def test_compute_dependency_intensity_all_very_low_is_zero():
    ratings = pd.Series(['VL', 'VL'])
    assert compute_dependency_intensity(ratings) == 0.0


def test_compute_dependency_intensity_mixed_ratings_is_weighted_mean():
    # 2 rows VH (1.0), 2 rows M (0.3) -> mean = (1.0 + 1.0 + 0.3 + 0.3) / 4 = 0.65
    ratings = pd.Series(['VH', 'VH', 'M', 'M'])
    assert compute_dependency_intensity(ratings) == pytest.approx(0.65)


def test_compute_dependency_intensity_ignores_nan_and_unknown_values():
    ratings = pd.Series(['VH', None, 'not-a-rating', 'L'])
    # Only 'VH' (1.0) and 'L' (0.1) count -> mean = 0.55
    assert compute_dependency_intensity(ratings) == pytest.approx(0.55)


def test_compute_dependency_intensity_empty_or_all_invalid_is_zero():
    assert compute_dependency_intensity(pd.Series([], dtype=object)) == 0.0
    assert compute_dependency_intensity(pd.Series([None, None])) == 0.0


def test_rating_weights_are_monotonic_and_bounded():
    order = ['VL', 'L', 'M', 'H', 'VH']
    weights = [RATING_WEIGHTS[r] for r in order]
    assert weights == sorted(weights)
    assert weights[0] == 0.0
    assert weights[-1] == 1.0
    assert all(0.0 <= w <= 1.0 for w in weights)


def test_is_material_threshold():
    assert is_material(0.01) is True
    assert is_material(0.0) is False
    assert is_material(0.5, threshold=0.5) is False
    assert is_material(0.51, threshold=0.5) is True


def test_build_encore_materiality_differentiates_sectors_and_emits_enriched_schema():
    """
    Synthetic dep_mat_joined: two EXIOBASE sectors that ENCORE would have equally
    flagged as "material" under the old binary logic (both have >= 1 'VH' rating),
    but which should now get different intensities under the graded scheme.
    """
    dep_mat_joined = pd.DataFrame({
        'EXIOBASE': [
            'Cultivation of fruits', 'Cultivation of fruits', 'Cultivation of fruits',
            'Mining of coal', 'Mining of coal', 'Mining of coal',
        ],
        'Pollination': ['VH', 'VH', 'VH', 'VH', 'L', 'VL'],
    })
    ecosystem_services = ['Pollination']
    exiobase_sectors = ['Cultivation of fruits', 'Mining of coal']

    output_data = build_encore_materiality(dep_mat_joined, ecosystem_services, exiobase_sectors)

    assert len(output_data) == 1
    entry = output_data[0]
    assert entry['service'] == 'Pollination'

    sectors_by_name = {s['sector']: s['intensity'] for s in entry['sectors']}

    # Cultivation of fruits: all VH -> intensity 1.0
    assert sectors_by_name['Cultivation of fruits'] == pytest.approx(1.0)
    # Mining of coal: VH, L, VL -> mean(1.0, 0.1, 0.0) = 0.3667 -- still "material"
    # under the old vh_count>=1 rule, but now clearly differentiated (lower) from
    # Cultivation of fruits, fixing finding A2.
    assert sectors_by_name['Mining of coal'] == pytest.approx((1.0 + 0.1 + 0.0) / 3, abs=1e-3)
    assert sectors_by_name['Mining of coal'] < sectors_by_name['Cultivation of fruits']


def test_build_encore_materiality_drops_non_material_sectors():
    dep_mat_joined = pd.DataFrame({
        'EXIOBASE': ['Fishing', 'Fishing'],
        'Pollination': ['VL', 'VL'],
    })
    output_data = build_encore_materiality(dep_mat_joined, ['Pollination'], ['Fishing'])
    # Fishing has zero intensity for Pollination -> not material -> service dropped entirely
    assert output_data == []


def test_build_encore_materiality_skips_service_not_present_for_sector():
    dep_mat_joined = pd.DataFrame({
        'EXIOBASE': ['Fishing'],
        'Pollination': ['VH'],
    })
    # 'Water supply' isn't a column in dep_mat_joined at all.
    output_data = build_encore_materiality(dep_mat_joined, ['Pollination', 'Water supply'], ['Fishing'])
    services = [entry['service'] for entry in output_data]
    assert services == ['Pollination']
