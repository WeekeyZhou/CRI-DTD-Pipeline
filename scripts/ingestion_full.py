"""
market_cap_full_series.py
--------------------------------------------------------------------
Task 1 (Part 1) — Vanke full-range CUR_MKT_CAP(HKD) computation +
                   Risk_Free_Rate supplementation + new trading-day fetch

    This version adds the Risk_Free_Rate supplementation logic (extending
    directly on top of the market-cap line, not as a separate file). What's
    different from market cap:
        - The Risk_Free_Rate for the historical window (2023-12-12 ~
          2025-12-12) is not re-fetched and not given an ORI/CUL comparison
          validation — the code already did this (orig["Risk_Free_Rate"]),
          unchanged in this version.
        - Only the previously hard-coded None for the new window
          (2025-12-13 ~ 2025-12-31) is replaced in this version with a real
          rate fetched live from the HKMA API.
    See the [Risk_Free_Rate Supplementation] section below for details.

    This version also fills in the 4 balance-sheet columns (BS_CUR_LIAB /
    BS_LT_BORROW / BS_TOT_LIAB2 / BS_TOT_ASSET): the new window carries
    forward the values from the historical window's last day (2025-12-12)
    unchanged — no fetching, no fallback needed — since the task explicitly
    assumes no new financial statements are released within this window,
    these four figures are constants across the entire new window. See the
    [Balance-Sheet Carry-Forward] section below for details.

[Output Table Structure]
    Leads with Comp_no, Date, followed by:

        CUR_MKT_CAP_ORI(HKD), CUR_MKT_CAP_CUL(HKD),
        BS_CUR_LIAB(HKD), BS_LT_BORROW(HKD), BS_TOT_LIAB2(HKD), BS_TOT_ASSET(HKD),
        Risk_Free_Rate, Risk_Free_Rate_is_stale,
        A_STOCK_SHARE, A_STOCK_PRICE, A_price_is_stale,
        EXCHANGE_RATE,
        H_STOCK_SHARE, H_STOCK_PRICE, H_price_is_stale,
        DIFFERENCE, DIFFERENCE_pct

    The output file is vanke_input_extended.xlsx, a single sheet named
    "Input" (matching the original vanke.xlsx sheet name, for easy future
    comparison).

    CUR_MKT_CAP_ORI(HKD) and CUR_MKT_CAP_CUL(HKD) are two separate columns
    (no longer doing double duty as one column like in earlier versions):
        - ORI = the original real value from vanke.xlsx. Only present for
          the historical window (2023-12-12 ~ 2025-12-12, the existing 493
          rows) — the new window has no "official real value," so this
          column is NaN there.
        - CUL = the market cap we compute ourselves from A-share price +
          H-share price + FX rate + share count. Computed for both the
          historical window and the new window — both have values.
        - DIFFERENCE = CUR_MKT_CAP_CUL(HKD) - CUR_MKT_CAP_ORI(HKD),
          DIFFERENCE_pct = DIFFERENCE / CUR_MKT_CAP_ORI(HKD) x 100.
          Since ORI is already NaN in the new window, these two columns
          automatically become NaN there too (NaN propagates through
          subtraction/division), so no extra branching is needed.

    Historical window (2023-12-12 ~ 2025-12-12):
        BS_*, Risk_Free_Rate are taken directly from vanke.xlsx's original
        data, with no modification whatsoever.

    New window (2025-12-13 ~ 2025-12-31, dates not present in vanke.xlsx):
        Comp_no is fixed at 5338; the 4 BS_* columns carry forward the
        2025-12-12 (the historical window's last day) values unchanged;
        Risk_Free_Rate is fetched as a real value from the HKMA API.

[Validated Methodology]
    CUR_MKT_CAP(HKD) (computed) = A-share closing price (CNY) x A-share
                                   count x CNY/HKD FX rate
                                 + H-share closing price (HKD) x H-share
                                   count
    Validated against real data — the error on two historical days is
    within 0.1%, judged to be a reasonable error, with no need to add an
    extra "floating B-shares" term — Vanke's B-shares were fully converted
    to H-shares via a "B-to-H" conversion in 2014, and no independent
    B-shares remain outstanding today.

[Why "Fetch the Whole Range in One Go" Rather Than "One Request Per Day"]
    Calling yfinance separately for each day would mean over a thousand
    network requests for 2+ years of data — slow and prone to rate-
    limiting. Here, only one "whole range" request is made per ticker, the
    result stored as a pandas Series; all subsequent "look up a day's
    value / forward-fill" operations are pure local pandas operations that
    trigger no further network requests.

[Share Count]
    9,724,196,533 A-shares and 2,206,512,938 H-shares, cross-checked
    against four official periodic reports (Vanke's 2023 annual report
    through the 2025 Q3 report), confirmed constant over this computation
    window (through 2025-12-31). The 2025 annual report won't be released
    until 2026, so this is an assumption that needs to be written into the
    report: it assumes the share count won't suddenly change before the
    2025 annual report is released.

[Handling Trading Halts / Missing Data]
    When a given market has no price data on a given day, look backward
    for the most recent valid trading day's price as a substitute, and
    explicitly flag it with is_stale to keep it traceable — never handled
    silently.

[Trading-Day Calendar — An Explicitly Discussed, Deliberate Trade-off]
    Checking the original vanke.xlsx: 12/25, 12/26, and 1/1 of the
    following year, for both 2023 and 2024, are entirely absent from the
    493 historical rows — even though A-shares (Shenzhen) traded normally
    on these days, CRI's original dataset has no corresponding row. In
    other words, CRI's historical definition of "trading day" actually
    follows the Hong Kong Exchange (HKEX) calendar, not "a day counts as a
    trading day if any one market is open."

    Copying this historical CRI convention (skip the whole row when
    H-shares are closed) was considered, but after discussion this was
    rejected: on 12/25 and 12/26, Shenzhen is clearly open for normal
    trading — dropping the entire row (along with the A-share's genuine
    price movement that day) just because the Hong Kong market is closed
    would effectively let the H-share holiday "drag down" the A-share as
    well, discarding real information that actually exists. So the rule
    for the new window was changed to: as long as one market is open that
    day with a real price, that day is kept as a row — if A-shares have a
    new price that day, use it; if H-shares don't (Hong Kong market
    closed), carry forward the last closing price and flag it as
    is_stale, and vice versa.

    The cost of handling it this way: the new window will include rows for
    12/25 and 12/26, dates that never had corresponding rows in CRI's
    historical data (2023, 2024) — meaning the new window's and the
    historical window's definitions of "trading day" are not fully
    consistent. This is an explicit departure that needs to be written
    into the report, not an oversight.

[Known Limitations]
    The judgment "no new H-share price that day = Hong Kong market
    closed" does not rule out the possibility of "the broad market is
    open but Vanke's H-share specifically is suspended" — no such case was
    observed within the sample window, so for now it's treated as a
    market-wide closure.

[Risk_Free_Rate Supplementation]
    Same data source as previously validated: the HKMA official API's
    efb_364d field (the 12-month Exchange Fund Bill rate) —
    https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/efbn/efbn-yield-daily

    Only fetches the small span of dates needed for the new window
    (EXTENSION_START ~ RANGE_END), unlike market cap which fetches the
    full 2-year historical range — the historical window's Risk_Free_Rate
    is already in vanke.xlsx and doesn't need to be re-fetched or given a
    comparison validation.

    Pagination approach: rather than starting from offset=0 and paging
    backward one page at a time — tested in practice, and since `end`
    (2025-12-31) is more than half a year from "today," paging from 0 to
    there could take a dozen-plus pages, and any single request timing out
    along the way would cause the whole function to give up outright
    (this is exactly what happened the first time it was tested). Changed
    to use estimate_start_offset to estimate a starting offset close to
    `end` based on the date gap, compressing the total number of requests
    down to one or two; retry (with backoff) was also added to each
    request, so a single timeout no longer causes the entire range to be
    abandoned.

    This rate is itself a market-derived figure backed out from actual EFB
    trading/quotes in the HKD money market, and isn't available every day:
    it follows the same HKEX/Hong Kong money-market holiday calendar as
    H-share prices (e.g. HKMA's data has no record at all for 12/25,
    12/26). So it's handled exactly the same way as H_STOCK_PRICE: reusing
    lookup_with_fallback, carrying forward the most recent valid value when
    there's no quote for the day, and explicitly flagging it via
    Risk_Free_Rate_is_stale — never handled silently.

    Risk_Free_Rate_is_stale is uniformly set to False for the historical
    window — these are original real values from vanke.xlsx, not something
    we supplemented ourselves, so there's no "borrowing a prior value"
    concern.

    Accuracy already validated against real data: over the 7 historical
    trading days 2025-12-04 ~ 2025-12-12, the efb_364d fetched from HKMA
    matches vanke.xlsx's original Risk_Free_Rate exactly day by day
    (2.55/2.55/2.48/2.50/2.53/2.50/2.46, no difference even to one decimal
    place).

[Balance-Sheet Carry-Forward — Checkpoint Pattern, Requires Manual
 Quarterly Maintenance]
    The task explicitly states: assuming no new financial statements are
    released within this window (2025-12-13 ~ 2025-12-31), the four
    figures BS_CUR_LIAB / BS_LT_BORROW / BS_TOT_LIAB2 / BS_TOT_ASSET should
    be carried forward unchanged. But "unchanged within this specific
    window" doesn't mean "never needs attention again" — Vanke will
    continue to release new quarterly/annual reports going forward, so
    this version doesn't hard-code "carry forward 2025-12-12"; instead it
    copies the same pattern as SHARE_CHECKPOINTS (share count), built as
    BS_CHECKPOINTS + get_balance_sheet_snapshot():
        - BS_CHECKPOINTS is a manually maintained list, where each record
          is (effective date, the 4 balance-sheet figures, source);
        - get_balance_sheet_snapshot(date) finds the most recent record
          with "effective date <= date," logic identical to
          get_shares_outstanding();
        - The list currently has only one entry (2025-12-12, taken from
          the historical window's last day in vanke.xlsx), which is enough
          to cover through 2025-12-31 for this task;
        - !!! Every time Vanke releases a new financial statement, someone
          needs to verify the latest balance-sheet figures and manually
          add a new record to the end of BS_CHECKPOINTS !!! — the code
          will not go fetch a new statement on its own; it will simply,
          faithfully use whichever record has the most recent "effective
          date" not later than the current date. Using a stale value is a
          "nobody updated it" problem, not a code-logic problem.
        - Added check_bs_checkpoint_freshness(): if the latest checkpoint
          is more than BS_STALENESS_WARN_DAYS (default 100 days) old
          relative to when the script actually runs, it prints a warning
          reminding someone to check whether a new financial statement has
          been missed — a purely "warn if it's been too long since the
          last update" heuristic; the code itself has no idea when Vanke
          will release a new statement.

    No corresponding is_stale flag was added: these four figures were
    already "unchanged between two statement releases" in the original
    vanke.xlsx (checking roughly the past 200 historical trading days,
    these four columns changed only 5 times, each corresponding to a
    statement update) — the checkpoint pattern is simply extending this
    existing pattern forward and adding a manual-maintenance reminder, not
    a "borrowing" behavior we invented ourselves, so it follows the same
    "no is_stale column" treatment as the historical window.

    Known limitation: if Vanke suddenly releases a supplementary
    announcement between two checkpoints that adjusts the balance sheet
    (e.g. a temporary share placement, a debt-restructuring supplement),
    this checkpoint mechanism — which updates on "statement release date"
    — cannot capture this kind of "irregular, off-quarterly-cadence"
    change. The task states that "no new financial statements are
    released" is an explicitly permitted assumption, so this limitation is
    outside the scope of what this version handles, but it's worth writing
    into the report's limitations section.
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

# ---------- Config ----------
# Same treatment as dtd_pipeline/config.py: use __file__ to locate the
# data/ directory under the repo root, rather than a bare filename relative
# to the current working directory, so this script reliably finds the data
# files regardless of which directory it's invoked from. Directory
# assumption: <repo_root>/scripts/market_cap_full_series.py and
# <repo_root>/data/vanke*.xlsx.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
INPUT_XLSX = DATA_DIR / "vanke.xlsx"
OUTPUT_XLSX = DATA_DIR / "vanke_input_extended.xlsx"
RANGE_START = dt.date(2023, 12, 12)
RANGE_END = dt.date(2025, 12, 31)
EXTENSION_START = dt.date(2025, 12, 13)  # first day after the historical dataset (through 2025-12-12)

MAX_STALE_LOOKBACK_DAYS = 30  # fallback ceiling (avoids an infinite loop if the series is abnormal), actually bounded by the series' earliest date

# Share-count checkpoints (A-shares, H-shares; both confirmed constant across this window)
SHARE_CHECKPOINTS = [
    # (effective date, A-share count, H-share count, source)
    ("2023-12-31", 9_724_196_533, 2_206_512_938, "2023 Annual Report"),
    ("2024-12-31", 9_724_196_533, 2_206_512_938, "2024 Annual Report"),
    ("2025-12-31", 9_724_196_533, 2_206_512_938, "2025 Annual Report"),
]

# Balance-sheet 4-column checkpoints — same pattern as SHARE_CHECKPOINTS:
# financial statements are released quarterly/annually, and the code has no
# way to "sense" on its own whether a new statement has come out; it can
# only rely on someone manually checking the latest figures after each
# release and appending a new checkpoint to the list.
#
# !!! Needs to be manually checked and updated every quarter !!!
# Currently there's only one entry: the value for 2025-12-12 (the
# historical dataset's last day), taken directly from vanke.xlsx — which
# specific Vanke financial statement this corresponds to (e.g. the 2025 Q3
# report) hasn't been separately verified, and this is a point that needs
# manual confirmation, to be written into the report. Once Vanke releases
# its next statement (most likely the 2025 annual report, expected in H1
# 2026), someone needs to verify the latest balance-sheet figures and add a
# new checkpoint to the end of the list below, rather than letting the code
# keep quietly reusing this old value.
BS_CHECKPOINTS = [
    # (effective date, BS_CUR_LIAB, BS_LT_BORROW, BS_TOT_LIAB2, BS_TOT_ASSET, source)
    (
        "2025-12-12",
        655_360.632475,
        221_894.376752,
        913_130.657295,
        1_242_105.617464,
        "Last day of vanke.xlsx's historical window (which specific statement this corresponds to hasn't been verified, needs manual confirmation)",
    ),
]

# If the latest BS_CHECKPOINTS entry is more than this many days older than
# the script's actual run date, print a warning reminding someone to check
# whether a new financial statement has been missed — a purely "warn if
# it's been too long since the last update" heuristic; the code itself has
# no idea when Vanke will release a new statement.
BS_STALENESS_WARN_DAYS = 100

A_SHARE_TICKER = "000002.SZ"
H_SHARE_TICKER = "2202.HK"
FX_TICKER = "CNYHKD=X"
# Fallback cross rate: when the direct CNYHKD=X can't be fetched, derive it
# via USDCNY and USDHKD instead: CNY/HKD = (USD/HKD) / (USD/CNY)
FX_FALLBACK_USD_HKD_TICKER = "HKD=X"      # USD -> HKD
FX_FALLBACK_USD_CNY_TICKER = "CNY=X"      # USD -> CNY

# HKMA's 12-month (efb_364d) Exchange Fund Bill rate — already validated as
# matching vanke.xlsx's original Risk_Free_Rate column exactly (see the
# validation results in risk_free_rate_fetch.py)
HKMA_EFBN_DAILY_URL = (
    "https://api.hkma.gov.hk/public/market-data-and-statistics/"
    "monthly-statistical-bulletin/efbn/efbn-yield-daily"
)
RATE_FIELD = "efb_364d"

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


# ---------------------------------------------------------------------------
# Stage 1: Share count / balance sheet (both low-frequency reference data,
#          checkpoint + forward-fill; both require manual quarterly
#          maintenance of the checkpoint list after checking the statements)
# ---------------------------------------------------------------------------
def get_shares_outstanding(date: dt.date) -> tuple[int, int, str]:
    cp_df = pd.DataFrame(
        SHARE_CHECKPOINTS, columns=["checkpoint_date", "a_shares", "h_shares", "source"]
    )
    cp_df["checkpoint_date"] = pd.to_datetime(cp_df["checkpoint_date"]).dt.date
    applicable = cp_df[cp_df["checkpoint_date"] <= date]
    if applicable.empty:
        row = cp_df.iloc[0]
        return int(row["a_shares"]), int(row["h_shares"]), row["source"] + "（backward-fill，未直接验证）"
    row = applicable.iloc[-1]
    return int(row["a_shares"]), int(row["h_shares"]), row["source"]


def get_balance_sheet_snapshot(date: dt.date) -> tuple[float, float, float, float, str]:
    """
    The 4 balance-sheet columns, using the same checkpoint + backward-fill
    logic as get_shares_outstanding() — see the "!!! Needs to be manually
    checked and updated every quarter !!!" comment above BS_CHECKPOINTS:
    these four figures don't update automatically; someone needs to
    manually append a new record to the end of the list after each
    statement release, otherwise it will keep reusing the previous
    checkpoint's stale value.
    """
    cp_df = pd.DataFrame(
        BS_CHECKPOINTS,
        columns=[
            "checkpoint_date",
            "bs_cur_liab",
            "bs_lt_borrow",
            "bs_tot_liab2",
            "bs_tot_asset",
            "source",
        ],
    )
    cp_df["checkpoint_date"] = pd.to_datetime(cp_df["checkpoint_date"]).dt.date
    applicable = cp_df[cp_df["checkpoint_date"] <= date]
    if applicable.empty:
        row = cp_df.iloc[0]
        source = row["source"] + "（backward-fill，未直接验证）"
    else:
        row = applicable.iloc[-1]
        source = row["source"]
    return (
        float(row["bs_cur_liab"]),
        float(row["bs_lt_borrow"]),
        float(row["bs_tot_liab2"]),
        float(row["bs_tot_asset"]),
        source,
    )


def check_bs_checkpoint_freshness(run_date: dt.date) -> None:
    """
    A reminder printed while running the pipeline: if the latest entry in
    BS_CHECKPOINTS hasn't been updated in a long time, it's quite likely a
    quarterly statement was missed — the code itself has no idea when
    Vanke will release a new statement, and can only rely on this "warn if
    it's been too long since the last checkpoint" heuristic to prompt
    someone to check.
    """
    latest_cp_date = max(dt.date.fromisoformat(cp[0]) for cp in BS_CHECKPOINTS)
    gap_days = (run_date - latest_cp_date).days
    if gap_days > BS_STALENESS_WARN_DAYS:
        print(
            f"[提醒] BS_CHECKPOINTS最新一条是{latest_cp_date}，距离脚本运行日"
            f"({run_date})已经过了{gap_days}天(超过{BS_STALENESS_WARN_DAYS}天"
            f"阈值)——大概率有新一期财报已经发布，请人工核对最新资产负债表"
            f"数字，在BS_CHECKPOINTS末尾添加新的checkpoint，而不是继续沿用"
            f"这个旧值。"
        )


# ---------------------------------------------------------------------------
# Stage 2: Bulk-fetch prices / FX rate (one request for the whole range;
#          everything else is a local operation)
# ---------------------------------------------------------------------------
def fetch_price_series(ticker: str, start: dt.date, end: dt.date) -> pd.Series:
    """Fetch closing prices for the whole range in one go; returns a Series indexed by date, sorted and deduplicated."""
    try:
        hist = yf.Ticker(ticker).history(
            start=start.isoformat(), end=(end + dt.timedelta(days=1)).isoformat()
        )
    except Exception as e:
        print(f"[警告] 批量抓取 {ticker} 失败: {type(e).__name__}: {e}")
        return pd.Series(dtype=float)

    if hist is None or hist.empty:
        print(f"[警告] {ticker} 在 {start}~{end} 区间没有拿到任何数据")
        return pd.Series(dtype=float)

    hist.index = pd.to_datetime(hist.index).date
    series = hist["Close"].sort_index()
    series = series[~series.index.duplicated(keep="last")]
    return series


def get_fx_series(start: dt.date, end: dt.date) -> tuple[pd.Series, str]:
    """
    The CNY/HKD FX rate series.

    The previous version only had the "direct connection succeeded"
    branch; when the direct connection failed, the function implicitly
    returned None, and the caller's
    `fx_series, fx_source_label = get_fx_series(...)` unpacking of None
    would throw a TypeError, with an error message that gave no hint the
    real problem was missing FX data. This version fixes that:
        1) when the direct CNYHKD=X connection fails, fall back to the
           cross rate USD/HKD divided by USD/CNY;
        2) if the cross rate also fails, explicitly raise a meaningful
           RuntimeError instead of letting the caller's unpacking crash
           for no obvious reason.
    """
    direct = fetch_price_series(FX_TICKER, start, end)
    if not direct.empty:
        return direct, "direct(CNYHKD=X)"

    print(f"[警告] {FX_TICKER} 直连拿不到数据，尝试用 USD/HKD ÷ USD/CNY 交叉汇率兜底")
    usd_hkd = fetch_price_series(FX_FALLBACK_USD_HKD_TICKER, start, end)
    usd_cny = fetch_price_series(FX_FALLBACK_USD_CNY_TICKER, start, end)
    if usd_hkd.empty or usd_cny.empty:
        raise RuntimeError(
            "CNY/HKD 汇率获取失败：直连(CNYHKD=X)和交叉汇率(HKD=X / CNY=X)都没有"
            "拿到数据，请检查网络连通性或改用其他汇率数据源，不要静默继续。"
        )

    cross = (usd_hkd / usd_cny).dropna()
    cross = cross[~cross.index.duplicated(keep="last")]
    return cross, "cross(HKD=X / CNY=X)"


def estimate_start_offset(end: dt.date, margin: int = 20, floor: int = 0) -> int:
    """
    A rough estimate: starting from offset=0 (the most recent record),
    roughly how many pages need to be paged through to reach coverage of
    `end`. Estimated using the number of weekdays (Mon-Fri) between "today"
    and `end` — the weekday count will only be larger than the actual
    number of trading days (since Hong Kong public holidays haven't been
    subtracted yet), so this estimate will run a bit larger than the true
    offset — margin pulls it back a bit, to make sure overestimating
    doesn't cause the days closest to `end` in the target window to be
    skipped over.

    Why this function exists: testing found that paging backward one page
    at a time from offset=0, to reach a date several months back like
    December 2025, meant any single request along the way timing out or
    failing would cause the whole series to come back empty (this is
    exactly what happened in the first version — offset=20 timed out
    outright, ending with "0 records fetched"). Starting to page from near
    the estimated offset instead brings the total request count down from
    over a dozen to one or two, substantially reducing the odds of a
    mid-way failure.
    """
    weekdays = 0
    d = end
    today = dt.date.today()
    while d < today:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            weekdays += 1
    return max(weekdays - margin, floor)


def fetch_hkma_rate_series(start: dt.date, end: dt.date) -> pd.Series:
    """
    Fetches HKMA's 12-month (efb_364d) Exchange Fund Bill rate, covering
    only the small [start, end] range (not the full two years like market
    cap).

    Uses offset pagination + local date filtering, rather than relying on
    the documented but unverified from/to parameters — testing previously
    found these two parameters unreliable (either ignored, or the request
    times out outright).

    The first version here paged backward one page at a time from
    offset=0 — logically correct, but testing exposed a problem: `end`
    (2025-12-31) is more than half a year from "today," so paging from
    offset=0 to there could take a dozen-plus pages, and any single
    request along the way timing out or failing would cause the whole
    function to just give up and return an empty series (the first test
    run hit exactly this — offset=20 timed out, ending with "0 records
    fetched"). This version instead first uses estimate_start_offset to
    estimate a starting offset close to `end` and starts paging from
    around there, bringing the total request count down from over a dozen
    to one or two; retry (with backoff) was also added to each request, so
    a single timeout no longer causes the whole range to be abandoned.
    """
    all_records: list[dict] = []
    offset = estimate_start_offset(end)
    page_size = 20  # tested previously to be more stable than a larger page size
    max_pages = 50  # a safety ceiling to prevent an infinite loop if the API misbehaves, not an expectation of actually paging this much
    max_retries_per_page = 4

    print(f"[利率抓取] 从估算的offset={offset}附近开始翻页(而不是从0)")

    for _ in range(max_pages):
        params = {
            "fields": f"end_of_day,{RATE_FIELD}",
            "pagesize": page_size,
            "offset": offset,
        }

        payload = None
        last_err = None
        for attempt in range(1, max_retries_per_page + 1):
            try:
                resp = requests.get(HKMA_EFBN_DAILY_URL, params=params, timeout=15)
                resp.raise_for_status()
                payload = resp.json()
                break
            except Exception as e:
                last_err = e
                print(
                    f"[警告] HKMA API请求失败 (offset={offset}, "
                    f"第{attempt}/{max_retries_per_page}次尝试): {type(e).__name__}: {e}"
                )
                time.sleep(2 * attempt)  # backoff: 2s, 4s, 6s, 8s

        if payload is None:
            print(f"[警告] offset={offset} 重试{max_retries_per_page}次后仍失败，放弃: {last_err}")
            break

        if not payload.get("header", {}).get("success"):
            print(f"[警告] HKMA API返回失败: {payload.get('header')}")
            break

        records = payload.get("result", {}).get("records", [])
        if not records:
            break

        all_records.extend(records)
        earliest_in_page = min(r["end_of_day"] for r in records)
        newest_in_page = max(r["end_of_day"] for r in records)
        earliest_date = dt.date.fromisoformat(earliest_in_page)
        newest_date = dt.date.fromisoformat(newest_in_page)

        if newest_date < end and offset == 0:
            # The estimated offset came in smaller than the true value —
            # paging all the way back to 0 still didn't reach end. This
            # shouldn't happen in theory (estimate_start_offset already
            # pulls its margin toward "closer to today"), but if it does,
            # log it for easy debugging rather than silently losing data.
            print(f"[警告] offset已经到0，最新记录({newest_date})还是早于目标end({end})，可能漏数据")

        offset += page_size
        if earliest_date <= start:
            break
        time.sleep(0.3)  # be polite to the public API
    else:
        print(f"[警告] 已翻了{max_pages}页还没翻到 {start}，可能没有覆盖完整区间，请检查")

    if not all_records:
        return pd.Series(dtype=float)

    df = pd.DataFrame(all_records)
    df["end_of_day"] = pd.to_datetime(df["end_of_day"]).dt.date
    df = df.dropna(subset=[RATE_FIELD])
    df = df[(df["end_of_day"] >= start) & (df["end_of_day"] <= end)]

    series = df.set_index("end_of_day")[RATE_FIELD].astype(float).sort_index()
    series = series[~series.index.duplicated(keep="last")]
    return series


def lookup_with_fallback(
    series: pd.Series, date: dt.date, max_lookback: int = MAX_STALE_LOOKBACK_DAYS
) -> tuple[Optional[float], Optional[dt.date], Optional[bool]]:
    """
    Looks up a given day's value in an already bulk-fetched price Series
    (a pure local operation, no network request triggered); when there's
    no data for that day (trading halt / holiday), looks backward for the
    most recent valid trading day's value as a substitute.

    The lookback boundary is the Series' own earliest date, not a fixed
    number of days — for a long holiday like Chinese New Year that can run
    9+ days in a row, a fixed "look back at most 5 days" would fail to
    find a value (return None) for the days in the middle of the holiday.
    As long as any valid trading day exists in the series before this day,
    a value can always be backfilled; max_lookback only serves as a
    fallback ceiling, to prevent an infinite loop if the series is
    abnormal (e.g. the whole series is empty).
    """
    if date in series.index:
        return float(series.loc[date]), date, False

    if series.empty:
        return None, None, None

    earliest = series.index.min()
    cursor = date
    steps = 0
    while cursor > earliest and steps < max_lookback * 20:
        cursor -= dt.timedelta(days=1)
        steps += 1
        if cursor in series.index:
            return float(series.loc[cursor]), cursor, True

    return None, None, None


# ---------------------------------------------------------------------------
# Stage 3: Build the target date grid (historical trading days + new
#          trading-day candidates)
# ---------------------------------------------------------------------------
def load_historical_input(xlsx_path: Path) -> pd.DataFrame:
    """Reads the original Input sheet of vanke.xlsx, indexed by Date, so the historical window can take the original 8 columns directly."""
    df = pd.read_excel(xlsx_path, sheet_name="Input")
    return df.set_index("Date")


def extension_trading_day_candidates(start: dt.date, end: dt.date) -> list[dt.date]:
    """
    "Trading-day candidates" for the new window — only Saturdays and
    Sundays are skipped; public holidays are left to the next step, which
    filters them out based on whether the H-share price is fresh (see the
    filtering logic in build_final_table and the "Trading-Day Calendar"
    section of the module docstring). Deliberately kept simple here —
    this step only produces candidates, it doesn't make the final call.
    """
    days = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:  # 0=Monday ... 4=Friday
            days.append(cursor)
        cursor += dt.timedelta(days=1)
    return days


def build_full_date_grid(hist_dates: list[dt.date]) -> pd.DataFrame:
    hist_set = set(hist_dates)
    ext_dates = extension_trading_day_candidates(EXTENSION_START, RANGE_END)
    all_dates = sorted(hist_set | set(ext_dates))
    return pd.DataFrame(
        {
            "Date": all_dates,
            "is_new_extension_day": [d not in hist_set for d in all_dates],
        }
    )


# ---------------------------------------------------------------------------
# Stage 4: Assemble the final table — the original 8 columns + the
#          process/validation columns we compute
# ---------------------------------------------------------------------------
def build_final_table(xlsx_path: Path = INPUT_XLSX) -> pd.DataFrame:
    original = load_historical_input(xlsx_path)
    hist_dates = [
        dt.datetime.strptime(str(d), "%Y%m%d").date() for d in original.index
    ]
    grid = build_full_date_grid(hist_dates)
    print(
        f"目标日期网格: {len(grid)} 天"
        f"（历史 {(~grid['is_new_extension_day']).sum()} 天 + "
        f"新增候选 {grid['is_new_extension_day'].sum()} 天，"
        f"新增候选只跳过周末，不跳过公众假期——见docstring'交易日日历'一节）"
    )

    a_series = fetch_price_series(A_SHARE_TICKER, RANGE_START, RANGE_END)
    h_series = fetch_price_series(H_SHARE_TICKER, RANGE_START, RANGE_END)
    fx_series, fx_source_label = get_fx_series(RANGE_START, RANGE_END)
    print(f"汇率数据来源: {fx_source_label}")

    # Only fetches the small span of rate data needed for the new window;
    # the historical window uses vanke.xlsx's original values directly,
    # with no re-fetching and no comparison validation (see the module
    # docstring's [Risk_Free_Rate Supplementation] section).
    rate_series = fetch_hkma_rate_series(EXTENSION_START, RANGE_END)
    print(f"HKMA利率数据: 抓到 {len(rate_series)} 条记录 "
          f"({EXTENSION_START} ~ {RANGE_END})")

    # The 4 balance-sheet columns: the new window uses BS_CHECKPOINTS
    # (checkpoint + backward-fill, the same pattern as share-count
    # SHARE_CHECKPOINTS), not simply hard-coded as "carry forward the last
    # day" — this way, once the next statement is released and someone
    # manually appends a new record to BS_CHECKPOINTS, this will
    # automatically switch to the new figures without any code change.
    # Before running, check whether the checkpoint is stale (see
    # check_bs_checkpoint_freshness).
    check_bs_checkpoint_freshness(dt.date.today())
    _bs_preview = get_balance_sheet_snapshot(EXTENSION_START)
    print(
        f"资产负债表checkpoint(适用于新增区间起点{EXTENSION_START}): "
        f"BS_CUR_LIAB={_bs_preview[0]:.2f}, BS_LT_BORROW={_bs_preview[1]:.2f}, "
        f"BS_TOT_LIAB2={_bs_preview[2]:.2f}, BS_TOT_ASSET={_bs_preview[3]:.2f}"
        f"（来源: {_bs_preview[4]}）"
    )

    rows = []
    for _, grid_row in grid.iterrows():
        date = grid_row["Date"]
        date_int = int(date.strftime("%Y%m%d"))
        is_extension = bool(grid_row["is_new_extension_day"])

        a_price, a_src, a_stale = lookup_with_fallback(a_series, date)
        h_price, h_src, h_stale = lookup_with_fallback(h_series, date)
        fx_rate, fx_src, fx_stale = lookup_with_fallback(fx_series, date)
        a_shares, h_shares, share_source = get_shares_outstanding(date)

        # Deliberately does NOT drop the whole row just because "H-shares
        # are closed" or "A-shares are closed" — see the "Trading-Day
        # Calendar" section of the module docstring: as long as one market
        # genuinely traded that day, the row is kept, avoiding letting one
        # market's holiday "drag down" the other market, which may have
        # had a genuine price move that day.
        # (This can create a date-alignment mismatch when merging with the
        # rate series, which is a known limitation that needs to be noted
        # in the report — this step does not forcibly align dates by
        # dropping data.)
        #
        # But if neither A-shares nor H-shares have fresh data that day
        # (is_stale is not False for either), that most likely means it's
        # a shared holiday for both markets (e.g. New Year's Day), and in
        # that case this row isn't written at all — kept consistent with
        # the same rule in dtd_pipeline/run_daily_update.py (added there
        # per the user's request), to avoid these two scripts giving
        # different answers to "does this day count as a trading day" in
        # future re-runs / range extensions. This only applies to the new
        # window — rows in the historical window come from CRI's original
        # data and are already genuine trading days by definition, so this
        # check doesn't apply there.
        if is_extension and a_stale is not False and h_stale is not False:
            print(f"[跳过] {date}：A股和H股当天都没有新鲜数据(可能是两地共同假期)，不生成这一行")
            continue

        computed_total_million = None
        if a_price is not None and h_price is not None and fx_rate is not None:
            a_cap_hkd = a_price * a_shares * fx_rate
            h_cap_hkd = h_price * h_shares
            computed_total_million = (a_cap_hkd + h_cap_hkd) / 1e6

        if not is_extension:
            # Historical window: the original columns are taken directly
            # from vanke.xlsx with no modification. Risk_Free_Rate is
            # CRI's original real value, not something we supplemented, so
            # there's no "borrowing a prior value" concern — is_stale is
            # uniformly set to False.
            orig = original.loc[date_int]
            row = {
                "Comp_no": int(orig["Comp_no"]),
                "Date": date_int,
                "CUR_MKT_CAP_ORI(HKD)": orig["CUR_MKT_CAP(HKD)"],
                "BS_CUR_LIAB(HKD)": orig["BS_CUR_LIAB(HKD)"],
                "BS_LT_BORROW(HKD)": orig["BS_LT_BORROW(HKD)"],
                "BS_TOT_LIAB2(HKD)": orig["BS_TOT_LIAB2(HKD)"],
                "BS_TOT_ASSET(HKD)": orig["BS_TOT_ASSET(HKD)"],
                "Risk_Free_Rate": orig["Risk_Free_Rate"],
                "Risk_Free_Rate_is_stale": False,
            }
        else:
            # New window: no CRI original value, ORI is left empty.
            # The BS_* columns are taken from BS_CHECKPOINTS based on the
            # current date (checkpoint + backward-fill), not hard-coded as
            # carrying forward a specific day — once the next statement is
            # released and someone adds a new checkpoint, this same code
            # will automatically switch to the new figures.
            # Risk_Free_Rate is changed to be fetched live from HKMA, using
            # lookup_with_fallback the same way as H_STOCK_PRICE to fill
            # trading-halt/holiday gaps, with is_stale explicitly flagged.
            bs_cur_liab, bs_lt_borrow, bs_tot_liab2, bs_tot_asset, bs_source = (
                get_balance_sheet_snapshot(date)
            )
            rate, rate_src, rate_stale = lookup_with_fallback(rate_series, date)
            row = {
                "Comp_no": 5338,
                "Date": date_int,
                "CUR_MKT_CAP_ORI(HKD)": None,
                "BS_CUR_LIAB(HKD)": bs_cur_liab,
                "BS_LT_BORROW(HKD)": bs_lt_borrow,
                "BS_TOT_LIAB2(HKD)": bs_tot_liab2,
                "BS_TOT_ASSET(HKD)": bs_tot_asset,
                "Risk_Free_Rate": rate,
                "Risk_Free_Rate_is_stale": rate_stale,
            }

        # DIFFERENCE = CUL - ORI. ORI is already None in the new window,
        # and None participating in arithmetic would raise an error
        # (unlike pandas' NaN, which propagates automatically), so this is
        # explicitly checked here; the effect is the same as "NaN
        # propagating automatically" — these two columns end up empty in
        # the new window either way.
        ori = row["CUR_MKT_CAP_ORI(HKD)"]
        if computed_total_million is not None and ori is not None:
            diff = computed_total_million - ori
            diff_pct = diff / ori * 100
        else:
            diff, diff_pct = None, None

        row.update(
            {
                "CUR_MKT_CAP_CUL(HKD)": computed_total_million,
                "A_STOCK_SHARE": a_shares,
                "A_STOCK_PRICE": a_price,
                "A_price_is_stale": a_stale,
                "EXCHANGE_RATE": fx_rate,
                "H_STOCK_SHARE": h_shares,
                "H_STOCK_PRICE": h_price,
                "H_price_is_stale": h_stale,
                "DIFFERENCE": diff,
                "DIFFERENCE_pct": diff_pct,
            }
        )
        rows.append(row)

    df = pd.DataFrame(rows)
    return df[FINAL_COLUMNS]


def main():
    print(f"计算区间: {RANGE_START} ~ {RANGE_END}\n")
    final_df = build_final_table()

    hist_valid = final_df[final_df["DIFFERENCE_pct"].notna()]
    print(f"\n=== 历史区间逐日校验（{len(hist_valid)}/493 天有对比数据）===")
    if not hist_valid.empty:
        print(f"平均绝对误差: {hist_valid['DIFFERENCE_pct'].abs().mean():.3f}%")
        print(f"中位数绝对误差: {hist_valid['DIFFERENCE_pct'].abs().median():.3f}%")
        print(f"最大误差: {hist_valid['DIFFERENCE_pct'].abs().max():.3f}%")
        print(f"误差超过1%的天数: {(hist_valid['DIFFERENCE_pct'].abs() > 1).sum()}")
        worst = hist_valid.reindex(
            hist_valid["DIFFERENCE_pct"].abs().sort_values(ascending=False).index
        )
        print("\n误差最大的5天：")
        print(
            worst[
                ["Date", "CUR_MKT_CAP_ORI(HKD)", "CUR_MKT_CAP_CUL(HKD)", "DIFFERENCE", "DIFFERENCE_pct"]
            ]
            .head(5)
            .to_string(index=False)
        )
    else:
        print("没有可对比的数据（本地网络不通，或yfinance拿不到数据）")

    out_path = OUTPUT_XLSX
    final_df.to_excel(out_path, sheet_name="Input", index=False)
    print(f"\n已导出完整结果 ({len(final_df)} 行): {out_path.resolve()}")

    ext_rows = final_df[final_df["Date"] >= int(EXTENSION_START.strftime("%Y%m%d"))]
    n_rate_stale = ext_rows["Risk_Free_Rate_is_stale"].sum()
    n_rate_missing = ext_rows["Risk_Free_Rate"].isna().sum()
    print(
        f"\n=== 新增交易日 (跳过周末，共{len(ext_rows)}天；12/25、12/26按讨论保留) ===\n"
        f"其中利率借用前值(is_stale)的天数: {n_rate_stale}；"
        f"完全没抓到利率的天数: {n_rate_missing}"
    )
    print(
        ext_rows[
            [
                "Date",
                "CUR_MKT_CAP_CUL(HKD)",
                "A_STOCK_PRICE",
                "A_price_is_stale",
                "H_STOCK_PRICE",
                "H_price_is_stale",
                "EXCHANGE_RATE",
                "Risk_Free_Rate",
                "Risk_Free_Rate_is_stale",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
