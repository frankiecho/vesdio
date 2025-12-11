import numpy as np
import pandas as pd
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
    A_mn = A_df.loc[exogenous_labels, endogenous_labels]
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

    # --- Corrected Calculation for New Endogenous Output ---
    # The standard mixed-model equation is x_n = (I - A_nn)⁻¹ * (A_nm * x_m_new + y_n).
    # However, this formula assumes the shock is on the *demand* side. For a supply-side
    # shock where inputs are constrained, we must adjust the final demand vector.
    # We calculate the change in inputs required by endogenous sectors from the shocked sectors.
    x_m_old = X_df.loc[exogenous_labels, 'GrossOutput'].to_numpy()
    delta_x_m = x_m_new.to_numpy() - x_m_old
    unavailable_inputs = A_mn.to_numpy().T @ delta_x_m
    
    # Calculate the new equilibrium output for endogenous sectors.
    # We treat the reduction in available inputs as a negative final demand shock.
    # This correctly propagates the supply constraint through the endogenous economy.
    x_n_new_values = endogenous_leontief_inv @ (y_n.to_numpy() + unavailable_inputs)
    x_n_new = pd.Series(x_n_new_values, index=endogenous_labels)

    # Combine new outputs and calculate the total change in production (Δx)
    x_new = pd.concat([x_n_new, x_m_new])
    x_new.name = 'GrossOutput'
    # Reindex x_new to match the original order and structure of X_df.
    # This is crucial to prevent alignment errors during subtraction.
    x_new = x_new.reindex(X_df.index)
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
    delta_x = x_new - X_df['GrossOutput']
    
    return None, delta_x # delta_y_req is not relevant for the Ghosh model

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
    attribution = {
        'total_impact': total_impact,
        'causes': {label: (impact / total_attributed_external) * 100 if total_attributed_external > 0 else 0
                   for label, impact in sorted(external_causes.items(), key=lambda item: item[1], reverse=True)},
        'message': f'Change in Gross Output for {home_sector}'
    }
    
    return attribution

def is_dask(data):
    return isinstance(data, (dd.DataFrame, dd.Series, da.Array))

def compute(data):
    if isinstance(data, (dd.DataFrame, dd.Series, da.Array)):
        return data.compute()
    return data