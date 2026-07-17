# src/data_bootstrap.py
"""
First-run reference-data downloader.

Context: the packaged executable (see `vesdio.spec`) no longer bundles the
EXIOBASE reference-year dataset — it used to, but a single ingested year
(with dense float64 L/G matrices) is well over a gigabyte, and GitHub's
per-asset limit plus the desire for small, fast-to-download per-OS
executables made bundling untenable. Instead, the data is fetched **once**,
on first run, from a GitHub Release, into a persistent per-user data
directory (see `src/paths.py: get_base_data_path()` — NOT `sys._MEIPASS`,
which is a read-only temp dir PyInstaller re-extracts on every launch).

This module is intentionally stdlib-only (`urllib.request`, `hashlib`,
`json`, `pathlib`) — no new heavy dependency is justified just to download a
handful of files once per install.

--------------------------------------------------------------------------
Manifest schema (`manifest.json`, itself a release asset)
--------------------------------------------------------------------------
GitHub release assets are a flat namespace (no folders), so the manifest
maps each flat asset name to the repo-relative path it should be written to
under the base data directory:

    {
        "year": 2021,
        "files": [
            {
                "asset": "EXIOBASE_2021_A.parquet",
                "path": "exiobase/2021/EXIOBASE_A.parquet",
                "sha256": "<hex digest>",
                "bytes": 12345678,
                "required": true
            },
            {
                "asset": "EXIOBASE_2021_G.parquet",
                "path": "exiobase/2021/EXIOBASE_G.parquet",
                "sha256": "<hex digest>",
                "bytes": 87654321,
                "required": false
            },
            ...
        ]
    }

- `asset`: the literal GitHub release asset filename, fetched from
  `DATA_RELEASE_BASE_URL + asset` (see `src/config.py`).
- `path`: where to write the file, relative to `get_base_data_path()`.
- `sha256` / `bytes`: used to verify the download; a mismatch is treated as
  a failed/corrupted download and retried (see `_download_one`).
- `required`: if `false` (e.g. the optional `G` Ghosh-inverse matrix,
  `production_history.parquet`, `encore_materiality.json`), a permanent
  failure to fetch/verify this file is logged and skipped rather than
  failing the whole bootstrap — the app's existing per-loader fallbacks
  (see `src/providers/exiobase.py`) already tolerate these being absent.
  Entries without a `required` key default to required=True.

`build_release_manifest()` in `ingest_exiobase.py` produces exactly this
file (plus the flatly-renamed assets) from an assembled offline bundle.
"""
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from src.config import DATA_RELEASE_BASE_URL, DATA_MANIFEST_NAME
from src.paths import get_base_data_path

# Matrices `src/providers/exiobase.py: _load_mrio_matrices` loads by default;
# used only as a cheap "is data for this year already present" pre-check so
# that a normal, already-provisioned run never touches the network.
_REQUIRED_MATRIX_STEMS = ('A', 'Y', 'E', 'X', 'L')

# Retry/backoff schedule (seconds) for transient network errors, per the
# plan: up to 4 retries with exponential backoff 2/4/8/16s.
_RETRY_BACKOFFS = (2, 4, 8, 16)

_CHUNK_SIZE = 1024 * 1024  # 1 MiB streamed reads


def _report(progress, value):
    """Best-effort progress callback invocation. `value` is either a
    human-readable status string or a float fraction in [0, 1]; callers
    (see `app.py`) decide how to render either. Never lets a broken/absent
    callback take down the download."""
    if progress is None:
        return
    try:
        progress(value)
    except Exception:
        pass


def _year_data_present(base_data_path: Path, year: int) -> bool:
    """True if all of the required per-year EXIOBASE files already exist
    locally, i.e. no download is needed at all. This keeps normal dev runs
    (and a second launch of the packaged app) from ever touching the
    network."""
    year_dir = base_data_path / 'exiobase' / str(year)
    if not (year_dir / 'labels.json').exists():
        return False
    return all(
        (year_dir / f'EXIOBASE_{stem}.parquet').exists()
        for stem in _REQUIRED_MATRIX_STEMS
    )


def _fetch_manifest(base_url: str, manifest_name: str) -> dict | None:
    """Downloads and parses `manifest.json` from the release base URL.
    Returns None (rather than raising) on any failure, so the caller can
    fall back to the synthetic dummy dataset instead of crashing the app."""
    url = base_url.rstrip('/') + '/' + manifest_name
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as e:
        print(f"[data_bootstrap] Failed to fetch manifest from {url}: {e}")
        return None


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(_CHUNK_SIZE), b''):
            h.update(chunk)
    return h.hexdigest()


def _download_one(base_url: str, entry: dict, base_data_path: Path, progress=None) -> bool:
    """Downloads a single manifest entry to its target path, verifying
    sha256 + byte size, with retry/backoff on network errors. Streams to a
    `.part` temp file and only renames it into place once fully verified,
    so a crash/interrupt mid-download never leaves a corrupt "real" file
    behind for the loaders in `src/providers/exiobase.py` to pick up.

    Returns True on success (or if the target already exists and verifies),
    False if all retries were exhausted.
    """
    asset = entry['asset']
    rel_path = entry['path']
    expected_sha256 = entry.get('sha256')
    expected_bytes = entry.get('bytes')

    target_path = base_data_path / rel_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Already present and verified? Skip re-downloading (e.g. a partial
    # bootstrap from a previous run that got some files but not others).
    if target_path.exists():
        if expected_sha256 is None or _sha256_of(target_path) == expected_sha256:
            _report(progress, f"{rel_path} already present; skipping.")
            return True
        _report(progress, f"{rel_path} exists but failed checksum verification; re-downloading.")

    url = base_url.rstrip('/') + '/' + asset
    part_path = target_path.with_suffix(target_path.suffix + '.part')

    attempts = len(_RETRY_BACKOFFS) + 1
    for attempt in range(1, attempts + 1):
        try:
            _report(progress, f"Downloading {asset} -> {rel_path} (attempt {attempt}/{attempts})...")
            with urllib.request.urlopen(url, timeout=60) as resp:
                with open(part_path, 'wb') as out:
                    while True:
                        chunk = resp.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        out.write(chunk)

            # Verify size first (cheap), then sha256 (expensive) before
            # committing the .part file to its real path.
            actual_bytes = part_path.stat().st_size
            if expected_bytes is not None and actual_bytes != expected_bytes:
                raise ValueError(
                    f"size mismatch for {asset}: expected {expected_bytes} bytes, got {actual_bytes}"
                )

            if expected_sha256 is not None:
                actual_sha256 = _sha256_of(part_path)
                if actual_sha256 != expected_sha256:
                    raise ValueError(
                        f"sha256 mismatch for {asset}: expected {expected_sha256}, got {actual_sha256}"
                    )

            # Atomic on POSIX and on Windows (os.replace semantics via Path.replace).
            part_path.replace(target_path)
            _report(progress, f"Verified and saved {rel_path}.")
            return True

        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError) as e:
            part_path.unlink(missing_ok=True)
            if attempt <= len(_RETRY_BACKOFFS):
                backoff = _RETRY_BACKOFFS[attempt - 1]
                _report(progress, f"Download of {asset} failed ({e}); retrying in {backoff}s...")
                time.sleep(backoff)
            else:
                _report(progress, f"Giving up on {asset} after {attempts} attempts: {e}")
                return False

    return False  # pragma: no cover - unreachable, loop always returns


def ensure_reference_data(year: int = 2021, progress=None) -> bool:
    """
    Ensures the reference year's EXIOBASE data is present in the persistent
    data directory (`get_base_data_path()`), downloading it from a GitHub
    Release if missing/incomplete.

    Args:
        year: The EXIOBASE reference year to provision (default 2021, the
            only year VESDIO currently ships a pre-processed release for).
        progress: Optional callback(value), called with either a short
            human-readable status string or a float fraction in [0, 1] as
            the download proceeds. See `app.py` for a console-printing
            implementation. Never required — if it raises, it's ignored.

    Returns:
        True if the year's required files are present and verified when
        this returns (whether because they were already there, or the
        download succeeded); False if the download failed and the caller
        should expect the synthetic dummy-data fallback
        (`src.providers.exiobase._generate_dummy_data`) to engage instead.
        A False return is not fatal to the app — it just means real data
        isn't available yet.
    """
    base_data_path = get_base_data_path()

    if _year_data_present(base_data_path, year):
        _report(progress, f"Reference data for {year} already present at {base_data_path}; skipping download.")
        return True

    base_data_path.mkdir(parents=True, exist_ok=True)

    _report(progress, f"Reference data for {year} not found; fetching manifest from {DATA_RELEASE_BASE_URL}...")
    manifest = _fetch_manifest(DATA_RELEASE_BASE_URL, DATA_MANIFEST_NAME)
    if manifest is None:
        _report(progress, "Could not fetch data manifest; will fall back to synthetic dummy data.")
        return False

    manifest_year = manifest.get('year')
    if manifest_year is not None and int(manifest_year) != int(year):
        _report(
            progress,
            f"Manifest is for year {manifest_year}, not requested year {year}; proceeding anyway "
            f"(files are addressed by their own 'path' entries).",
        )

    files = manifest.get('files', [])
    if not files:
        _report(progress, "Manifest has no files listed; will fall back to synthetic dummy data.")
        return False

    total = len(files)
    all_required_ok = True
    for i, entry in enumerate(files):
        _report(progress, i / total)
        ok = _download_one(DATA_RELEASE_BASE_URL, entry, base_data_path, progress=progress)
        if not ok and entry.get('required', True):
            all_required_ok = False
            _report(progress, f"Required file {entry.get('path', entry.get('asset'))} failed to download.")

    _report(progress, 1.0)

    # Re-check on-disk state rather than trusting the per-file bools alone —
    # this is the same predicate normal startup uses, so it's the actual
    # source of truth for "does the app have what it needs".
    success = all_required_ok and _year_data_present(base_data_path, year)
    if success:
        _report(progress, f"Reference data for {year} is ready at {base_data_path}.")
    else:
        _report(progress, f"Reference data for {year} could not be fully provisioned; dummy-data fallback will be used.")
    return success
