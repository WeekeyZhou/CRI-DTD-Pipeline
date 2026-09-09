# Vanke DTD Pipeline — CRI Production-Oriented DTD Pipeline

A production-grade pipeline for China Vanke Co. (000002.SZ / 2202.HK) Distance-to-Default
(DTD) input data, built for the CRI internship task.

- **Part 1**: Extend the historical DTD input data provided by CRI (2023-12-12 ~
  2025-12-12, 493 trading days) by at least 5 new trading days, and build a
  staged (ingestion / transform / consistency checks / output) production
  pipeline that can run as a daily incremental update.
- **Part 2**: A case-study reflection cross-referencing the DTD trajectory against
  Vanke's real public credit-distress events over the same window — event
  identification, a six-phase read of where DTD anticipates, coincides with,
  lags, or is noisy/muted/counter-intuitive relative to reality, a
  methodological background section on how DTD itself is computed (drawing on
  three CRI Technical Report addenda), and a discussion of assumptions,
  limitations and how a signal like this should be used in practice. See
  `report/part2_case_study.md`.

## Directory structure

```
vanke-dtd-pipeline/
├── README.md                          # This file: project overview, how to run, directory guide
├── requirements.txt                   # Python dependencies
│
├── data/
│   ├── vanke.xlsx                     # Original data provided by the task (read-only, do not overwrite)
│   └── vanke_input_extended.xlsx      # Pipeline output: historical 493 rows + new trading days
│
├── scripts/
│   └── ingestion_full.py      # One-off methodology validation script (see notes below)
│
├── dtd_pipeline/                      # Daily incremental update pipeline (the production pipeline the task asks for)
│   ├── config.py                      # Shared config: ticker, HKMA endpoint, checkpoint list
│   ├── ingestion.py                   # Stage 1: data ingestion
│   ├── transform.py                   # Stage 2: transformation / computation
│   ├── validate.py                    # Stage 3: consistency checks
│   ├── output.py                      # Stage 4: output (append + persist)
│   ├── run_daily_update.py            # Orchestration entry point (CLI)
│   └── README.md                      # Detailed docs for this pipeline package
│
└── report/
    ├── part1_report.md                # Part 1 report: methodology, assumptions, limitations, trade-offs
    ├── part2_case_study.md            # Part 2: DTD vs. Vanke's real credit events
    └── dtd_vs_events_en.png           # Part 2 chart

```

## Division of labor between the two scripts

- **`scripts/ingestion_full.py`** is a **one-off methodology validation script**:
  using two years of historical data (2023-12-12 ~ 2025-12-31), it compares,
  day by day, "CRI's official market cap (`CUR_MKT_CAP_ORI`)" against "a
  market cap reconstructed from A-share price × share count × FX rate + H-share
  price × share count (`CUR_MKT_CAP_CUL`)" to validate the accuracy of the
  market-cap reconstruction method (median error ~0.03%), and in the same run
  computes the full 2023-12-12 ~ 2025-12-31 range (historical + new) and
  persists it to `data/vanke_input_extended.xlsx`. This script has already
  done its job — it **does not need to be re-run daily**.

- **`dtd_pipeline/`** is the "production-grade daily update pipeline" the task
  actually asks for: each run processes exactly **one** new trading day,
  reading the existing content of `data/vanke_input_extended.xlsx`, computing
  the new row, and appending it — it never recomputes or overwrites existing
  historical rows. In normal production use, run `python run_daily_update.py`
  once after each trading day's close. See `dtd_pipeline/README.md` for
  details.

## How to run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Run once only) validate the methodology on two years of historical data
#    and generate the initial vanke_input_extended.xlsx
cd scripts
python ingestion_full.py

# 3. Daily production use: run once after each trading day's close, processing
#    only the "next pending trading day"
cd ../dtd_pipeline
python run_daily_update.py

# You can also process several consecutive days at once, or target a specific
# date — see dtd_pipeline/README.md
```

## Data sources

| Data | Source |
|---|---|
| A-share price (000002.SZ) | yfinance |
| H-share price (2202.HK) | yfinance |
| CNY/HKD FX rate | yfinance |
| Risk-free rate (12-month Exchange Fund Bill yield) | Hong Kong Monetary Authority (HKMA) public API |
| Share count and the 4 balance-sheet columns | Vanke's periodic financial statements, maintained manually on a quarterly basis (see `dtd_pipeline/README.md`) |

## Reports

- `report/part1_report.md` — Part 1 methodology: market-cap reconstruction
  method, accuracy validation, pipeline architecture, assumptions and
  limitations, key trade-offs.
- `report/part2_case_study.md` (English) / `report/part2_case_study_zh.md`
  (Chinese) — Part 2 case study: a public event timeline for Vanke's
  2023–2025 credit distress, a six-phase read of the DTD series against that
  timeline (where it anticipates, coincides, lags, or is noisy/muted/
  counter-intuitive), a background section on how DTD itself is computed
  (based on three CRI Technical Report addenda covering the core DTD formula
  and the calibration of its σ and δ parameters), a documented hypothesis for
  why DTD diverged sharply from reality in Oct–Nov 2025, and a discussion of
  limitations and practical takeaways for using a signal like this in
  production.
