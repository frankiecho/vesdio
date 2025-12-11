import pytest
import pandas as pd
import plotly.graph_objects as go
from src.plotting import (
    create_before_after_barchart,
    create_top_impacts_table,
    create_sankey_diagram
)
from src.scenario_modeler import run_physical_risk

def test_create_before_after_barchart(dummy_mrio_data):
    """Ensure the before/after chart function returns a Figure."""
    X, A, Y, L = dummy_mrio_data['X'], dummy_mrio_data['A'], dummy_mrio_data['Y'], dummy_mrio_data['L']
    shock_maps = [{'region': 'C1', 'sector': 'Farming', 'magnitude': 0.1}]
    _, delta_x = run_physical_risk(A, X, Y, L, shock_maps)

    fig = create_before_after_barchart(X, delta_x, 'C1', 'Food Processing', dummy_mrio_data['country_mapping'], dummy_mrio_data['COLOR_PALETTE'])
    assert isinstance(fig, go.Figure)

def test_create_top_impacts_table(dummy_mrio_data):
    """Ensure the top impacts table function returns a Figure."""
    X, A, Y, L = dummy_mrio_data['X'], dummy_mrio_data['A'], dummy_mrio_data['Y'], dummy_mrio_data['L']
    shock_maps = [{'region': 'C1', 'sector': 'Farming', 'magnitude': 0.1}]
    _, delta_x = run_physical_risk(A, X, Y, L, shock_maps)

    fig = create_top_impacts_table(delta_x, X, dummy_mrio_data['country_mapping'], dummy_mrio_data['COLOR_PALETTE'])
    assert isinstance(fig, go.Figure)

def test_create_sankey_diagram(dummy_mrio_data):
    """Ensure the Sankey diagram function returns a Figure."""
    X, A, Y, L = dummy_mrio_data['X'], dummy_mrio_data['A'], dummy_mrio_data['Y'], dummy_mrio_data['L']
    shock_maps = [{'region': 'C1', 'sector': 'Farming', 'magnitude': 0.1}]
    _, delta_x = run_physical_risk(A, X, Y, L, shock_maps)

    fig = create_sankey_diagram(A, delta_x, shock_maps, 'C1', 'Food Processing', dummy_mrio_data['country_mapping'], dummy_mrio_data['COLOR_PALETTE'])
    assert isinstance(fig, go.Figure)