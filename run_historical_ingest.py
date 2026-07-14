import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from ingest_exiobase import ingest_and_save_exiobase, create_production_history, EXIOBASE_DIR

YEARS = list(range(2010, 2023))

def already_done(year):
    p = EXIOBASE_DIR / str(year) / 'EXIOBASE_A.parquet'
    return p.exists() and p.stat().st_size > 1_000_000  # >1MB rules out dummy/test data

for y in YEARS:
    if already_done(y):
        print(f"[{y}] already ingested, skipping", flush=True)
        continue
    print(f"[{y}] starting ingest", flush=True)
    try:
        ingest_and_save_exiobase(year=y, float32=True)
        print(f"[{y}] done", flush=True)
    except Exception as e:
        print(f"[{y}] FAILED: {e}", flush=True)

print("Rebuilding production_history.parquet across all years...", flush=True)
create_production_history()
print("ALL DONE", flush=True)
