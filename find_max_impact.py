import pandas as pd
import numpy as np
from src.data_loader import load_mrio_data
from src.scenario_modeler import run_physical_risk
import itertools
import multiprocessing
from functools import partial

def print_progress_bar(iteration, total, length=50, fill='█', print_end="\r"):
    """
    Call in a loop to create terminal progress bar
    """
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    print(f'\rProgress: |{bar}| {percent}% Complete', end=print_end)
    if iteration == total:
        print()

# Worker function for parallel processing
def calculate_impact(scenario, A, X, shock_magnitude):
    """
    Calculates the impact for a single scenario.
    """
    shock_sector, shock_country, home_country, home_sector = scenario

    # Define the shock
    shock_map = {
        'region': shock_country,
        'sector': shock_sector,
        'magnitude': shock_magnitude
    }

    # Run the simulation
    try:
        delta_y_req, _ = run_physical_risk(A, X, shock_map)
        impact = abs(delta_y_req.loc[(home_country, home_sector)])
        return (impact, scenario)
    except Exception:
        return None

def find_max_impact_scenario():
    """
    Finds the max impact scenario by focusing on high-value trade flows.
    """
    print("Loading MRIO data lazily with Dask...")
    A_dask, Y_dask, E_dask, X_dask, L_dask, LABELS, COUNTRIES, SECTORS, DEFAULTS = load_mrio_data(use_dask=True)
    print("Data loaded as Dask DataFrames.")

    AGRICULTURE_SECTORS = [
        'Cultivation of paddy rice', 'Cultivation of wheat', 'Cultivation of cereal grains nec',
        'Cultivation of vegetables, fruit, nuts', 'Cultivation of oil seeds',
        'Cultivation of sugar cane, sugar beet', 'Cultivation of plant-based fibers',
        'Cultivation of crops nec', 'Cattle farming', 'Pigs farming', 'Poultry farming',
        'Meat animals nec', 'Animal products nec', 'Raw milk', 'Wool, silk-worm cocoons',
        'Manure treatment (conventional), storage and land application',
        'Manure treatment (biogas), storage and land application',
        'Forestry, logging and related service activities (02)',
        'Fishing, operating of fish hatcheries and fish farms; service activities incidental to fishing (05)'
    ]

    valid_agri_sectors = [s for s in AGRICULTURE_SECTORS if s in SECTORS]
    shock_magnitude = 0.1  # 10% shock

    print("Identifying high-flow scenarios using Dask...")
    print("Calculating intermediate flows (Z matrix)...")
    Z_df_dask = A_dask.multiply(X_dask['GrossOutput'], axis=1)

    # Filter for agriculture sectors as producers (rows)
    # This is a dask operation, so it is lazy
    Z_agri_dask = Z_df_dask[Z_df_dask.index.get_level_values(1).isin(valid_agri_sectors)]

    print("Computing Z matrix to find high-flow threshold...")
    Z_agri = Z_agri_dask.compute()

    # Define "high flow" threshold as the 95th percentile of non-zero flows
    all_flows = Z_agri.to_numpy().flatten()
    non_zero_flows = all_flows[all_flows > 1e-9]
    if len(non_zero_flows) == 0:
        print("No non-zero flows found from agriculture sectors. Cannot proceed.")
        return
        
    high_flow_threshold = np.quantile(non_zero_flows, 0.95)
    print(f"Defined 'high flow' threshold as the 95th percentile: {high_flow_threshold:,.2f}")

    # Find all producer-consumer pairs above this threshold
    high_flow_pairs = Z_agri[Z_agri > high_flow_threshold].stack(future_stack=True).index.tolist()

    # Build the list of scenarios to test from these high-flow pairs
    scenario_combinations = []
    # The index from stack() is (shock_country, shock_sector, home_country, home_sector)
    for shock_country, shock_sector, home_country, home_sector in high_flow_pairs:
        # Apply constraints
        if shock_country == home_country or shock_sector == home_sector:
            continue
            
        # The worker function expects (shock_sector, shock_country, home_country, home_sector)
        scenario_combinations.append((shock_sector, shock_country, home_country, home_sector))

    total_combinations = len(scenario_combinations)
    if total_combinations == 0:
        print("No high-flow scenarios found matching the criteria.")
        return

    print(f"Found {total_combinations} high-flow scenarios to test.")
    print("This may take some time...")

    max_impact = 0
    best_scenario_info = None

    print("Computing A and X matrices for parallel processing...")
    A = A_dask.compute()
    X = X_dask.compute()

    # Use functools.partial to pass fixed arguments to the worker function
    worker_func = partial(calculate_impact, A=A, X=X, shock_magnitude=shock_magnitude)

    with multiprocessing.Pool() as pool:
        print(f"Using {pool._processes} worker processes.")
        results_iterator = pool.imap_unordered(worker_func, scenario_combinations)
        
        # Process results as they come in
        print_progress_bar(0, total_combinations)
        for i, result in enumerate(results_iterator):
            print_progress_bar(i + 1, total_combinations)
            if result is None:
                continue

            impact, scenario = result
            if impact > max_impact:
                max_impact = impact
                shock_sector, shock_country, home_country, home_sector = scenario
                best_scenario_info = {
                    'shock_country': shock_country,
                    'shock_sector': shock_sector,
                    'home_country': home_country,
                    'home_sector': home_sector,
                    'impact': max_impact
                }
                print(f"\nFound new max impact: {max_impact:,.2f}")
                print(f"Scenario: Shock '{shock_sector}' in {shock_country} -> Affects '{home_sector}' in {home_country}\n")

    print("\n--- Search Complete ---")
    if best_scenario_info:
        print("Best scenario found:")
        print(f"  Shock Country: {best_scenario_info['shock_country']}")
        print(f"  Shock Sector: {best_scenario_info['shock_sector']}")
        print(f"  Home Country: {best_scenario_info['home_country']}")
        print(f"  Home Sector: {best_scenario_info['home_sector']}")
        print(f"  Highest Total Impact: {best_scenario_info['impact']:,.2f} (from a {shock_magnitude*100}% shock)")
    else:
        print("Could not find a valid scenario with non-zero impact in the tested subset.")

if __name__ == '__main__':
    find_max_impact_scenario()
