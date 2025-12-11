
import numpy as np
import pandas as pd

def calculate_leontief_inverse(A_df):
    """
    Calculates the Leontief inverse matrix L = (I - A)^-1.

    Args:
        A_df (pd.DataFrame): Technical coefficients matrix.

    Returns:
        pd.DataFrame: The Leontief inverse matrix, or None if inversion fails.
    """
    A = A_df.to_numpy()
    I = np.identity(A.shape[0])
    
    try:
        L = np.linalg.inv(I - A)
        L_df = pd.DataFrame(L, index=A_df.index, columns=A_df.columns)
        return L_df
    except np.linalg.LinAlgError:
        print("Error: Matrix (I-A) is singular and cannot be inverted.")
        return None
