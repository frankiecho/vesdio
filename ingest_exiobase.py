import pymrio
import pandas as pd
import numpy as np
import json
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Define paths
CURRENT_DIR = Path(os.getenv('DATA_DIR', Path(__file__).parent))
RAW_DATA_DIR = Path(CURRENT_DIR / 'raw_data')
EXIOBASE_DIR = Path(CURRENT_DIR / 'exiobase')
ENCORE_DATA_DIR = Path(CURRENT_DIR / 'ENCORE_data')

# Define start and end years
YEAR_START = int(os.getenv('YEAR_START', '2021'))
YEAR_END = int(os.getenv('YEAR_END', '2021'))

# Ensure directories exist
RAW_DATA_DIR.mkdir(exist_ok=True)
EXIOBASE_DIR.mkdir(exist_ok=True)

def ingest_and_save_exiobase(year=2021, float32=None):
    """
    Downloads and processes EXIOBASE 3 data for a given year, then
    saves the necessary matrices and labels in Parquet and JSON format.

    Args:
        year: The EXIOBASE reference year to ingest.
        float32: If True, save the dense L and G (Leontief/Ghosh inverse)
            matrices as float32 instead of float64, roughly halving their
            on-disk size. If None (default), this is controlled by the
            BUNDLE_FLOAT32 environment variable ("1"/"true" to enable).
            Default behavior (float64) is unchanged unless explicitly
            requested — this flag exists to produce a smaller, shippable
            offline data bundle (see `build_distributable_bundle` and
            docs/PACKAGING.md).
    """
    if float32 is None:
        float32 = os.environ.get('BUNDLE_FLOAT32', '0').strip().lower() in ('1', 'true', 'yes')

    print(f"Starting EXIOBASE ingestion for the year {year}.")
    print("This is a one-time process that can take a long time and consume significant disk space.")
    if float32:
        print("BUNDLE_FLOAT32 enabled: L and G will be saved as float32 (halved size) instead of float64.")

    # --- 1. Find or Download Data ---
    print("Checking for existing EXIOBASE zip file...")
    zip_path = None
    # Search for a zip file for the given year in the raw_data directory
    for f in RAW_DATA_DIR.glob(f'*{year}*.zip'):
        zip_path = f
        print(f"Found existing data file: {zip_path}")
        break

    if not zip_path:
        print("No existing data file found. Downloading now...")
        # This will download the data into the 'raw_data' directory
        try:
            zip_path = pymrio.download_exiobase3(storage_folder=RAW_DATA_DIR, years=year, system='ixi')
        except Exception as e:
            print(f"Failed to download EXIOBASE data. Error: {e}")
            print("Please check your internet connection and ensure you have sufficient disk space.")
            return
        print(f"Successfully downloaded data to {zip_path}")
    else:
        print(f"Using existing data from {zip_path}")

    # --- 2. Parse MRIO Data ---
    print("Parsing MRIO data... This may take several minutes.")
    try:
        mrio = pymrio.parse_exiobase3(zip_path)
    except Exception as e:
        print(f"Failed to parse the downloaded data. Error: {e}")
        return

    print("MRIO data parsed successfully.")

    # --- 3. Extract and Transform Matrices ---
    print("Extracting and transforming matrices (A, Y, E, X).")
    
    # Flatten the MultiIndex to the 'Region-Sector' format used by the app
    def flatten_index(mrio_df):
        #if isinstance(mrio_df, pd.DataFrame):
        #    mrio_df['index'] = mrio_df.index
        return mrio_df

    # A - Technical Coefficients Matrix
    A_df = flatten_index(mrio.A.copy())

    # Y - Final Demand Vector (summing all demand categories)
    Y_df_multi = mrio.Y.copy()
    Y_series = Y_df_multi.sum(axis=1)
    Y_df = pd.DataFrame(Y_series, columns=['FinalDemand'])
    Y_df = flatten_index(Y_df)

    # E - Environmental Extensions (Land Use)
    # Find all land use related satellite accounts
    if hasattr(mrio, "land"):
        land_use_indicators = mrio.land.unit[mrio.land.unit['unit'].str.contains('|'.join(['ha','km2']), na=False)].index
    else:
        land_use_indicators = pd.Series([])

    if land_use_indicators.empty:
        print("Warning: No land use indicators found in the environmental extensions.")
        # Create a dummy E matrix if none is found
        E_series = pd.Series(np.zeros(len(A_df)), index=A_df.index)
    else:
        #print(f"Found land use indicators: {list(land_use_indicators)}")
        # Sum up all land use types to get a single land use value per sector
        E_series = mrio.land.F.loc[land_use_indicators].sum(axis=0)
    
    E_df = pd.DataFrame(E_series, columns=['LandUse'])
    E_df = flatten_index(E_df)

    # X - Gross Output
    X_df = pd.DataFrame(mrio.x.copy())
    X_df.rename(columns={'indout': 'GrossOutput'}, inplace=True)

    # --- 4. Calculate All System Matrices using pymrio ---
    print("Calculating system matrices (L, G, etc.) using pymrio.calc_all()...")
    mrio.calc_all(include_ghosh=True)
    print("System matrices calculated.")

    L_df = mrio.L.copy()
    G_df = mrio.G.copy()

    # --- 6. Pre-calculate Default Scenario ---
    print("Pre-calculating default scenario based on largest trade flow...")
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

    # The Leontief inverse L_ij shows the total output from sector i required for one unit of final demand in sector j.
    # A high L_ij value means sector j is highly dependent on sector i, considering all direct and indirect links.
    # We want to find the largest dependency of any sector (j) on an international agricultural sector (i).
    
    # 1. Identify "large" agricultural producers (potential shock source)
    agri_outputs = X_df[X_df.index.get_level_values(1).isin(AGRICULTURE_SECTORS)]['GrossOutput']
    large_output_threshold = agri_outputs.quantile(0.9)
    large_agri_producers = agri_outputs[agri_outputs > large_output_threshold].index
    print(f"Identified {len(large_agri_producers)} large agricultural producers (output > {large_output_threshold:,.0f}).")
    
    # 2. Identify "large" sectors in general (potential home/consumer)
    all_outputs = X_df['GrossOutput']
    large_consumer_threshold = all_outputs.quantile(0.9)
    large_consumers = all_outputs[all_outputs > large_consumer_threshold].index
    print(f"Identified {len(large_consumers)} large consumer sectors (output > {large_consumer_threshold:,.0f}).")

    # 3. Filter the Leontief matrix to only consider flows from large producers to large consumers.
    # This finds the strongest dependencies between these two significant groups.
    L_filtered = L_df.loc[large_agri_producers, large_consumers]

    # Define regions to exclude from being a default home or shock region
    excluded_regions = ['WA', 'WL', 'WE', 'WF', 'WM']
    
    # Filter out excluded regions from both rows (producers) and columns (consumers)
    L_filtered = L_filtered[~L_filtered.index.get_level_values('region').isin(excluded_regions)]
    L_filtered = L_filtered.loc[:, ~L_filtered.columns.get_level_values('region').isin(excluded_regions)]

    # Set intra-country dependencies to zero to focus on international supply chains
    idx_regions = L_filtered.index.get_level_values(0).to_numpy()
    col_regions = L_filtered.columns.get_level_values(0).to_numpy()
    mask = idx_regions[:, None] == col_regions
    L_filtered[mask] = 0

    # Find the largest inter-country, inter-sector dependency.
    # We loop to ensure we don't pick a scenario where the shock and home sectors are the same.
    temp_L = L_filtered.to_numpy()
    max_dependency = 0
    
    for _ in range(10): # Try up to 10 times to find a valid pair
        if temp_L.size == 0 or temp_L.max() == 0:
            break
            
        pos = np.unravel_index(np.argmax(temp_L), temp_L.shape)
        producer_label = L_filtered.index[pos[0]]
        consumer_label = L_filtered.columns[pos[1]]
        
        if producer_label[1] != consumer_label[1]: # Check if sectors are different
            max_dependency = temp_L.max()
            break
        else:
            temp_L[pos] = 0 # Mask this value and search again
    else: # This 'else' belongs to the 'for' loop
        print("Could not find a suitable default scenario where shock and home sectors are different.")

    if max_dependency > 0:
        default_shock_region, default_shock_sector = producer_label
        default_home_region, default_home_sector = consumer_label
        print(f"Default scenario found: {producer_label} -> {consumer_label}")
    else:
        print("Could not determine default scenario, using fallbacks.")
        regions = list(mrio.get_regions())
        sectors = list(mrio.get_sectors())
        default_home_region = regions[0]
        default_home_sector = sectors[0]
        default_shock_region = regions[1] if len(regions) > 1 else regions[0]
        default_shock_sector = sectors[1] if len(sectors) > 1 else sectors[0]

    # --- 7. Save Processed Data ---
    output_dir = EXIOBASE_DIR / str(year)
    output_dir.mkdir(exist_ok=True)
    print(f"Saving processed matrices to {output_dir}")
    
    # L and G are dense NxN matrices and dominate the on-disk footprint;
    # downcasting them to float32 (when requested) roughly halves their size
    # with negligible precision loss for this application's purposes.
    L_to_save = L_df.astype(np.float32) if float32 else L_df
    G_to_save = G_df.astype(np.float32) if float32 else G_df

    A_df.to_parquet(output_dir / 'EXIOBASE_A.parquet')
    L_to_save.to_parquet(output_dir / 'EXIOBASE_L.parquet')
    G_to_save.to_parquet(output_dir / 'EXIOBASE_G.parquet')
    Y_df.to_parquet(output_dir / 'EXIOBASE_Y.parquet')
    E_df.to_parquet(output_dir / 'EXIOBASE_E.parquet')
    X_df.to_parquet(output_dir / 'EXIOBASE_X.parquet')

    # --- 8. Save Labels and Defaults ---
    print("Saving labels and default scenario to JSON.")
    labels_data = {
        'countries': list(mrio.get_regions()),
        'sectors': list(mrio.get_sectors()),
        'labels': A_df.index.tolist(),
        'defaults': {
            'home_region': default_home_region,
            'home_sector': default_home_sector,
            'shock_region': default_shock_region,
            'shock_sector': default_shock_sector
        }
    }
    with open(output_dir / 'labels.json', 'w') as f:
        json.dump(labels_data, f, indent=4)

    print("\n-----------------------------------------------------")
    print("Ingestion complete!")
    print("The application will now use the full EXIOBASE dataset.")
    print("-----------------------------------------------------")

def create_production_history():
    """
    Aggregates production data (Gross Output) across all processed years
    and saves it to a single Parquet file for historical analysis.
    """
    print("\nStarting post-processing: Creating production history...")
    
    yearly_x_dfs = []
    
    # Find all year directories
    year_dirs = [d for d in EXIOBASE_DIR.iterdir() if d.is_dir() and d.name.isdigit()]
    
    for year_dir in year_dirs:
        year = int(year_dir.name)
        x_path = year_dir / 'EXIOBASE_X.parquet'
        
        if x_path.exists():
            print(f"Loading production data for {year}...")
            x_df = pd.read_parquet(x_path)
            x_df['year'] = year
            yearly_x_dfs.append(x_df)
        else:
            print(f"Warning: EXIOBASE_X.parquet not found for year {year}.")

    if not yearly_x_dfs:
        print("No production data found to process.")
        return

    # Concatenate all yearly data
    all_years_df = pd.concat(yearly_x_dfs)
    
    # The index is already a MultiIndex of (region, sector), which is good.
    # We want to have years as columns.
    
    # Reset index to turn MultiIndex into columns
    all_years_df = all_years_df.reset_index()
    
    # Pivot the table
    production_history_df = all_years_df.pivot_table(
        index=['region', 'sector'], 
        columns='year', 
        values='GrossOutput'
    )
    
    # Save the aggregated data
    output_path = EXIOBASE_DIR / 'production_history.parquet'
    production_history_df.to_parquet(output_path)
    
    print(f"Successfully created and saved production history to {output_path}")
    print("Post-processing complete.")

def build_distributable_bundle(year=2021, output_dir=None, float32=True, include_ghosh=True):
    """
    Assembles the minimal offline data bundle needed to ship VESDIO as a
    self-contained desktop app for a single reference year, so end users
    never have to run the (multi-GB, multi-hour) EXIOBASE download/ingest
    pipeline themselves. See docs/PACKAGING.md for the full offline
    packaging story.

    This does NOT (re-)download or parse EXIOBASE; it expects
    `ingest_and_save_exiobase(year)` to have already been run so that
    `<DATA_DIR>/exiobase/<year>/*.parquet` and `labels.json` exist. Given
    that, it produces a bundle directory containing exactly:
        exiobase/<year>/EXIOBASE_{A,L,G,Y,E,X}.parquet
        exiobase/<year>/labels.json
        exiobase/production_history.parquet   (if available)
        ENCORE_data/encore_materiality.json    (if available)

    Args:
        year: The reference year to bundle (must already be ingested).
        output_dir: Destination directory for the bundle. Defaults to
            `<DATA_DIR>/bundle/<year>`.
        float32: If True (default for a *distributable* bundle), the L and
            G matrices are downcast to float32 in the bundle copy, roughly
            halving their size (e.g. ~512MB -> ~256MB each), regardless of
            what dtype they were originally ingested/saved as.
        include_ghosh: If False, omit G (the Ghosh/supply-side inverse)
            from the bundle entirely to further shrink it; supply-side
            ("ghosh") scenarios will then be unavailable offline for this
            bundle. Leontief-based scenarios are unaffected.

    Returns:
        The Path to the assembled bundle directory.
    """
    year_dir = EXIOBASE_DIR / str(year)
    if not (year_dir / 'EXIOBASE_A.parquet').exists():
        raise FileNotFoundError(
            f"No ingested EXIOBASE data found for {year} at {year_dir}. "
            f"Run ingest_and_save_exiobase({year}) first."
        )

    output_dir = Path(output_dir) if output_dir else (EXIOBASE_DIR.parent / 'bundle' / str(year))
    bundle_exiobase_year_dir = output_dir / 'exiobase' / str(year)
    bundle_exiobase_year_dir.mkdir(parents=True, exist_ok=True)

    print(f"Building distributable bundle for {year} at {output_dir} "
          f"(float32={float32}, include_ghosh={include_ghosh})")

    # A, Y, E, X, labels.json are copied unchanged - they are small
    # relative to the dense L/G inverses.
    for name in ('EXIOBASE_A.parquet', 'EXIOBASE_Y.parquet', 'EXIOBASE_E.parquet', 'EXIOBASE_X.parquet'):
        src = year_dir / name
        if src.exists():
            shutil.copy2(src, bundle_exiobase_year_dir / name)

    labels_src = year_dir / 'labels.json'
    if labels_src.exists():
        shutil.copy2(labels_src, bundle_exiobase_year_dir / 'labels.json')

    # L (and optionally G) are the big dense NxN matrices; re-save them at
    # the requested dtype for the bundle rather than assuming the source
    # year directory was already produced with BUNDLE_FLOAT32 set.
    dtype = np.float32 if float32 else np.float64

    L_df = pd.read_parquet(year_dir / 'EXIOBASE_L.parquet')
    L_df.astype(dtype).to_parquet(bundle_exiobase_year_dir / 'EXIOBASE_L.parquet')

    if include_ghosh:
        g_src = year_dir / 'EXIOBASE_G.parquet'
        if g_src.exists():
            G_df = pd.read_parquet(g_src)
            G_df.astype(dtype).to_parquet(bundle_exiobase_year_dir / 'EXIOBASE_G.parquet')
        else:
            print(f"Warning: {g_src} not found; bundle will not include G.")
    else:
        print("Skipping G (Ghosh inverse) in the bundle; supply-side (Ghosh) "
              "scenarios will be unavailable offline for this bundle.")

    # production_history.parquet powers the Historical tab; optional.
    history_src = EXIOBASE_DIR / 'production_history.parquet'
    if history_src.exists():
        shutil.copy2(history_src, output_dir / 'exiobase' / 'production_history.parquet')
    else:
        print(f"Note: {history_src} not found; Historical tab will be empty in this bundle. "
              f"Run create_production_history() to generate it.")

    # encore_materiality.json powers ecosystem-service shocks; optional.
    encore_src = ENCORE_DATA_DIR / 'encore_materiality.json'
    if encore_src.exists():
        bundle_encore_dir = output_dir / 'ENCORE_data'
        bundle_encore_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(encore_src, bundle_encore_dir / 'encore_materiality.json')
    else:
        print(f"Warning: {encore_src} not found; ecosystem-service shocks will be "
              f"unavailable in this bundle. Run ingest_encore.py first if needed.")

    print(f"Bundle ready at {output_dir}")
    return output_dir

if __name__ == '__main__':
    # Ingest data for all available years in parallel
    # This will create subdirectories in the 'data' folder for each year
    import multiprocessing

    years = list(range(YEAR_START, YEAR_END))
    
    # Use a Pool to manage worker processes
    # The number of processes will default to the number of available CPU cores
    #with multiprocessing.Pool() as pool:
    #    pool.map(ingest_and_save_exiobase, years)

    for y in years:
        ingest_and_save_exiobase(year = y)

    #create_production_history()