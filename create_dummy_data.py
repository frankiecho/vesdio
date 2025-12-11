
import pandas as pd
import numpy as np
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Define paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_DIR = os.getenv('DATA_DIR', os.path.join(PROJECT_ROOT, 'data'))

def generate_dummy_data():
    """
    Generates synthetic MRIO data and saves it to parquet files.
    This simulates a 2-country, 2-sector economy.
    """
    # Define the structure
    countries = ['C1', 'C2']
    sectors = ['S1', 'S2']
    labels = [f'{c}-{s}' for c in countries for s in sectors]
    size = len(labels)

    # Create directory if it doesn't exist
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

    # 1. Technical Coefficients Matrix (A)
    # Values represent the input required from sector i to produce one unit in sector j.
    # Column sums must be < 1.
    np.random.seed(42)
    A_matrix = np.random.rand(size, size) * 0.2  # Keep values low
    A_matrix = A_matrix / (A_matrix.sum(axis=0) * 2) # Ensure column sums are < 1
    A_df = pd.DataFrame(A_matrix, index=labels, columns=labels)

    # 2. Final Demand Vector (Y)
    # Represents the final consumption of goods/services from each sector.
    Y_matrix = np.random.randint(100, 1000, size=(size, 1))
    Y_df = pd.DataFrame(Y_matrix, index=labels, columns=['FinalDemand'])

    # 3. Environmental Extensions (E) - e.g., Land Use per unit of Gross Output
    # Represents the amount of land (e.g., in hectares) used per monetary unit of output.
    E_matrix = np.random.uniform(0.01, 0.5, size=(size, 1))
    E_df = pd.DataFrame(E_matrix, index=labels, columns=['LandUse'])
    
    # 4. Base Gross Output (x) - for transition risk scenario
    # We can derive a plausible x from A and Y: x = (I-A)^-1 * Y
    try:
        I = np.identity(size)
        L = np.linalg.inv(I - A_matrix)
        x_matrix = L @ Y_matrix
        x_df = pd.DataFrame(x_matrix, index=labels, columns=['GrossOutput'])
    except np.linalg.LinAlgError:
        # Fallback if matrix is singular
        x_matrix = Y_matrix * 2 
        x_df = pd.DataFrame(x_matrix, index=labels, columns=['GrossOutput'])


    # Save to parquet files
    A_df.to_parquet(os.path.join(DATA_DIR, 'EXIOBASE_A.parquet'))
    Y_df.to_parquet(os.path.join(DATA_DIR, 'EXIOBASE_Y.parquet'))
    E_df.to_parquet(os.path.join(DATA_DIR, 'EXIOBASE_E.parquet'))
    x_df.to_parquet(os.path.join(DATA_DIR, 'EXIOBASE_X.parquet')) # Save base output for later use

    print(f"Dummy data generated successfully in '{DATA_DIR}/'.")
    print("Labels:", labels)

if __name__ == '__main__':
    generate_dummy_data()
