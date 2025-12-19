import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
import os
import json

load_dotenv()

CURRENT_DIR = Path(__file__).parent

EXIOBASE_DIR = Path(os.getenv('DATA_DIR', CURRENT_DIR))  / 'ENCORE_data'

# Load dependency materiality ratings
def load_dependency_materiality_ratings():
    filepath = EXIOBASE_DIR / 'Updated ENCORE knowledge base September 2025' /  'ENCORE files' / '06. Dependency mat ratings.csv'
    df = pd.read_csv(filepath, index_col='ISIC Unique code')
    return df

# Load crosswalk between ENCORE sectors and EXIOBASE sectors
def load_encore_exiobase_crosswalk():
    filepath = EXIOBASE_DIR / 'Updated ENCORE knowledge base September 2025' /  'Crosswalk tables' / 'EXIOBASE NACE ISIC crosswalk.csv'
    df = pd.read_csv(filepath, index_col='ISIC Unique Class code')
    return df

if __name__ == '__main__':
    dep_mat = load_dependency_materiality_ratings()
    crosswalk = load_encore_exiobase_crosswalk()

    # Ensure indices are strings for matching
    dep_mat.index = dep_mat.index.astype(str)
    crosswalk.index = crosswalk.index.astype(str)

    # First, attempt a direct merge on the full ISIC code (the index)
    dep_mat_merged = pd.merge(dep_mat, crosswalk, on=['ISIC Section', 'ISIC Division', 'ISIC Group', 'ISIC Class'], how='left', suffixes = ("", ""))

    # Identify rows that did not find a match by checking for nulls in the 'EXIOBASE' column,
    # which should have been brought in from the crosswalk file.
    unmatched_mask = dep_mat_merged['EXIOBASE'].isnull()
    unmatched_rows = dep_mat_merged[unmatched_mask]

    if not unmatched_rows.empty:
        print(f"Found {len(unmatched_rows)} ENCORE sectors that did not match on the full ISIC code. Attempting to match by ISIC group...")

        unmatched_merged = pd.merge(dep_mat, crosswalk.drop('ISIC Class', axis=1), on=['ISIC Section', 'ISIC Division', 'ISIC Group'], how='left', suffixes = ("", ""))
        dep_mat_merged = pd.concat([dep_mat_merged[~unmatched_mask], unmatched_merged])

    # After attempting to fix unmatched rows, we define the final joined dataframe
    # A row is considered joined if it has a value in the 'EXIOBASE' column
    final_unmatched_mask = dep_mat_merged['EXIOBASE'].isnull()
    dep_mat_joined = dep_mat_merged[~final_unmatched_mask]
    dep_mat_unjoined = dep_mat_merged[final_unmatched_mask]

    if not dep_mat_unjoined.empty:
        print(f"Warning: After attempting group matching, {len(dep_mat_unjoined)} ENCORE sectors still could not be matched to EXIOBASE sectors:")
        print(dep_mat_unjoined.index.tolist())

    # Get the list of ecosystem services
    ecosystem_services = list(dep_mat.columns)
    ecosystem_services = [es for es in ecosystem_services if 'ISIC' not in es and es != 'EXIOBASE Sector']
    
    # Get unique exiobase sectors
    exiobase_sectors = dep_mat_joined['EXIOBASE'].dropna().unique()

    output_data = []

    for service in ecosystem_services:
        material_sectors_for_service = []
        for sector_name in exiobase_sectors:
            sector_df = dep_mat_joined[dep_mat_joined['EXIOBASE'] == sector_name]
            
            if service in sector_df:
                service_ratings = sector_df[service]
                counts = service_ratings.value_counts()
                vh_count = counts.get('VH', 0)
                h_count = counts.get('H', 0)

                # Apply materiality criteria for the sector
                is_material = (vh_count >= 1) or \
                              (len(service_ratings) > 0 and (vh_count + h_count) / len(service_ratings) > 0.5) or \
                              (vh_count + h_count >= 3)
                
                if is_material:
                    material_sectors_for_service.append(sector_name)
        
        if material_sectors_for_service:
            output_data.append({
                "service": service,
                "sectors": sorted(material_sectors_for_service)
            })

    # Save the results
    output_path = EXIOBASE_DIR / 'encore_materiality.json'
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=4)
    
    dep_mat_joined.to_csv(EXIOBASE_DIR / 'encore_materiality.csv')

    print(f"Materiality analysis complete. Results saved to {output_path}")