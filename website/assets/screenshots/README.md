# Screenshots

The PNGs in this directory are **placeholders captured against the synthetic
2-country / 2-sector dummy dataset** (`create_dummy_data.py`), not real
EXIOBASE/ENCORE data. They exist so the landing page has something honest and
functional to show before the maintainer has run a full ingest.

| File | Tab | Notes |
| --- | --- | --- |
| `summary.png` | Summary | Bar chart + waterfall render correctly. |
| `geographic.png` | Geographic Impact | The choropleth needs real ISO3 region codes; the dummy `C1`/`C2` codes don't map to any country, so this tab renders blank. Replace once captured against real data. |
| `supply-chain.png` | Supply Chain Flow | Sankey diagram renders correctly, just with only 4 dummy sector-region nodes. |
| `global.png` | Global Impacts | Ranked-sector table renders correctly. |
| `historical.png` | Historical Context | Dummy data has no production history, so this shows the "not available" empty state (expected, not a bug). |
| `portfolio.png` | Portfolio Breakdown | Two-asset dummy portfolio (60% C1-S1 / 40% C2-S2), renders correctly. |
| `scenario-builder.png` | Scenario Builder modal | Renders correctly. |

## How to regenerate with real data

1. Ingest real data (`python ingest_exiobase.py && python ingest_encore.py`)
   or point `DATA_DIR` at an existing processed data folder.
2. Start the app: `python app.py` (it will fall back to serving at
   `http://127.0.0.1:8050` if `pywebview` isn't available).
3. Drive it with Playwright/Chromium at a 1440px-wide viewport, run one or
   two representative scenarios, and screenshot each result tab plus the
   Scenario Builder modal. Save over the files in this directory using the
   same names so `website/index.html` doesn't need to change.
4. Keep each PNG under ~400 KB (resize/compress if needed) so the page loads
   fast on GitHub Pages.
