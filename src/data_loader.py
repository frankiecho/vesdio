import pandas as pd
import numpy as np
import os
import json
import dask.dataframe as dd
import sys
from functools import lru_cache
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
load_dotenv()

def get_base_data_path():
    """
    Determines the base path for data files.
    - For a packaged app (PyInstaller), it's a folder named 'data' inside the bundle.
    - For development, it uses the DATA_DIR from .env, defaulting to './data'.
    """
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        return Path(sys._MEIPASS) / 'data'
    else:
        # Running in a normal Python environment
        return Path(os.getenv('DATA_DIR', 'data'))

BASE_DATA_PATH = get_base_data_path()
EXIOBASE_DIR = BASE_DATA_PATH / 'exiobase'
ENCORE_DATA_DIR = BASE_DATA_PATH / 'ENCORE_data'

# --- DUMMY DATA GENERATION (FALLBACK) ---

def _generate_dummy_data(year=None):
    """
    Generates and saves synthetic MRIO data if real data isn't ingested.
    If a year is provided, it saves the data in a year-specific subfolder.
    """
    print("Generating synthetic dummy data as a fallback.")
    
    output_dir = EXIOBASE_DIR
    if year: # This path is now a Path object
        output_dir = EXIOBASE_DIR / str(year)
    
    # Use Path object methods
    output_dir.mkdir(parents=True, exist_ok=True)

    labels_path = output_dir / 'labels.json'

    countries = ['C1', 'C2']
    sectors = ['S1', 'S2']
    labels = [f'{c}-{s}' for c in countries for s in sectors]
    size = len(labels)

    # Save labels
    defaults = {
        'home_region': countries[0],
        'home_sector': sectors[0],
        'shock_region': countries[1] if len(countries) > 1 else countries[0],
        'shock_sector': sectors[1] if len(sectors) > 1 else sectors[0]
    }
    with open(labels_path, 'w') as f:
        json.dump({
            'countries': countries, 
            'sectors': sectors, 
            'labels': labels,
            'defaults': defaults
        }, f)

    # Create and save matrices
    np.random.seed(42)
    A_matrix = np.random.rand(size, size) * 0.2
    A_matrix = A_matrix / (A_matrix.sum(axis=0) * 2)
    A_df = pd.DataFrame(A_matrix, index=labels, columns=labels)
    A_df.to_parquet(output_dir / 'EXIOBASE_A.parquet')

    Y_matrix = np.random.randint(100, 1000, size=(size, 1))
    Y_df = pd.DataFrame(Y_matrix, index=labels, columns=['FinalDemand'])
    Y_df.to_parquet(output_dir / 'EXIOBASE_Y.parquet')

    E_matrix = np.random.uniform(0.01, 0.5, size=(size, 1))
    E_df = pd.DataFrame(E_matrix, index=labels, columns=['LandUse'])
    E_df.to_parquet(output_dir / 'EXIOBASE_E.parquet')

    I = np.identity(size)
    try:
        L_matrix = np.linalg.inv(I - A_matrix)
        x_matrix = L_matrix @ Y_matrix
    except np.linalg.LinAlgError:
        L_matrix = I # Fallback L
        x_matrix = Y_matrix * 2
    
    L_df = pd.DataFrame(L_matrix, index=labels, columns=labels)
    L_df.to_parquet(output_dir / 'EXIOBASE_L.parquet')

    x_df = pd.DataFrame(x_matrix, index=labels, columns=['GrossOutput'])
    x_df.to_parquet(output_dir / 'EXIOBASE_X.parquet')
    
    print(f"Generated and saved dummy data in {output_dir}.")

# --- MAIN DATA LOADERS ---

def load_labels_data(year=2021):
    """
    Loads labels and metadata for a specific year.
    """
    year_data_dir = EXIOBASE_DIR / str(year)
    labels_path = year_data_dir / 'labels.json'

    if not labels_path.exists():
        print(f"Data for year {year} not found.")
        _generate_dummy_data(year=year)

    with open(labels_path, 'r') as f:
        labels_data = json.load(f)
    
    countries = labels_data['countries']
    sectors = labels_data['sectors']
    labels = labels_data['labels']
    defaults = labels_data.get('defaults')

    return labels, countries, sectors, defaults

def load_mrio_matrices(year=2021, matrices_to_load=None, use_dask=False):
    """
    Loads specified MRIO matrices for a specific year.
    Handles loading the 'A' matrix from multiple parts.
    """
    if matrices_to_load is None:
        matrices_to_load = ['A', 'Y', 'E', 'X', 'L']

    year_data_dir = EXIOBASE_DIR / str(year)
    reader = dd.read_parquet if use_dask else pd.read_parquet
    concatenator = dd.concat if use_dask else pd.concat

    matrices = {}
    for matrix_name in matrices_to_load:
        try:
            matrix_path = year_data_dir / f'EXIOBASE_{matrix_name}.parquet'
            matrices[matrix_name] = reader(matrix_path)
        except FileNotFoundError as e:
            print(f"Error loading {e.filename}. File not found.")
            print("Please ensure the ingestion script has been run successfully for the selected year.")
            exit(1)
            
    if len(matrices_to_load) == 1:
        return matrices[matrices_to_load[0]]
    else:
        return tuple(matrices.get(name) for name in matrices_to_load)

@lru_cache(maxsize=1)
def load_production_history():
    """
    Loads the aggregated production history data from 'production_history.parquet'.
    """
    history_path = EXIOBASE_DIR / 'production_history.parquet'
    if not history_path.exists():
        print("Warning: production_history.parquet not found. Historical plot will be empty.")
        print("Run `ingest_exiobase.py` with `create_production_history()` to generate it.")
        return None
    
    return pd.read_parquet(history_path)

@lru_cache(maxsize=1)
def load_encore_materiality():
    """
    Loads the ENCORE materiality JSON data.
    """
    encore_materiality_path = ENCORE_DATA_DIR / 'encore_materiality.json'
    if not encore_materiality_path.exists():
        print(encore_materiality_path)
        print("Warning: encore_materiality.json not found. Materiality data will be unavailable.")
        print("Run `ingest_encore.py` to generate it.")
        return None
    
    with open(encore_materiality_path, 'r') as f:
        materiality_data = json.load(f)
    
    return materiality_data