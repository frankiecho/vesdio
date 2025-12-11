import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add the project root to the Python path to allow imports from 'src'
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@pytest.fixture(scope="session")
def dummy_mrio_data():
    """
    Creates a small, consistent set of MRIO data for testing purposes.
    Models a 2-country, 2-sector economy.
    C1-S1: Farming
    C1-S2: Food Processing (depends on C1-S1)
    C2-S1: Mining
    C2-S2: Manufacturing (depends on C2-S1)
    """
    idx = pd.MultiIndex.from_tuples([
        ('C1', 'Farming'), ('C1', 'Food Processing'),
        ('C2', 'Mining'), ('C2', 'Manufacturing')
    ], names=['region', 'sector'])

    # A Matrix (Technical Coefficients)
    A = pd.DataFrame(np.zeros((4, 4)), index=idx, columns=idx)
    A.loc[('C1', 'Farming'), ('C1', 'Food Processing')] = 0.4  # Food Proc needs Farming
    A.loc[('C2', 'Mining'), ('C2', 'Manufacturing')] = 0.5   # Manuf needs Mining
    A.loc[('C1', 'Farming'), ('C2', 'Manufacturing')] = 0.1  # Manuf needs some Farming

    # Y Vector (Final Demand)
    Y = pd.DataFrame({'FinalDemand': [100, 150, 80, 200]}, index=idx)

    # L and X matrices
    I = np.identity(4)
    L_matrix = np.linalg.inv(I - A.to_numpy())
    L = pd.DataFrame(L_matrix, index=idx, columns=idx)
    X_matrix = L_matrix @ Y['FinalDemand'].to_numpy()
    X = pd.DataFrame({'GrossOutput': X_matrix}, index=idx)

    # G Matrix (Ghosh Inverse)
    Z_matrix = A.to_numpy() * X['GrossOutput'].to_numpy()
    x_inv = 1 / X['GrossOutput'].to_numpy()
    B_matrix = (Z_matrix.T * x_inv).T
    G_matrix = np.linalg.inv(I - B_matrix)
    G = pd.DataFrame(G_matrix, index=idx, columns=idx)

    # Mock country mapping
    country_mapping = {'C1': 'Country 1', 'C2': 'Country 2'}
    COLOR_PALETTE = {
        'blue': "#0072B2", 'red': "#D55E00", 'amber': "#E69F00",
        'beige': "#F0E442", 'green': "#009E73", 'grey': "#999999"
    }

    return {
        "A": A, "X": X, "Y": Y, "L": L, "G": G,
        "country_mapping": country_mapping,
        "COLOR_PALETTE": COLOR_PALETTE
    }