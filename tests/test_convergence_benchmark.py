"""
Benchmark/regression tests for Workstream 3 (rigorous constrained solver + supply-side
fix).

IMPORTANT CAVEAT: the real EXIOBASE dataset (~8000 region-sector rows) is not present in
this repository (only the tiny 2-country x 2-sector dummy fallback in
`src.data_loader._generate_dummy_data` is available offline). The synthetic MRIO systems
built below are deliberately small (tens to a few hundred sectors) so these tests can run
quickly and deterministically in CI. They demonstrate that:
  1. each `model_method` ('leontief', 'ghosh', 'constrained') completes well within the
     <60s wall-clock budget on these synthetic systems, and
  2. no method returns a negative gross output for shocks up to 100%.

They do NOT by themselves prove the <1-minute convergence claim on the full ~8000-sector
EXIOBASE system -- that requires real, ingested EXIOBASE data (see `ingest_exiobase.py`).

UPDATE (real-data validation performed): the full 2021 EXIOBASE dataset (49 regions x 163
sectors = 7987 rows) was ingested and used to benchmark `run_physical_risk_constrained`
directly, which surfaced two real bugs neither the tiny dummy fallback nor these small
synthetic fixtures could have caught:
  1. The shock-reachable subgraph reduction's original defaults (`max_hops=4`,
     `min_weight=1e-9`) reached 100% of all ~8000 sectors within 2 hops on the real,
     densely-connected economy -- solving the full system directly took ~74s, over
     budget. Fixed by tightening the defaults (`max_hops=2`, `min_weight=5e-3`) to
     economically material thresholds, and by no longer attempting the full-system LP at
     all when the reduction can't shrink the problem (immediate fallback instead).
  2. `BIG_M` was scaled off `max(weight_R)` (`weight_R = 1/x0_R`); a single near-zero
     baseline-output sector in the real data pushed `max(weight_R)` to ~1.9e4, making
     `BIG_M ~= 1.9e10` and blowing the LP's coefficient dynamic range past double
     precision -- HiGHS failed immediately with "numerical difficulties" (status 4,
     nit=0), not a timeout. Fixed by scaling `BIG_M` with subgraph size instead (see the
     comment at its definition in `src/scenario_modeler.py`), which is provably bounded
     regardless of any individual sector's output.
`test_constrained_solver_stable_with_near_zero_output_sector` below is a regression test
for bug 2, reproduced on a small synthetic system by injecting a single artificially tiny-
output sector.
"""
import time
import itertools

import numpy as np
import pandas as pd
import pytest

from src.scenario_modeler import (
    run_physical_risk,
    run_physical_risk_ghosh,
    run_physical_risk_constrained,
)

TIME_BUDGET_SECONDS = 60


def _build_synthetic_mrio(n_regions=8, n_sectors=10, seed=7, density=0.15, max_col_sum=0.6):
    """
    Build a small, internally-consistent synthetic MRIO system (A, X, Y, L, G) with a
    MultiIndex(region, sector), for benchmark/non-negativity testing only.

    The technical coefficient matrix A is constructed sparse and randomly, then each
    column is rescaled so its sum is below `max_col_sum` (< 1). This guarantees
    (I - A) is invertible and, by the standard Leontief non-negativity theorem (a
    non-negative matrix with column sums < 1 has a non-negative inverse), that the
    baseline gross output X = L @ Y is itself non-negative for any non-negative Y.
    """
    rng = np.random.default_rng(seed)
    regions = [f"R{i}" for i in range(n_regions)]
    sectors = [f"S{j}" for j in range(n_sectors)]
    labels = pd.MultiIndex.from_tuples(
        list(itertools.product(regions, sectors)), names=["region", "sector"]
    )
    n = len(labels)

    mask = rng.random((n, n)) < density
    values = rng.uniform(0.01, 0.08, size=(n, n))
    A_matrix = values * mask
    np.fill_diagonal(A_matrix, 0.0)

    col_sums = A_matrix.sum(axis=0)
    scale = np.where(col_sums > max_col_sum, max_col_sum / np.maximum(col_sums, 1e-12), 1.0)
    A_matrix = A_matrix * scale

    y_vector = rng.uniform(500, 2000, size=n)
    I = np.identity(n)
    L_matrix = np.linalg.inv(I - A_matrix)
    x_vector = L_matrix @ y_vector

    # Sanity check on the synthetic system itself (not the code under test).
    assert np.all(x_vector >= -1e-8), "Synthetic baseline system must be non-negative."

    A_df = pd.DataFrame(A_matrix, index=labels, columns=labels)
    Y_df = pd.DataFrame({"FinalDemand": y_vector}, index=labels)
    X_df = pd.DataFrame({"GrossOutput": x_vector}, index=labels)
    L_df = pd.DataFrame(L_matrix, index=labels, columns=labels)

    # Ghosh (allocation coefficient) matrix and its inverse.
    Z_matrix = A_matrix * x_vector  # Z_ij = A_ij * x_j
    B_matrix = (Z_matrix.T / np.maximum(x_vector, 1e-12)).T  # B_ij = Z_ij / x_i
    G_matrix = np.linalg.inv(I - B_matrix)
    G_df = pd.DataFrame(G_matrix, index=labels, columns=labels)

    return {"A": A_df, "X": X_df, "Y": Y_df, "L": L_df, "G": G_df, "labels": labels}


@pytest.fixture(scope="module")
def synthetic_mrio():
    return _build_synthetic_mrio(n_regions=8, n_sectors=10, seed=7)


@pytest.fixture(scope="module")
def larger_synthetic_mrio():
    # A bigger synthetic system to give the constrained LP and the shock-reachable
    # subgraph reduction something non-trivial to chew on, while staying fast for CI.
    return _build_synthetic_mrio(n_regions=15, n_sectors=20, seed=11)


def _shock(mrio, magnitude, index=0):
    label = mrio["labels"][index]
    return [{"region": label[0], "sector": label[1], "magnitude": magnitude}]


@pytest.mark.parametrize("method", ["leontief", "ghosh", "constrained"])
def test_method_converges_within_time_budget(larger_synthetic_mrio, method):
    """
    Each model_method must complete within the 60s convergence budget (WS3 goal).
    NOTE: this is validated on a small synthetic system (300 sectors), not the full
    ~8000-sector EXIOBASE reference dataset -- see module docstring.
    """
    mrio = larger_synthetic_mrio
    shock_maps = _shock(mrio, magnitude=0.4, index=0)

    start = time.time()
    if method == "leontief":
        _, delta_x = run_physical_risk(mrio["A"], mrio["X"], mrio["Y"], mrio["L"], shock_maps)
    elif method == "ghosh":
        _, delta_x = run_physical_risk_ghosh(mrio["A"], mrio["X"], mrio["G"], shock_maps)
    else:
        warning, delta_x = run_physical_risk_constrained(
            mrio["A"], mrio["X"], mrio["Y"], mrio["G"], shock_maps, time_limit=55
        )
        assert warning is None, f"Constrained solver unexpectedly fell back: {warning}"
    elapsed = time.time() - start

    assert elapsed < TIME_BUDGET_SECONDS, f"{method} took {elapsed:.2f}s (budget {TIME_BUDGET_SECONDS}s)"
    assert delta_x is not None
    assert len(delta_x) == len(mrio["labels"])


@pytest.mark.parametrize("method", ["leontief", "ghosh", "constrained"])
@pytest.mark.parametrize("magnitude", [0.1, 0.5, 0.9, 1.0])
def test_no_negative_gross_output_for_large_shocks(synthetic_mrio, method, magnitude):
    """
    Regression test for finding A1: no method should ever produce a negative gross
    output, even for a full (100%) shock to a sector.
    """
    mrio = synthetic_mrio
    # Shock a sector that is a supplier to others (index 0) so second-order effects
    # actually propagate through the system.
    shock_maps = _shock(mrio, magnitude=magnitude, index=0)

    if method == "leontief":
        _, delta_x = run_physical_risk(mrio["A"], mrio["X"], mrio["Y"], mrio["L"], shock_maps)
    elif method == "ghosh":
        _, delta_x = run_physical_risk_ghosh(mrio["A"], mrio["X"], mrio["G"], shock_maps)
    else:
        _, delta_x = run_physical_risk_constrained(
            mrio["A"], mrio["X"], mrio["Y"], mrio["G"], shock_maps, time_limit=55
        )

    x_new = mrio["X"]["GrossOutput"] + delta_x
    assert (x_new >= -1e-6).all(), f"{method} produced a negative gross output for a {magnitude:.0%} shock"


def test_constrained_model_respects_capacity_ceiling(synthetic_mrio):
    """
    The constrained LP model must never let the shocked sector exceed its reduced
    capacity ceiling -- this is the key correctness property the analytical models
    cannot guarantee (they can, in principle, exceed a physical capacity constraint).
    """
    mrio = synthetic_mrio
    magnitude = 0.7
    shock_maps = _shock(mrio, magnitude=magnitude, index=0)
    shock_label = mrio["labels"][0]

    warning, delta_x = run_physical_risk_constrained(
        mrio["A"], mrio["X"], mrio["Y"], mrio["G"], shock_maps, time_limit=55
    )
    assert warning is None

    baseline = mrio["X"].loc[shock_label, "GrossOutput"]
    new_output = baseline + delta_x.loc[shock_label]
    cap = baseline * (1 - magnitude)

    assert new_output <= cap + 1e-6
    assert new_output >= -1e-6


def test_constrained_model_falls_back_when_time_budget_exceeded(synthetic_mrio):
    """
    If the LP cannot finish within its time budget, `run_physical_risk_constrained` must
    fall back to the analytical Ghosh model and report a warning rather than silently
    returning a partial/unreliable result.
    """
    mrio = synthetic_mrio
    shock_maps = _shock(mrio, magnitude=0.5, index=0)

    # An effectively-zero time budget forces the fallback path deterministically.
    warning, delta_x = run_physical_risk_constrained(
        mrio["A"], mrio["X"], mrio["Y"], mrio["G"], shock_maps, time_limit=1e-9
    )

    assert warning is not None
    assert "falling back" in warning.lower()
    assert delta_x is not None


def test_constrained_solver_stable_with_near_zero_output_sector(synthetic_mrio):
    """
    Coverage test motivated by a real bug found via EXIOBASE 2021 data: a sector with a
    near-zero baseline gross output must not prevent the LP from solving. The original
    `BIG_M = 1e6 * max(weight_R)` formula scaled with 1/x0 for the smallest-output sector
    in the (real, ~8000-sector) subgraph, and there the resulting coefficient dynamic
    range exceeded double precision, causing HiGHS to fail immediately with "numerical
    difficulties" (status 4, nit=0). That exact failure was NOT reproducible at this
    small synthetic scale even with the old formula reinstated (HiGHS's presolve/scaling
    tolerates a single extreme value here) -- so this test does not by itself prove the
    fix's necessity; the real-data benchmark (see module docstring) is what demonstrated
    the bug and its fix. What this test does verify is the fix's invariant holds and the
    solver stays functional for a near-zero-output sector at this scale too.
    """
    mrio = synthetic_mrio
    A_df = mrio["A"].copy()
    X_df = mrio["X"].copy()
    Y_df = mrio["Y"].copy()
    # Inject one artificially tiny-output sector -- on real data this made
    # weight_R.max() = 1/x0 blow up to ~1.9e4 and BIG_M (formerly 1e6 * that) to ~1.9e10.
    # Its own final demand is scaled down to match, and its outgoing supply links are
    # zeroed so no other sector's capacity constraint requires more than it can produce
    # -- isolating the numerical-conditioning bug under test from an unrelated (and
    # correctly-reported) infeasibility that a tiny-output supplier would otherwise cause.
    tiny_label = mrio["labels"][1]
    A_df.loc[tiny_label, :] = 0.0
    X_df.loc[tiny_label, "GrossOutput"] = 1e-4
    Y_df.loc[tiny_label, "FinalDemand"] = 1e-5

    shock_maps = _shock(mrio, magnitude=0.3, index=0)
    warning, delta_x = run_physical_risk_constrained(
        A_df, X_df, Y_df, mrio["G"], shock_maps, time_limit=55
    )

    assert warning is None, f"Should solve the LP directly, not fall back: {warning}"
    assert delta_x is not None
