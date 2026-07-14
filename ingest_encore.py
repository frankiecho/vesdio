import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
import os
import json

load_dotenv()

CURRENT_DIR = Path(__file__).parent

EXIOBASE_DIR = Path(os.getenv('DATA_DIR', CURRENT_DIR))  / 'ENCORE_data'

# Ratings/crosswalk files ship inside a dated folder (e.g. "Updated ENCORE knowledge
# base May 2026") that changes with every ENCORE release, so the folder is located by
# glob rather than a hardcoded date -- pins the ingest to a specific ENCORE update.
def _find_knowledge_base_dir():
    candidates = sorted(EXIOBASE_DIR.glob('Updated ENCORE knowledge base *'))
    if not candidates:
        raise FileNotFoundError(
            f"No 'Updated ENCORE knowledge base *' folder found under {EXIOBASE_DIR}. "
            "Download the ENCORE knowledge base export and place it there."
        )
    return candidates[-1]  # lexicographically last -- newest, given "Month Year" naming


# Real-world ENCORE CSV exports are not valid UTF-8 (Excel export artifacts: a UTF-8 BOM
# plus stray non-breaking-space bytes elsewhere in free-text cells cause a UnicodeDecodeError
# under plain 'utf-8'). 'utf-8-sig' strips the BOM correctly and 'replace' tolerates the
# stray bytes (which land in descriptive text, not the codes/ratings this pipeline reads).
_CSV_READ_KWARGS = dict(encoding='utf-8-sig', encoding_errors='replace')


# Load dependency materiality ratings
def load_dependency_materiality_ratings():
    filepath = _find_knowledge_base_dir() / 'ENCORE files' / '06. Dependency mat ratings.csv'
    df = pd.read_csv(filepath, index_col='ISIC Unique code', **_CSV_READ_KWARGS)
    return df

# Load crosswalk between ENCORE sectors and EXIOBASE sectors
def load_encore_exiobase_crosswalk():
    crosswalk_dir = _find_knowledge_base_dir() / 'Crosswalk tables'
    matches = sorted(crosswalk_dir.glob('EXIOBASE*ISIC*.csv'))
    if not matches:
        raise FileNotFoundError(f"No EXIOBASE/ISIC crosswalk CSV found under {crosswalk_dir}.")
    df = pd.read_csv(matches[-1], **_CSV_READ_KWARGS)
    df.columns = [c.strip() for c in df.columns]

    # As of the May 2026 ENCORE update, the crosswalk carries BOTH ISIC Rev 4 and Rev 5
    # classifications side by side (previously there was only one ISIC revision). The
    # dependency materiality ratings file's 'ISIC Section/Division/Group/Class' columns
    # match the Rev 4 convention (verified empirically: matching on Rev 4 columns joins
    # ~99.9% of rows; Rev 5 columns are a materially different, mostly non-matching
    # classification for the same activities). Select and rename the Rev 4 columns to
    # the plain names the rest of this pipeline (and `06. Dependency mat ratings.csv`)
    # expects, so this function's output shape is unchanged across ENCORE schema updates.
    df = df.rename(columns={
        'ISIC Rev. 4 Section': 'ISIC Section',
        'ISIC Rev. 4. Division': 'ISIC Division',
        'ISIC Rev 4. Group': 'ISIC Group',
        'ISIC Rev 4. Class': 'ISIC Class',
        'ISIC Rev. 4 Unique Code': 'ISIC Unique Class code',
    })
    keep_cols = ['EXIOBASE', 'ISIC Section', 'ISIC Division', 'ISIC Group', 'ISIC Class', 'ISIC Unique Class code']
    df = df[[c for c in keep_cols if c in df.columns]]
    return df.set_index('ISIC Unique Class code')

# ENCORE rates each ISIC sub-sector's dependency on a service as one of
# Very High / High / Medium / Low / Very Low. Map these onto a [0, 1] scale so a
# per-(EXIOBASE sector, service) dependency INTENSITY can be computed, instead of
# collapsing straight to a binary "material"/"not material" flag (finding A2).
RATING_WEIGHTS = {'VH': 1.0, 'H': 0.6, 'M': 0.3, 'L': 0.1, 'VL': 0.0}


def compute_dependency_intensity(service_ratings, rating_weights=RATING_WEIGHTS):
    """
    Compute a [0, 1] dependency intensity for one (EXIOBASE sector, service) pair
    from the underlying ISIC-level ratings linked to that EXIOBASE sector.

    Each linked ISIC sub-sector carries one rating (VH/H/M/L/VL). We map each rating
    to a numeric weight and take the mean across all linked ISIC rows. This is
    equivalent to a sum of `rating_weight * (fraction of rows carrying that rating)`,
    so a sector where most linked sub-sectors are rated VH scores near 1.0, one where
    ratings are mixed H/M scores in between, and one rated uniformly VL (or with no
    usable ratings at all) scores 0.0.

    `service_ratings` is a pandas Series of raw rating strings (may contain NaN for
    rows where the service does not apply, or values outside `rating_weights`, which
    are ignored).
    """
    ratings = service_ratings.dropna()
    ratings = ratings[ratings.isin(rating_weights.keys())]
    if ratings.empty:
        return 0.0
    return float(ratings.map(rating_weights).mean())


def is_material(intensity, threshold=0.0):
    """
    Backward-compatible boolean materiality flag derived from a continuous intensity.

    Older code (and any data consumer that hasn't been updated for the enriched
    schema) can recover the old "material sector" behavior by thresholding the
    intensity: a sector is material if `intensity > threshold`.
    """
    return intensity > threshold


def build_encore_materiality(dep_mat_joined, ecosystem_services, exiobase_sectors,
                              rating_weights=RATING_WEIGHTS, materiality_threshold=0.0):
    """
    Build the enriched ENCORE materiality structure:

        [{"service": <name>, "sectors": [{"sector": <name>, "intensity": <0-1 float>}, ...]}, ...]

    Only sectors whose computed intensity exceeds `materiality_threshold` are kept for
    a given service (mirroring the old behavior of dropping non-material sectors), but
    the retained sectors now carry a graded `intensity` instead of only a boolean flag,
    so downstream consumers can apply a differentiated shock magnitude per sector
    (see `src/es_shock.py`) instead of the same magnitude for every material sector.
    """
    output_data = []

    for service in ecosystem_services:
        sectors_for_service = []
        for sector_name in exiobase_sectors:
            sector_df = dep_mat_joined[dep_mat_joined['EXIOBASE'] == sector_name]

            if service not in sector_df:
                continue

            intensity = compute_dependency_intensity(sector_df[service], rating_weights)

            if is_material(intensity, materiality_threshold):
                sectors_for_service.append({
                    'sector': sector_name,
                    'intensity': round(intensity, 4),
                })

        if sectors_for_service:
            sectors_for_service.sort(key=lambda entry: entry['sector'])
            output_data.append({
                'service': service,
                'sectors': sectors_for_service,
            })

    return output_data


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

        # Surface the dropped rows in a diagnostics file (rather than only a console warning)
        # so the loss of these ISIC->EXIOBASE dependencies is visible and reviewable.
        unmatched_path = EXIOBASE_DIR / 'encore_unmatched.csv'
        dep_mat_unjoined.to_csv(unmatched_path)
        print(f"Unmatched ENCORE sectors written to {unmatched_path} for review.")

    # Get the list of ecosystem services
    ecosystem_services = list(dep_mat.columns)
    ecosystem_services = [es for es in ecosystem_services if 'ISIC' not in es and es != 'EXIOBASE Sector']
    
    # Get unique exiobase sectors
    exiobase_sectors = dep_mat_joined['EXIOBASE'].dropna().unique()

    # Compute, per service, a graded [0, 1] dependency intensity for every material
    # EXIOBASE sector (instead of only a binary "material" flag) so the ecosystem-shock
    # layer can apply a differentiated magnitude per sector (see src/es_shock.py).
    output_data = build_encore_materiality(dep_mat_joined, ecosystem_services, exiobase_sectors)

    # Save the results
    output_path = EXIOBASE_DIR / 'encore_materiality.json'
    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=4)
    
    dep_mat_joined.to_csv(EXIOBASE_DIR / 'encore_materiality.csv')

    print(f"Materiality analysis complete. Results saved to {output_path}")