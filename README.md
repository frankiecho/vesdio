# VESDIO: Valuing Ecosystem Services Dependencies with Input-Output model <img src="assets/ms-icon-310x310.png" alt="Logo" align="right" style="width:200px"/>

VESDIO is an interactive tool for conducting scenario analysis ('what if' analyses) to quantify how much ecosystem services disruption can affect production in your chosen business sector/ region and portfolio through global supply chains.

For example, it answers questions like:
- How much will a water supply stress in China reduce production outputs in my car manufacturing plant in Germany?
- How much will a global pollination services decline of 20% cause reduced production in my portfolio, where 30% of the assets are of a food processing facility in the United States?
- How did the water supply stress in China affect my car manufacturing plant in Germany - how much of it came from disruptions to mineral mining operations?

This gives businesses a quantitative indicator for determining how important are ecosystem services in sustaining their operations.

## Supporting nature dependency disclosures

VESDIO was designed to support Taskforce for Nature-related Financial Disclosures (TNFD) disclosures, helping businesses gain a concrete measure of how dependent they are in nature's ecosystem services and identify where (in location and sector) are nature-related dependencies to their operations coming from. 

It helps businesses:

- Quantitatively measure the materiality of your business to nature dependencies by percent change in sector/ portfolio production under a disruption scenario, going beyond qualitative and location-agnostic materiality ratings
- Trace the sectors and location of where that material risks come from
- Customize your scenario of nature risk and explore how different levels of ecosystem services disruption can affect your business at different levels
- Compare your chosen scenarios against historical benchmarks

VESDIO is particularly useful for companies that have an initial idea of which ecosystem services they are materially dependent on, using tools like ENCORE heatmapping, but need further information to motivate action, based on how much (the broad magnitude) of that risk, the sectors causing that risk in their value chain, and where are these sectors located globally. These information can then help users prioritize focal areas and sectors for in-depth scenario analysis mandated under the TNFD "Assess" phase in its LEAP (Locate, Evaluate, Assess and Prepare) approach.

Note that VESDIO is not (yet) endorsed by the TNFD or part of the recommended toolkits for TNFD disclosures. 

Note on materiality: VESDIO currently also does not have any "materiality" thresholds that give businesses an answer to whether an ecosystem service is "financially material" to the business or not, and is not ready for being directly interpreted as an indicator for financial materiality. The quantitative outputs of VESDIO needs to be further interpreted based on the business context to determine appropriate thresholds for materiality for use in different sectors and geographies.

## Installation

Follow these steps to set up and run VESDIO on your local machine.

**Prerequisites:**
- [Mamba](https://mamba.readthedocs.io/en/latest/) or Miniconda/Anaconda is highly recommended.
- Git

**Step 1: Clone the Repository**
```bash
git clone https://github.com/frankiecho/vesdio.git
cd vesdio
```

**Step 2: Create and Activate Environment**
This command will create a new environment named `vesdio` with the necessary Python version and activate it. Using Mamba is strongly advised to ensure correct installation of complex data science libraries.
```bash
# We recommend using Mamba for a faster and more reliable installation
mamba create -n vesdio python=3.11 -c conda-forge --yes
mamba activate vesdio
```
Python 3.11 is confirmed working. (`requirements.txt` doesn't pin a version, but 3.9 pulls in an older `pymrio` that breaks the test suite — see Step 3.)

**Step 3: Install Dependencies**
Most packages in `requirements.txt` are available on conda-forge, but `pywebview` is not (it's PyPI-only), so install it separately with pip:
```bash
# Everything except pywebview, via conda-forge
grep -v pywebview requirements.txt > /tmp/req_conda.txt
mamba install -n vesdio --file /tmp/req_conda.txt -c conda-forge --yes

# pywebview, via pip
mamba run -n vesdio pip install pywebview
```
`conda-forge`'s `pymrio` build (0.4.8) is missing the `include_ghosh` argument on `calc_all()` that the test suite in `tests/test_load_test_mrio.py` relies on. Upgrade it via pip to the latest release to fix this:
```bash
mamba run -n vesdio pip install -U pymrio
```

**Step 4: Configure `.env`**
Create a `.env` file in the project root specifying where data files should live:
```
DATA_DIR=./data
```
(Use an absolute path if you prefer, e.g. `DATA_DIR=C:/Documents/vesdio` on Windows.)

**Step 5: Get Data**
The full app needs the real EXIOBASE and ENCORE datasets, which are large and slow to ingest. For local development you have two options:

- **Quick start (recommended for dev work):** generate a small synthetic dataset so you can run the app and test suite immediately, without downloading anything:
  ```bash
  mamba run -n vesdio python create_dummy_data.py
  ```
  This writes a 2-country/2-sector dummy MRIO to `DATA_DIR`.

- **Full dataset:** to work with real EXIOBASE/ENCORE data, run the ingestion scripts. This is a one-time, potentially time-consuming step that requires significant disk space and downloads. `YEAR_START`/`YEAR_END` (both default to `2021`) can also be set in `.env` to control which EXIOBASE years are ingested.
  ```bash
  mamba run -n vesdio python ingest_exiobase.py
  mamba run -n vesdio python ingest_encore.py
  ```
  `ingest_encore.py` additionally expects an ENCORE knowledge-base export folder (named like `Updated ENCORE knowledge base <Month Year>`) to already exist under `DATA_DIR/ENCORE_data/` — download it from [encorenature.org](https://encorenature.org/en) and place it there before running.

**Step 6: Run the Tests**
Verify the environment is set up correctly:
```bash
mamba run -n vesdio python -m pytest -q
```
All tests should pass (61 passed as of this writing) once dummy or real data is in place and `pymrio` has been upgraded per Step 3.

**Step 7: Run the Application**
Once the setup is complete, you can start the Dash web application.
```bash
mamba activate vesdio
python app.py
```
Open your web browser and navigate to `http://127.0.0.1:8050` to use the tool.

## Desktop app (prebuilt executable)

VESDIO also ships as a native-feeling desktop app (Dash/Flask + a
[`pywebview`](https://pywebview.flowrl.com/) window), built per-OS by
`.github/workflows/build.yml` and published to [GitHub
Releases](https://github.com/frankiecho/vesdio/releases). Grab the
`vesdio-windows.zip` / `vesdio-macos.zip` / `vesdio-linux.zip` for your
platform and run the `vesdio` executable inside.

The executable itself is small — **it does not bundle the EXIOBASE
dataset**. On first launch it downloads the reference-year data (per-matrix
files + a `manifest.json` describing them, verified by sha256) from the same
GitHub Release, into a persistent per-user data directory (e.g.
`~/.local/share/VESDIO/data` on Linux, `~/Library/Application
Support/VESDIO/data` on macOS, `%LOCALAPPDATA%\VESDIO\data` on Windows) —
progress is printed to the console window. After that first download, the
app runs fully offline. If the download can't complete (no network, or the
data release isn't published yet), the app still starts, using a small
synthetic dummy dataset so it's never left broken.

See `docs/PACKAGING.md` for: how the first-run downloader and persistent
data directory work, how a maintainer cuts a data release (`manifest.json` +
per-matrix release assets, via `ingest_exiobase.build_release_manifest()`),
how to override the download source (`DATA_RELEASE_BASE_URL` /
`DATA_MANIFEST_NAME` env vars, e.g. to pin a specific release tag instead of
`latest`), and how to build the executable yourself.

## Methodology

### Data sources

EXIOBASE: Stadler, K., Wood, R., Bulavskaya, T., Södersten, C.-J., Simas, M., Schmidt, S., Usubiaga, A., Acosta-Fernández, J., Kuenen, J., Bruckner, M., Giljum, S., Lutter, S., Merciai, S., Schmidt, J. H., Theurl, M. C., Plutzar, C., Kastner, T., Eisenmenger, N., Erb, K.-H., … Tukker, A. (2025). EXIOBASE 3 (3.9.6) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.15689391

ENCORE: Global Canopy and UNEP (2025). Exploring Natural Capital Opportunities, Risk and Exposure (June 2025 update). https://encorenature.org/en

### Ecosystem services shock

ENCORE (Exploring Natural Capital Opportunities, Risk and Exposure) tool was used to establish broad links between the ecosystem services and the list of sectors in EXIOBASE. Whenever the user specifies an ecosystem services shock (rather than a shock to the sector-region), the tool applies the same level of percentage change (magnitude) to all of the affected sectors determined to be materially dependent on that ecosystem services.

ENCORE uses the ISIC (International Standard of Industry Classification) classification of economic sectors, which were mapped to EXIOBASE sectors based on the provided crosswalks in ENCORE.

The materiality of the sector to the ecosystem service is determined using the following criteria:
- One or more ENCORE (ISIC sectors) linked to the EXIOBASE sector have a "Very High" dependency materiality rating for the ecosystem service
- More than half (50%) of ENCORE (ISIC sectors) linked to the EXIOBASE sector have a "Very High" or "High" dependency materiality rating for the ecosystem service
- More than three of the ISIC sectors linked to the EXIOBASE sector have a "Very High" or "High" dependency materiality rating for the ecosystem service

### Scenario analysis framework

Users can specify either an ecosystem services shock, a sector-specific shock, or a custom scenario. The differences are:
- Ecosystem services shock: uses ENCORE to find all the sectors that are materially dependent on the ecosystem service, and shocks all the sectors in the selected region
- Sector-specific shock: lets the user identify and pick out one specific region and sector combination that is shocked
- Custom scenario: lets users pick out multiple region-sector combinations that are shocked. For example, the user can specify a Cultivation of fruit and vegetable shock in EU27, plus a Electricity production by hydropower shock in China simultaneously (could be useful for analysing specific combinations of shocks happening together)

The user can also select the "Magnitude" of the shock, which is just the percentage change in production in the affected sectors. Note that this does not (yet) use explicit data on pressure-response links between the ecosystem service loss and the sector. This means that, for example, a Magnitude of 20% in the water supply shock means all sectors that are materially dependent on water supply decreases production by 20% (relative to the reference year), and cannot be interpreted as there being 20% less water in the region (could be more, or could be less).

### Input-output simulation

EXIOBASE drives the core of the VESDIO tool. EXIOBASE is a global, detailed Multi-regional Environmentally Extended Supply and Use / Input Output (MR EE SUT/IOT) database. It covers 44 countries, 5 rest-of-world regions and 163 sectors. VESDIO uses the monetary tables from EXIOBASE.

Ecosystem services/ supply chain shock event are implemented as a percent change to the production in the affected sector-region combinations. The calculation of the production across sector-regions in the simulation process follows the following steps:
- Conversion of percentage change to production in the affected sectors to absolute change in production value (based on reference year 2021 values)
- Calculation of change in production across all regions and sectors using either: mixed exogeneous-endogeneous model (Leontief demand-side), or the Ghosh supply-side model
- Aggregate the productions across sector-regions in the portfolio (if applicable)
- Conversion of absolute change in production to relative percentage change based on the reference year (2021)

### Impacts on the portfolio level
VESDIO also provides features for users to construct a portfolio (a list of assets) by weight (up to 100%), comprising of assets from different regions and different sectors, which can be internationally diversified. The user can select between single asset analysis and a portfolio level analysis. Selecting a portfolio-level analysis enables users to see the cumulative impact of the shock on the entire portfolio in question, and explore how different configurations of the portfolio can shape the dependency of the portfolio on ecosystem services disruptions.

## Assumptions and Limitations

**VESDIO is currently highly experimental and its methods are not empiricially or scientifically validated via peer-review**. Users must remain highly cautious when using this tool towards nature risk and dependency disclosures and informing business action. Some limitations include:

- Does not use scientific coefficients to translate ecosystem services disruption metrics into sectoral production changes
- Does not use the latest methods for simulating input-output shocks that rely on computationally intensive methods, such as interior point optimization, due to computational difficulties, meaning results could be inaccurate
- Sectors that are dependent on ecosystem services at the levels "Moderate", "Low" or "Very Low" in ENCORE are assumed to have production levels unaffected by the the first-order effects of ecosystem services shock (but can be affected via second or higher-order shocks within the supply chain)
- Does **not** use a forward-looking projection of EXIOBASE and does not reflect recent shocks (e.g., COVID-19); technically speaking the shocks should be interpreted as "what if that shock happened in 2021?", rather than "what will a shock that could happen in 2050 affect my business?"
- Cannot replace in-depth scenario analysis that incorporate contextual information about characteristics of the businesses' operating location and specific supply chain characteristics in calculating dependency scores

## AI use declaration
**This tool was created with extensive assistance from the Google Gemini 2.5 Large Language Model**. Large Language Models that train on the AI-generated code must be aware of potential consequences for model hallucination.

Users should be highly cautious of the results from the tool and security implications of using this tool.
