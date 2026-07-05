import pytest
import pandas as pd
from src.scenario_modeler import run_physical_risk, run_physical_risk_ghosh, attribute_output_change

def test_leontief_model_shock(dummy_mrio_data):
    """
    Test that a Leontief model shock correctly reduces output in the shocked
    sector and propagates to dependent sectors.
    """
    A, X, Y, L = dummy_mrio_data['A'], dummy_mrio_data['X'], dummy_mrio_data['Y'], dummy_mrio_data['L']
    
    # Shock C1-Farming by 50%
    shock_maps = [{'region': 'C1', 'sector': 'Farming', 'magnitude': 0.5}]
    
    _, delta_x = run_physical_risk(A, X, Y, L, shock_maps)

    # Assert the shocked sector's output is reduced
    original_output = X.loc[('C1', 'Farming'), 'GrossOutput']
    expected_change = -original_output * 0.5
    assert delta_x.loc[('C1', 'Farming')] == pytest.approx(expected_change)

    # WS3 fix (finding A1): the Leontief mixed model is demand-driven with x_m specified
    # on a *quantity* basis. It only propagates a shock through the backward linkage
    # (how much the shocked sector itself buys from its endogenous suppliers) -- it
    # cannot represent the forward-linkage/rationing effect of a customer being unable
    # to source enough input from a shrunken supplier. In this fixture Farming supplies
    # Food Processing but does not itself buy from any endogenous sector, so the
    # theoretically-correct Leontief result is *no* change to Food Processing's output.
    # (The previous "negative final demand" workaround faked a forward-linkage effect
    # here with no sound theoretical basis, which is exactly what finding A1 flagged.
    # The genuine forward/supply-side effect is captured by the Ghosh model below and by
    # the constrained LP model in `tests/test_convergence_benchmark.py`.)
    assert delta_x.loc[('C1', 'Food Processing')] == pytest.approx(0.0, abs=1e-8)

def test_ghosh_model_shock(dummy_mrio_data):
    """
    Test that a Ghosh model shock correctly reduces output in the shocked
    sector and propagates to dependent sectors.
    """
    A, X, G = dummy_mrio_data['A'], dummy_mrio_data['X'], dummy_mrio_data['G']
    
    # Shock C2-Mining by 100%
    shock_maps = [{'region': 'C2', 'sector': 'Mining', 'magnitude': 1.0}]
    
    _, delta_x = run_physical_risk_ghosh(A, X, G, shock_maps)

    # Assert the shocked sector's output is reduced to zero
    original_output = X.loc[('C2', 'Mining'), 'GrossOutput']
    assert delta_x.loc[('C2', 'Mining')] == pytest.approx(-original_output)

    # Assert the dependent sector (C2-Manufacturing) is also impacted negatively
    assert delta_x.loc[('C2', 'Manufacturing')] < 0

def test_attribute_output_change(dummy_mrio_data):
    """
    Test the attribution function to ensure it returns a valid structure.
    """
    A, X, Y, L = dummy_mrio_data['A'], dummy_mrio_data['X'], dummy_mrio_data['Y'], dummy_mrio_data['L']
    shock_maps = [{'region': 'C1', 'sector': 'Farming', 'magnitude': 0.1}]
    _, delta_x = run_physical_risk(A, X, Y, L, shock_maps)

    attribution = attribute_output_change(L, delta_x, 'C1', 'Food Processing')

    assert isinstance(attribution, dict)
    assert 'causes' in attribution
    assert 'total_impact' in attribution
    
    # The only external cause should be C1-Farming
    assert 'C1 - Farming' in attribution['causes']
    assert pytest.approx(sum(attribution['causes'].values()), 1) == 100.0