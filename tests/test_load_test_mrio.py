"""
WS7 — Offline methodology validation on a *complete* multi-region MRIO.

The rest of the suite exercises the models on a degenerate 2x2 synthetic economy.
Here we use ``pymrio.load_test()`` — a real 6-region x 8-sector (48-sector) MRIO
with genuine inter-industry structure and a computable Ghosh inverse — to validate
behaviour that the tiny dummy cannot exercise: non-negativity under large shocks,
the backward (Leontief) vs forward (Ghosh) linkage semantics, attribution
consistency, and that the constrained LP actually runs on a non-trivial network.

It requires NO network access (load_test is bundled with pymrio); the full
~8000-sector EXIOBASE convergence-timing claim still needs real data on target
hardware and is out of scope here.
"""
import numpy as np
import pandas as pd
import pytest

pymrio = pytest.importorskip("pymrio")

from src.scenario_modeler import (
    run_physical_risk,
    run_physical_risk_ghosh,
    run_physical_risk_constrained,
    attribute_output_change,
)


@pytest.fixture(scope="module")
def mrio():
    """A complete 48-sector MRIO in the app's expected schema (A, X, Y, L, G)."""
    m = pymrio.load_test().calc_all(include_ghosh=True)
    A = m.A.copy()
    X = pd.DataFrame(m.x.copy())
    X.columns = ["GrossOutput"]
    Y = pd.DataFrame(m.Y.sum(axis=1), columns=["FinalDemand"])
    L = m.L.copy()
    G = m.G.copy()
    return {"A": A, "X": X, "Y": Y, "L": L, "G": G}


def _shock(region, sector, magnitude=0.2):
    return [{"region": region, "sector": sector, "magnitude": magnitude}]


def test_all_methods_run_and_stay_nonnegative(mrio):
    """No method may drive gross output negative, even for a total (100%) shock."""
    A, X, Y, L, G = (mrio[k] for k in ("A", "X", "Y", "L", "G"))
    sm = _shock("reg2", "food", magnitude=1.0)

    _, dx_leon = run_physical_risk(A, X, Y, L, sm)
    _, dx_ghosh = run_physical_risk_ghosh(A, X, G, sm)
    _, dx_con = run_physical_risk_constrained(A, X, Y, G, sm)

    for name, dx in [("leontief", dx_leon), ("ghosh", dx_ghosh), ("constrained", dx_con)]:
        x_new = X["GrossOutput"] + dx
        assert x_new.min() >= -1e-6, f"{name} produced negative gross output ({x_new.min()})"


def test_leontief_is_backward_ghosh_is_forward(mrio):
    """
    Document the linkage semantics on a real table: an *upstream* supply shock
    propagates forward (Ghosh) more than backward (Leontief); a *downstream*
    demand shock propagates backward (Leontief) more than forward (Ghosh).
    """
    A, X, Y, L, G = (mrio[k] for k in ("A", "X", "Y", "L", "G"))
    up, down = ("reg1", "mining"), ("reg1", "manufactoring")

    # Upstream shock (mining) felt at a downstream home (manufactoring)
    _, dx_l = run_physical_risk(A, X, Y, L, _shock(*up))
    _, dx_g = run_physical_risk_ghosh(A, X, G, _shock(*up))
    assert abs(dx_g.loc[down]) > abs(dx_l.loc[down])

    # Downstream shock (manufactoring) felt at an upstream home (mining)
    _, dx_l2 = run_physical_risk(A, X, Y, L, _shock(*down))
    _, dx_g2 = run_physical_risk_ghosh(A, X, G, _shock(*down))
    assert abs(dx_l2.loc[up]) > abs(dx_g2.loc[up])


def test_leontief_attribution_nonzero_and_consistent(mrio):
    """
    On a realistic table the Leontief attribution is non-zero and its total
    equals |delta_x[home]| — confirming the WS6 "zero contribution" was a 2x2
    dummy-topology artifact, not a bug.
    """
    A, X, Y, L, G = (mrio[k] for k in ("A", "X", "Y", "L", "G"))
    home = ("reg1", "manufactoring")
    sm = _shock("reg1", "mining")

    _, dx = run_physical_risk(A, X, Y, L, sm)
    att = attribute_output_change("leontief", dx, sm, home[0], home[1], L_df=L, G_df=G, A_df=A)

    assert att["total_impact"] > 0
    assert att["total_impact"] == pytest.approx(abs(dx.loc[home]), rel=1e-6)


def test_constrained_respects_capacity_on_real_network(mrio):
    """The constrained LP runs on the 48-sector network and never exceeds baseline capacity."""
    A, X, Y, L, G = (mrio[k] for k in ("A", "X", "Y", "L", "G"))
    sm = _shock("reg3", "electricity", magnitude=0.5)

    warning, dx = run_physical_risk_constrained(A, X, Y, G, sm)
    x_new = X["GrossOutput"] + dx
    # No sector may end up producing more than its (unshocked) baseline capacity.
    assert (x_new <= X["GrossOutput"] + 1e-6).all()
    assert x_new.min() >= -1e-6


def test_dummy_fallback_is_runnable_end_to_end(tmp_path, monkeypatch):
    """
    The dummy fallback must now (a) use a (region, sector) MultiIndex and
    (b) include a Ghosh G matrix, so the default Ghosh run works completely
    offline. Previously it used flat string labels and omitted G, so every
    real model run on the fallback failed.
    """
    import src.providers.exiobase as ex

    monkeypatch.setattr(ex, "EXIOBASE_DIR", tmp_path / "exiobase")
    ex._generate_dummy_data(year=2021)

    d = tmp_path / "exiobase" / "2021"
    assert (d / "EXIOBASE_G.parquet").exists()  # G no longer missing

    A = pd.read_parquet(d / "EXIOBASE_A.parquet")
    X = pd.read_parquet(d / "EXIOBASE_X.parquet")
    Y = pd.read_parquet(d / "EXIOBASE_Y.parquet")
    L = pd.read_parquet(d / "EXIOBASE_L.parquet")
    G = pd.read_parquet(d / "EXIOBASE_G.parquet")
    assert isinstance(A.index, pd.MultiIndex) and A.index.names == ["region", "sector"]

    # A Ghosh run (the app default) completes and stays non-negative.
    sm = [{"region": "C2", "sector": "S2", "magnitude": 0.2}]
    _, dx = run_physical_risk_ghosh(A, X, G, sm)
    assert (X["GrossOutput"] + dx).min() >= -1e-6
    # And the Leontief path resolves the (region, sector) tuple index too.
    _, dx_l = run_physical_risk(A, X, Y, L, sm)
    assert dx_l.loc[("C2", "S2")] <= 0
