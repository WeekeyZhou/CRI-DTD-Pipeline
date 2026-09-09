"""
config.py
--------------------------------------------------------------------
Shared configuration — all five stage files (ingestion/transform/validate/
output/run_daily_update) read their constants from here rather than
duplicating them.

This package is the "daily incremental update" production pipeline, and is a
separate thing from the earlier market_cap_full_series.py:
    - market_cap_full_series.py is a "one-off" historical validation script:
      it compares the two-year historical market-cap reconstruction
      methodology against CRI's original values day by day and computes the
      error — essentially a one-time methodology validation that, along the
      way, produced the first version of vanke_input_extended.xlsx. That
      script has already done its job and does not need to be re-run daily.
    - This package (dtd_pipeline/) is the actual "daily update pipeline"
      that Part 1 of the task asks for: each run processes only "the next
      trading day" — it reads the existing output table, computes that one
      day, appends a row, and writes it back. It never recomputes history
      and never re-validates the methodology.

SHARE_CHECKPOINTS / BS_CHECKPOINTS are two lists that "require manual
quarterly maintenance"; market_cap_full_series.py already has its own copy
of these. Keeping a separate copy here instead of importing across files is
deliberate — the two scripts run at different times and may be maintained
by different people (one is "run once during validation analysis", the
other is "a production script run daily / after every market close"), and
hard-coupling them would work against the "clear, easy to maintain" goal
that the task emphasizes more.
Known limitation: this means the two checkpoint lists have to be kept in
sync manually. If that becomes a hassle down the line, they could be
refactored into a shared checkpoints.py — not doing that now (avoiding
over-engineering).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

# ---------- File paths ----------
# Locate data/ under the repo root via __file__, rather than a bare filename
# relative to the current working directory — this way, no matter which
# directory you cd into in the terminal or how run_daily_update.py is
# invoked, it reliably finds the same data file, without relying on the
# fragile convention of "must be run from a specific directory".
# Directory assumption: <repo_root>/dtd_pipeline/config.py and
# <repo_root>/data/vanke*.xlsx.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
ORIGINAL_XLSX = DATA_DIR / "vanke.xlsx"               # Original historical data provided by CRI
EXTENDED_XLSX = DATA_DIR / "vanke_input_extended.xlsx"  # The table this pipeline reads/appends to/writes back
SHEET_NAME = "Input"

# ---------- Equity / FX data sources ----------
A_SHARE_TICKER = "000002.SZ"
H_SHARE_TICKER = "2202.HK"
FX_TICKER = "CNYHKD=X"
FX_FALLBACK_USD_HKD_TICKER = "HKD=X"   # USD -> HKD
FX_FALLBACK_USD_CNY_TICKER = "CNY=X"   # USD -> CNY

# ---------- HKMA interest-rate data source ----------
HKMA_EFBN_DAILY_URL = (
    "https://api.hkma.gov.hk/public/market-data-and-statistics/"
    "monthly-statistical-bulletin/efbn/efbn-yield-daily"
)
RATE_FIELD = "efb_364d"  # 12-month Exchange Fund Bill yield

# ---------- Fallback / retry parameters ----------
MAX_STALE_LOOKBACK_DAYS = 30   # Upper bound (in trading days) on how far back to search the existing output table for a fallback value
MAX_RETRIES_PER_REQUEST = 4
REQUEST_TIMEOUT_SECONDS = 15

# ---------- Share-count checkpoints (require manual quarterly maintenance against the financial statements) ----------
SHARE_CHECKPOINTS = [
    # (effective date, A-share count, H-share count, source)
    ("2023-12-31", 9_724_196_533, 2_206_512_938, "2023年年度报告"),
    ("2024-12-31", 9_724_196_533, 2_206_512_938, "2024年年度报告"),
    ("2025-12-31", 9_724_196_533, 2_206_512_938, "2025年年度报告"),
]

# ---------- Balance-sheet checkpoints (same as above, require manual quarterly maintenance) ----------
BS_CHECKPOINTS = [
    # (effective date, BS_CUR_LIAB, BS_LT_BORROW, BS_TOT_LIAB2, BS_TOT_ASSET, source)
    (
        "2025-12-12",
        655_360.632475,
        221_894.376752,
        913_130.657295,
        1_242_105.617464,
        "vanke.xlsx历史区间最后一天(具体对应哪一期财报未核实，需人工确认)",
    ),
]

BS_STALENESS_WARN_DAYS = 100  # Warn once the latest checkpoint is older than this many days, prompting a manual check

# ---------- Final table column order ----------
FINAL_COLUMNS = [
    "Comp_no",
    "Date",
    "CUR_MKT_CAP_ORI(HKD)",
    "CUR_MKT_CAP_CUL(HKD)",
    "BS_CUR_LIAB(HKD)",
    "BS_LT_BORROW(HKD)",
    "BS_TOT_LIAB2(HKD)",
    "BS_TOT_ASSET(HKD)",
    "Risk_Free_Rate",
    "Risk_Free_Rate_is_stale",
    "A_STOCK_SHARE",
    "A_STOCK_PRICE",
    "A_price_is_stale",
    "EXCHANGE_RATE",
    "H_STOCK_SHARE",
    "H_STOCK_PRICE",
    "H_price_is_stale",
    "DIFFERENCE",
    "DIFFERENCE_pct",
]

COMP_NO = 5338


def today() -> dt.date:
    """Wrapped separately so it's easy to monkeypatch in tests (e.g. pin it to a fixed date)."""
    return dt.date.today()
