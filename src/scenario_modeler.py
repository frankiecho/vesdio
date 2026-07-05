import time
import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy.optimize import linprog
import dask.dataframe as dd
import dask.array as da
from src.data_loader import load_mrio_matrices

def run_physical_risk(A_df, X_df, Y_df, L_df, shock_maps):
    """
    Models a physical risk scenario using a mixed input-output model.
    This implementation uses the partitioning method with the pre-calculated
    full Leontief inverse to ensure both accuracy and high performance.
    """
    # Matrices (A, X, Y, L) are passed as arguments to improve performance.
    
    # Identify exogenous (shocked) and endogenous (non-shocked) sectors
    all_labels = A_df.index
    exogenous_labels = pd.MultiIndex.from_tuples([
        (shock['region'], shock['sector']) for shock in shock_maps
    ])
    endogenous_labels = all_labels.difference(exogenous_labels)

    # Calculate the new, reduced output for the exogenous (shocked) sectors
    x_m_new = X_df.loc[exogenous_labels, 'GrossOutput'].copy()
    for shock in shock_maps:
        shock_label = (shock['region'], shock['sector'])
        reduction_factor = 1.0 - shock['magnitude']
        x_m_new.loc[shock_label] *= reduction_factor

    # Partition the A matrix and Y vector
    A_nm = A_df.loc[endogenous_labels, exogenous_labels]
    y_n = Y_df.loc[endogenous_labels, 'FinalDemand']

    # --- Core of the Mixed Model (Partitioning Method) ---
    # To avoid a costly matrix inversion at runtime, we use the pre-calculated
    # full Leontief inverse (L) to derive the inverse of the endogenous
    # sub-system (L_nn_inv) based on the method from Miller and Blair.
    # (I - A_nn)⁻¹ = L_nn - L_nm * (L_mm)⁻¹ * L_mn
    L_nn = L_df.loc[endogenous_labels, endogenous_labels].to_numpy()
    L_nm = L_df.loc[endogenous_labels, exogenous_labels].to_numpy()
    L_mn = L_df.loc[exogenous_labels, endogenous_labels].to_numpy()
    L_mm = L_df.loc[exogenous_labels, exogenous_labels].to_numpy()

    # This inversion is very fast as L_mm is small (its size is the number of shocked sectors)
    L_mm_inv = np.linalg.inv(L_mm)
    
    # This is the Leontief inverse for the endogenous-only system, derived efficiently.
    endogenous_leontief_inv = L_nn - (L_nm @ L_mm_inv @ L_mn)

    # --- Fixed Calculation for New Endogenous Output (finding A1) ---
    # The exogenous (shocked) sectors are specified on a *quantity* basis: x_m is fixed
    # at its new, post-shock level. This is the textbook Miller & Blair "mixed model"
    # (quantity-type exogenous variables): x_n = (I - A_nn)⁻¹ * (A_nm @ x_m_new + y_n).
    # A_nm (rows=endogenous suppliers, columns=exogenous/shocked users) gives exactly the
    # inputs the shocked sectors buy from the rest of the economy, evaluated at their new
    # (reduced) output level -- this correctly captures the backward-linkage/demand effect
    # of the shock (shocked sectors buy less from their suppliers because they produce less).
    #
    # The previous implementation instead computed a "delta" via A_mn (the *opposite*
    # direction: inputs shocked sectors used to *supply* to endogenous sectors) and added
    # it to final demand y_n as a "negative final demand" workaround. That conflated a
    # forward-linkage/rationing effect (inputs no longer available to customers of the
    # shocked sector) with demand-side final-demand accounting, and had no theoretical
    # basis in the Leontief demand-driven framework -- it could also drive outputs
    # negative for large shocks. A true forward-linkage/rationing effect (what happens
    # when a customer physically cannot obtain enough input) is a *supply-constrained*
    # phenomenon, not a demand-driven one; it is properly modeled by the Ghosh model
    # (`run_physical_risk_ghosh`) and, more rigorously, the `constrained` LP model
    # (`run_physical_risk_constrained`) below.
    x_n_new_values = endogenous_leontief_inv @ (y_n.to_numpy() + A_nm.to_numpy() @ x_m_new.to_numpy())
    x_n_new = pd.Series(x_n_new_values, index=endogenous_labels)

    # Combine new outputs and calculate the total change in production (Δx)
    x_new = pd.concat([x_n_new, x_m_new])
    x_new.name = 'GrossOutput'
    # Reindex x_new to match the original order and structure of X_df.
    # This is crucial to prevent alignment errors during subtraction.
    x_new = x_new.reindex(X_df.index)
    # Clamp gross output to be non-negative -- a large shock combined with second-order
    # demand effects should never be able to produce a negative level of production.
    x_new = x_new.clip(lower=0)
    delta_x = x_new - X_df['GrossOutput']

    # Calculate the resulting change in final demand (Δy)
    # Efficiently calculate (I - A) without creating a large identity matrix
    I_minus_A = -A_df.to_numpy()
    I_minus_A[np.arange(len(all_labels)), np.arange(len(all_labels))] += 1
    delta_y_req_values = I_minus_A @ delta_x.to_numpy()
    delta_y_req = pd.Series(delta_y_req_values, index=all_labels)

    return delta_y_req, delta_x

def run_physical_risk_ghosh(A_df, X_df, G_df, shock_maps):
    """
    Models a physical risk scenario using the Ghosh supply-side model.
    This model is generally more suitable for simulating pure supply constraints.
    """
    # 1. Identify Shocked vs. Non-Shocked Sectors
    all_labels = A_df.index
    exogenous_labels = pd.MultiIndex.from_tuples([
        (shock['region'], shock['sector']) for shock in shock_maps
    ], names=['region', 'sector'])
    endogenous_labels = all_labels.difference(exogenous_labels)

    # 2. Calculate New Output for Shocked Sectors
    x_m_new = X_df.loc[exogenous_labels, 'GrossOutput'].copy()
    for shock in shock_maps:
        shock_label = (shock['region'], shock['sector'])
        reduction_factor = 1.0 - shock['magnitude']
        x_m_new.loc[shock_label] *= reduction_factor

    # 3. Partition the pre-computed Ghosh inverse matrix
    # Partition the Ghosh inverse matrix
    G_nn = G_df.loc[endogenous_labels, endogenous_labels].to_numpy()
    G_mn = G_df.loc[exogenous_labels, endogenous_labels].to_numpy()
    G_mm = G_df.loc[exogenous_labels, exogenous_labels].to_numpy()

    G_mm_inv = np.linalg.inv(G_mm)

    # --- Corrected Ghosh Mixed-Model Calculation (Stable Formulation) ---
    # The previous formulation was unstable. The correct approach is to calculate the
    # change in output of the shocked sectors (delta_x_m) and propagate this change
    # forward through the supply chain using the appropriate part of the Ghosh inverse.
    x_m_old = X_df.loc[exogenous_labels, 'GrossOutput'].to_numpy()
    delta_x_m_row = (x_m_new.to_numpy() - x_m_old).T
    
    # The change in output of the endogenous sectors is delta_x_n' = delta_x_m' * G_mm^-1 * G_mn
    delta_x_n_values = (delta_x_m_row @ G_mm_inv @ G_mn)
    x_n_new_values = X_df.loc[endogenous_labels, 'GrossOutput'].to_numpy() + delta_x_n_values
    x_n_new = pd.Series(x_n_new_values, index=endogenous_labels)

    # 4. Combine Results and Calculate Change
    x_new = pd.concat([x_n_new, x_m_new]).reindex(X_df.index)
    # Clamp gross output to be non-negative (finding A1) -- large shocks propagated
    # through the Ghosh inverse should never be allowed to imply negative production.
    x_new = x_new.clip(lower=0)
    delta_x = x_new - X_df['GrossOutput']

    return None, delta_x # delta_y_req is not relevant for the Ghosh model

def _shock_reachable_subgraph(A_sparse, all_labels, exogenous_labels, max_hops=4, min_weight=1e-9, max_fraction=0.5):
    """
    Reduce the full sector set to the subgraph reachable from the shocked ("exogenous")
    sectors within `max_hops` supply-chain hops, i.e. sectors that use -- directly or
    transitively -- an input from a shocked sector. Solving the constrained LP only over
    this (typically much smaller) subgraph is what keeps `run_physical_risk_constrained`
    inside its wall-clock budget on a large MRIO (e.g. the ~8000-sector EXIOBASE system),
    instead of building an LP over the full system.

    `A_sparse` must be a scipy.sparse matrix (rows=supplying sector, columns=using
    sector) so the hop expansion never densifies the full system.

    Returns a sorted list of integer positions (into `all_labels`) forming the reduced
    subgraph, or None if the reduction does not shrink the problem enough to be worth it
    (more than `max_fraction` of all sectors reached), signalling "solve the full system".
    """
    n = A_sparse.shape[0]
    label_to_pos = {label: i for i, label in enumerate(all_labels)}
    frontier = {label_to_pos[l] for l in exogenous_labels if l in label_to_pos}
    reached = set(frontier)
    A_csr = A_sparse.tocsr()

    for _ in range(max_hops):
        if not frontier:
            break
        # Sectors that buy a non-negligible input from any sector in the frontier are
        # "downstream" of the shock and must be included in the reduced system.
        sub = A_csr[sorted(frontier), :].tocoo()
        new_nodes = {c for c, w in zip(sub.col, sub.data) if abs(w) > min_weight} - reached
        if not new_nodes:
            break
        reached |= new_nodes
        frontier = new_nodes
        if len(reached) > n * max_fraction:
            return None

    return sorted(reached)


def run_physical_risk_constrained(A_df, X_df, Y_df, G_df, shock_maps, time_limit=55, max_hops=4, max_fraction=0.5):
    """
    Supply-constrained reallocation model ("rigorous"/constrained mode), in the
    MRIA / Koks & Thissen linear-programming family. Unlike the fast analytical
    Leontief/Ghosh models, this explicitly enforces non-negativity and a hard capacity
    ceiling on the shocked sectors by solving a linear program, so it *cannot* produce a
    negative or above-baseline-capacity gross output by construction.

    Problem reduction
    ------------------
    Sectors outside the shock-reachable subgraph (see `_shock_reachable_subgraph`) are
    held fixed at their baseline gross output and excluded from the LP's decision
    variables; only sectors within a few supply-chain hops of the shock are solved for.
    This keeps the LP small even though the full system (A/X/Y) may have ~8000 sectors.

    LP formulation
    ---------------
    Let R be the (small) reduced set of sector positions. For i in R:

      Variables:
        x_i  -- new gross output for sector i
        s_i  -- unmet final demand / rationing slack (used only if strictly necessary
                 for feasibility, e.g. a shocked sector's own final demand alone would
                 exceed its reduced capacity)
        d_i  -- auxiliary variable for |x_i - x0_i| (linearizes the L1 objective)

      Objective (minimize relative deviation from baseline output; heavily penalize
      rationing so it is only used when the LP would otherwise be infeasible):

          minimize   sum_i d_i / max(x0_i, eps)   +   BIG_M * sum_i s_i

      Constraints:
        (1) |x_i - x0_i| <= d_i        <=>   x_i - d_i <= x0_i   and   -x_i - d_i <= -x0_i
        (2) IO balance with rationing:
                x_i - sum_{j in R} A[i,j] * x_j + s_i >= y_i + fixed_input_term_i
            i.e. sector i's own production must cover intermediate demand from its
            in-subgraph customers plus final demand, net of any rationed/unmet demand.
            `fixed_input_term_i = sum_{j not in R} A[i,j] * x0_j` accounts for demand
            from sectors held fixed outside the reduced subgraph. This constraint is
            what forces *downstream* sectors to shrink output when they can no longer
            source enough input from a shocked upstream sector -- the genuine supply
            constraint that the old A1 "negative final demand" heuristic tried (and
            failed) to approximate.
        (3) Capacity bounds: 0 <= x_i <= cap_i, where cap_i = x0_i * (1 - magnitude) for
            shocked sectors and cap_i = x0_i for all other sectors in R (no sector can
            expand past baseline output in this short-run model).
        (4) 0 <= s_i <= max(y_i, 0)

    Solver & time budget
    ----------------------
    scipy.optimize.linprog(method="highs") with all constraint matrices built as
    scipy.sparse matrices restricted to the (already-reduced) subgraph -- the full
    n x n system is never densified or even instantiated as an LP. A hard wall-clock
    budget is enforced both by HiGHS's own `time_limit` option and an outer timer; if
    the solve does not finish with an optimal status inside the budget, this function
    falls back to the fast analytical Ghosh model and returns a warning string instead
    of a partial/unreliable LP solution.

    Returns
    -------
    (warning, delta_x): `warning` is None when the LP solved successfully, otherwise a
    human-readable string describing why the analytical fallback was used.
    """
    start_time = time.time()

    all_labels = A_df.index
    exogenous_labels = [(shock['region'], shock['sector']) for shock in shock_maps]
    shock_lookup = {label: shock['magnitude'] for label, shock in zip(exogenous_labels, shock_maps)}

    def _fallback(reason):
        warning = (
            f"Constrained LP solver {reason} (budget {time_limit}s); falling back to the "
            "analytical Ghosh supply-side model. Results reflect the fallback model, not "
            "the constrained LP."
        )
        _, delta_x_fallback = run_physical_risk_ghosh(A_df, X_df, G_df, shock_maps)
        return warning, delta_x_fallback

    try:
        n = len(all_labels)
        x0 = X_df['GrossOutput'].to_numpy()
        y = Y_df['FinalDemand'].to_numpy()
        A_sparse = sp.csr_matrix(A_df.to_numpy())

        subgraph = _shock_reachable_subgraph(
            A_sparse, all_labels, exogenous_labels, max_hops=max_hops, max_fraction=max_fraction
        )
        R_positions = list(range(n)) if subgraph is None else subgraph
        R_set = set(R_positions)
        F_positions = [p for p in range(n) if p not in R_set]
        n_R = len(R_positions)

        x0_R = x0[R_positions]
        y_R = y[R_positions]
        eps = 1e-6

        # Capacity ceiling: baseline output for all sectors in R, reduced for shocked ones.
        cap_R = x0_R.copy()
        for idx, pos in enumerate(R_positions):
            label = all_labels[pos]
            if label in shock_lookup:
                cap_R[idx] = max(0.0, x0_R[idx] * (1.0 - shock_lookup[label]))

        # Demand placed on R-sectors by sectors held fixed outside the subgraph.
        A_RR = A_sparse[R_positions, :][:, R_positions].tocsr()
        if F_positions:
            A_RF = A_sparse[R_positions, :][:, F_positions].tocsr()
            fixed_input_term = np.asarray(A_RF @ x0[F_positions]).ravel()
        else:
            fixed_input_term = np.zeros(n_R)

        weight_R = 1.0 / np.maximum(x0_R, eps)
        BIG_M = 1e6 * max(weight_R.max(initial=1.0), 1.0)

        # --- Objective: c^T @ [x, s, d] ---
        c = np.concatenate([np.zeros(n_R), np.full(n_R, BIG_M), weight_R])

        I_R = sp.identity(n_R, format='csr')
        Z_R = sp.csr_matrix((n_R, n_R))

        # (1a) x_i - d_i <= x0_i
        row_d1 = sp.hstack([I_R, Z_R, -I_R], format='csr')
        b_d1 = x0_R
        # (1b) -x_i - d_i <= -x0_i
        row_d2 = sp.hstack([-I_R, Z_R, -I_R], format='csr')
        b_d2 = -x0_R
        # (2) -x_i + sum_j A_RR[i,j] x_j - s_i <= -(y_i + fixed_input_term_i)
        row_bal = sp.hstack([A_RR - I_R, -I_R, Z_R], format='csr')
        b_bal = -(y_R + fixed_input_term)

        A_ub = sp.vstack([row_bal, row_d1, row_d2], format='csr')
        b_ub = np.concatenate([b_bal, b_d1, b_d2])

        bounds = (
            [(0, cap_R[i]) for i in range(n_R)]
            + [(0, max(y_R[i], 0.0)) for i in range(n_R)]
            + [(0, None) for _ in range(n_R)]
        )

        remaining = max(1.0, time_limit - (time.time() - start_time))
        res = linprog(
            c=c, A_ub=A_ub, b_ub=b_ub, bounds=bounds,
            method='highs', options={'time_limit': remaining}
        )

        elapsed = time.time() - start_time
        if elapsed > time_limit or not res.success:
            reason = "exceeded its time budget" if elapsed > time_limit else f"failed to converge ({res.message})"
            return _fallback(reason)

        x_R_solution = np.clip(res.x[:n_R], 0.0, None)

        x_new = x0.copy()
        x_new[R_positions] = x_R_solution
        x_new = pd.Series(x_new, index=all_labels, name='GrossOutput')
        delta_x = x_new - X_df['GrossOutput']

        return None, delta_x

    except Exception as exc:  # pragma: no cover - defensive fallback for any solver failure
        return _fallback(f"raised an error ({exc})")


def run_transition_risk(shock_map):
    """
    Models a transition risk scenario (supply-side shock).
    """
    A_df, E_df, X_df = load_mrio_matrices(matrices_to_load=['A', 'E', 'X'])

    shock_label = (shock_map['region'], shock_map['sector'])
    land_set_aside_percent = shock_map['magnitude']

    base_output_val = compute(X_df.loc[shock_label, 'GrossOutput'])
    if hasattr(base_output_val, 'iloc'):
        base_output = base_output_val.iloc[0]
    else:
        base_output = base_output_val
    output_reduction = base_output * land_set_aside_percent
    
    delta_x_direct = pd.Series(0.0, index=A_df.index)
    delta_x_direct[shock_label] = -output_reduction
    npartitions = A_df.npartitions if hasattr(A_df, 'npartitions') else 1
    delta_x_direct = dd.from_pandas(delta_x_direct, npartitions=npartitions)

    A = A_df.to_dask_array(lengths=True)
    I = da.eye(A.shape[0])
    I_minus_A = I - A
    
    delta_y_req_values = I_minus_A @ delta_x_direct.to_dask_array(lengths=True)
    delta_y_req = dd.from_dask_array(delta_y_req_values, index=A_df.index)

    return compute(delta_y_req), compute(delta_x_direct)

def attribute_output_change(model_method, delta_x, shock_maps, home_region, home_sector, L_df=None, G_df=None, A_df=None):
    """
    Attributes the change in a sector's gross output to the initial shock(s)
    using the appropriate inverse matrix (Leontief or Ghosh) to capture higher-order effects,
    or first-order effects for other models.
    """
    home_label = (home_region, home_sector)
    # The total impact is the change in gross output for the home sector.
    total_impact = abs(delta_x.loc[home_label])
    
    if total_impact < 1e-10:
        return {
            'message': 'No significant output change in your home sector.',
            'total_impact': 0,
            'causes': {}
        }
    
    # Identify the initial shocks from the delta_x vector.
    shock_labels = pd.MultiIndex.from_tuples([(s['region'], s['sector']) for s in shock_maps])
    initial_shocks = delta_x[delta_x.index.isin(shock_labels)].abs()
    
    # Use the appropriate matrix to calculate how much of each initial shock
    # contributes to the total production loss in the 'home' sector.
    impact_causes = {}
    if model_method == 'leontief' and L_df is not None:
        # Leontief: L_ij shows how much output from i is needed for 1 unit of final demand in j.
        # The contribution of a shock in sector i to sector j is L_ji * delta_x_i.
        # NOTE: this is a *backward-linkage* (demand-side) attribution and is
        # consistent with the demand-driven delta_x. It can legitimately be ~0
        # when the shocked sector is *upstream* of home (home does not supply the
        # shocked sector), which is not a bug — that upstream/forward "my supplier
        # failed" effect is a supply-side phenomenon captured by the Ghosh branch
        # below. Verified on a full multi-region MRIO (pymrio.load_test) where
        # Leontief attribution is non-zero and matches |delta_x[home]|; the
        # earlier zero seen on the degenerate 2x2 dummy was a topology artifact.
        for shock_label, shock_value in initial_shocks.items():
            contribution = L_df.loc[home_label, shock_label] * shock_value
            impact_causes[f"{shock_label[0]} - {shock_label[1]}"] = contribution
    elif model_method == 'ghosh' and G_df is not None:
        # Ghosh: G_ij shows how much output from j is caused by 1 unit of primary input in i.
        # The contribution of a shock in sector i to sector j is G_ij * delta_x_i.
        for shock_label, shock_value in initial_shocks.items():
            contribution = G_df.loc[shock_label, home_label] * shock_value
            impact_causes[f"{shock_label[0]} - {shock_label[1]}"] = contribution
    elif A_df is not None: # Fallback for Lenzen or other models (first-order impact)
        # A_ij shows direct input from i needed for 1 unit of output of j.
        for shock_label, shock_value in initial_shocks.items():
            contribution = A_df.loc[shock_label, home_label] * shock_value
            impact_causes[f"{shock_label[0]} - {shock_label[1]}"] = contribution
            
    # Exclude the home sector's contribution to its own impact from the attribution charts
    home_label_str = f"{home_region} - {home_sector}"
    external_causes = {k: v for k, v in impact_causes.items() if k != home_label_str}

    # Normalize the external causes to sum to 100%
    total_attributed_external = sum(external_causes.values())
    sorted_external_causes = sorted(external_causes.items(), key=lambda item: item[1], reverse=True)
    attribution = {
        'total_impact': total_impact,
        'causes': {label: (impact / total_attributed_external) * 100 if total_attributed_external > 0 else 0
                   for label, impact in sorted_external_causes},
        # Absolute (non-renormalized) contributions, in the same units as delta_x, so the
        # true magnitude of each cause is still visible alongside the normalized percentages above.
        'causes_absolute': {label: impact for label, impact in sorted_external_causes},
        'message': f'Change in Gross Output for {home_sector}'
    }

    return attribution

def attribute_portfolio_change(model_method, delta_x, shock_maps, portfolio_data, L_df=None, G_df=None, A_df=None):
    """
    Attributes the change in a portfolio's total value to the initial shock(s).
    It calculates the weighted contribution of each shock to each portfolio asset and sums them up.
    """
    total_portfolio_impact = 0
    portfolio_causes = {}

    shock_labels = pd.MultiIndex.from_tuples([(s['region'], s['sector']) for s in shock_maps])
    initial_shocks = delta_x[delta_x.index.isin(shock_labels)].abs()

    # Iterate through each asset in the portfolio
    for asset in portfolio_data:
        home_label = (asset['region'], asset['sector'])
        asset_weight = asset['weight'] / 100.0
        total_portfolio_impact += abs(delta_x.loc[home_label]) * asset_weight

        # Calculate the contribution of each external shock to this specific asset
        asset_impact_causes = {}
        if model_method == 'leontief' and L_df is not None:
            for shock_label, shock_value in initial_shocks.items():
                contribution = L_df.loc[home_label, shock_label] * shock_value
                asset_impact_causes[f"{shock_label[0]} - {shock_label[1]}"] = contribution
        elif model_method == 'ghosh' and G_df is not None:
            for shock_label, shock_value in initial_shocks.items():
                contribution = G_df.loc[shock_label, home_label] * shock_value
                asset_impact_causes[f"{shock_label[0]} - {shock_label[1]}"] = contribution
        
        # Add the weighted contributions to the overall portfolio causes
        for cause, impact in asset_impact_causes.items():
            portfolio_causes[cause] = portfolio_causes.get(cause, 0) + (impact * asset_weight)

    if total_portfolio_impact < 1e-10:
        return {
            'message': 'No significant output change in your portfolio.',
            'total_impact': 0,
            'causes': {}
        }

    # Normalize to 100%
    total_attributed = sum(portfolio_causes.values())
    sorted_portfolio_causes = sorted(portfolio_causes.items(), key=lambda item: item[1], reverse=True)
    attribution = {
        'total_impact': total_portfolio_impact,
        'causes': {label: (impact / total_attributed) * 100 if total_attributed > 0 else 0
                   for label, impact in sorted_portfolio_causes},
        # Absolute (non-renormalized) contributions, in the same units as delta_x.
        'causes_absolute': {label: impact for label, impact in sorted_portfolio_causes},
        'message': 'Change in Total Portfolio Value'
    }
    return attribution

def is_dask(data):
    return isinstance(data, (dd.DataFrame, dd.Series, da.Array))

def compute(data):
    if isinstance(data, (dd.DataFrame, dd.Series, da.Array)):
        return data.compute()
    return data