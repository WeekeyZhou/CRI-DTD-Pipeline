"""
transform.py
--------------------------------------------------------------------
Pipeline stage 2: transform / compute.

The input is the raw values ingestion.py fetched for a given day (which may
be None) plus the existing output table (existing_table, used for
carry-forward fallback), and the output is one dict matching the
config.FINAL_COLUMNS schema.

This layer makes no network requests (ingestion.py does that), and it isn't
responsible for "whether this row should actually be accepted"
(validate.py handles that) — it's only responsible for "how to compute
these final columns from the raw inputs".

[Key design point: carry-forward]
    In the earlier market_cap_full_series.py, lookup_with_fallback searched
    backward within a Series that had been bulk-pulled for the whole
    historical range; here, because ingestion.py only fetches "today's"
    single data point each time, searching backward doesn't mean searching
    a freshly-pulled historical Series — it means searching
    existing_table, i.e. the rows this pipeline itself has already computed
    and persisted on previous days. That's exactly what a "daily
    incremental update" should look like: the "last valid value" needed
    today should come from what the pipeline itself computed and stored
    yesterday (or earlier), not from re-pulling history.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import config
import ingestion


def _date_to_int(date: dt.date) -> int:
    return int(date.strftime("%Y%m%d"))


def get_shares_outstanding(date: dt.date) -> tuple[int, int, str]:
    """Share-count checkpoint + backward-fill; requires manually maintaining
    config.SHARE_CHECKPOINTS against the financial statements each quarter."""
    cp_df = pd.DataFrame(
        config.SHARE_CHECKPOINTS,
        columns=["checkpoint_date", "a_shares", "h_shares", "source"],
    )
    cp_df["checkpoint_date"] = pd.to_datetime(cp_df["checkpoint_date"]).dt.date
    applicable = cp_df[cp_df["checkpoint_date"] <= date]
    if applicable.empty:
        row = cp_df.iloc[0]
        return int(row["a_shares"]), int(row["h_shares"]), row["source"] + "（backward-fill，未直接验证）"
    row = applicable.iloc[-1]
    return int(row["a_shares"]), int(row["h_shares"]), row["source"]


def get_balance_sheet_snapshot(date: dt.date) -> tuple[float, float, float, float, str]:
    """The 4 balance-sheet columns' checkpoint + backward-fill; requires
    manually maintaining config.BS_CHECKPOINTS against the financial
    statements each quarter."""
    cp_df = pd.DataFrame(
        config.BS_CHECKPOINTS,
        columns=[
            "checkpoint_date", "bs_cur_liab", "bs_lt_borrow",
            "bs_tot_liab2", "bs_tot_asset", "source",
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
        float(row["bs_cur_liab"]), float(row["bs_lt_borrow"]),
        float(row["bs_tot_liab2"]), float(row["bs_tot_asset"]), source,
    )


def check_bs_checkpoint_freshness(run_date: dt.date) -> None:
    """Prints a warning if too long has passed since the last checkpoint, prompting a manual check for a new financial statement."""
    latest_cp_date = max(dt.date.fromisoformat(cp[0]) for cp in config.BS_CHECKPOINTS)
    gap_days = (run_date - latest_cp_date).days
    if gap_days > config.BS_STALENESS_WARN_DAYS:
        print(
            f"[transform提醒] BS_CHECKPOINTS最新一条是{latest_cp_date}，距离"
            f"运行日({run_date})已经过了{gap_days}天(超过"
            f"{config.BS_STALENESS_WARN_DAYS}天阈值)——请人工核对最新资产"
            f"负债表数字，在config.BS_CHECKPOINTS末尾添加新的checkpoint。"
        )


def carry_forward(existing_table: pd.DataFrame, column: str, date: dt.date) -> tuple[float | None, dt.date | None]:
    """
    Searches existing_table (persisted history plus previously-appended new
    rows, ascending by Date) for the most recent row strictly before
    `date` where `column` is non-null, and returns (value, that date).
    Returns (None, None) if none is found — this is the fallback for when
    existing_table itself has a gap (e.g. this is right at the start of the
    schema), and it's left to the caller to decide whether to warn about
    it.
    """
    date_int = _date_to_int(date)
    prior = existing_table[existing_table["Date"] < date_int]
    prior = prior[prior[column].notna()]
    if prior.empty:
        return None, None
    last_row = prior.sort_values("Date").iloc[-1]
    src_date = dt.datetime.strptime(str(int(last_row["Date"])), "%Y%m%d").date()
    return float(last_row[column]), src_date


def compute_market_cap_cul(
    a_price: float, a_shares: int, fx_rate: float, h_price: float, h_shares: int
) -> float:
    """CUR_MKT_CAP (computed value, in millions of HKD) = A-share market cap
    (converted to HKD) + H-share market cap (HKD). Already validated
    against two years of historical data in market_cap_full_series.py, with
    a median error of 0.03% — see that script and the methodology
    validation section of the Part 1 report for details."""
    a_cap_hkd = a_price * a_shares * fx_rate
    h_cap_hkd = h_price * h_shares
    return (a_cap_hkd + h_cap_hkd) / 1e6


def build_new_row(existing_table: pd.DataFrame, date: dt.date) -> dict:
    """
    Assembles the row for a "newly added trading day" — this is the only
    public entry point; run_daily_update.py calls only this one function
    each day. Historical-range rows never go through here (those are
    carried straight over from the raw vanke.xlsx data during bootstrap,
    see output.py).
    """
    date_int = _date_to_int(date)

    # --- Step 2.1: fetch the day's raw values (ingestion); if unavailable,
    #     carry-forward from existing_table — either way, record is_stale ---
    a_price_fresh = ingestion.fetch_day_price(config.A_SHARE_TICKER, date)
    h_price_fresh = ingestion.fetch_day_price(config.H_SHARE_TICKER, date)
    fx_rate_fresh, fx_source = ingestion.fetch_day_fx_rate(date)
    rate_fresh = ingestion.fetch_day_risk_free_rate(date)

    # Note that is_stale has three possible values, not a simple True/False binary:
    #   False = fresh data for this day
    #   True  = no new data for this day, a prior value was carried forward from existing_table
    #   None  = no new data for this day, AND nothing found looking backward in
    #           existing_table either (no usable value at all) — must not be
    #           written as False, which would misleadingly imply "this is fresh data"
    if a_price_fresh is not None:
        a_price, a_stale = a_price_fresh, False
    else:
        a_price, _ = carry_forward(existing_table, "A_STOCK_PRICE", date)
        a_stale = True if a_price is not None else None

    if h_price_fresh is not None:
        h_price, h_stale = h_price_fresh, False
    else:
        h_price, _ = carry_forward(existing_table, "H_STOCK_PRICE", date)
        h_stale = True if h_price is not None else None

    if fx_rate_fresh is not None:
        fx_rate = fx_rate_fresh
    else:
        fx_rate, _ = carry_forward(existing_table, "EXCHANGE_RATE", date)
        print(f"[transform警告] {date} 汇率({fx_source})拿不到新值，沿用前值兜底")

    if rate_fresh is not None:
        rate, rate_stale = rate_fresh, False
    else:
        rate, _ = carry_forward(existing_table, "Risk_Free_Rate", date)
        rate_stale = True if rate is not None else None

    # --- Step 2.2: low-frequency reference data (share count, balance sheet), checkpoint lookup ---
    a_shares, h_shares, _share_src = get_shares_outstanding(date)
    bs_cur_liab, bs_lt_borrow, bs_tot_liab2, bs_tot_asset, _bs_src = (
        get_balance_sheet_snapshot(date)
    )

    # --- Step 2.3: compute the market cap (computed value). If any one of
    #     the three inputs is None (e.g. existing_table has no earlier
    #     value to fall back on either), CUL is left as None rather than
    #     forced through with a partial computation.
    cul = None
    if a_price is not None and h_price is not None and fx_rate is not None:
        cul = compute_market_cap_cul(a_price, a_shares, fx_rate, h_price, h_shares)

    return {
        "Comp_no": config.COMP_NO,
        "Date": date_int,
        "CUR_MKT_CAP_ORI(HKD)": None,   # No official CRI real value for the newly-added range
        "CUR_MKT_CAP_CUL(HKD)": cul,
        "BS_CUR_LIAB(HKD)": bs_cur_liab,
        "BS_LT_BORROW(HKD)": bs_lt_borrow,
        "BS_TOT_LIAB2(HKD)": bs_tot_liab2,
        "BS_TOT_ASSET(HKD)": bs_tot_asset,
        "Risk_Free_Rate": rate,
        "Risk_Free_Rate_is_stale": rate_stale,
        "A_STOCK_SHARE": a_shares,
        "A_STOCK_PRICE": a_price,
        "A_price_is_stale": a_stale,
        "EXCHANGE_RATE": fx_rate,
        "H_STOCK_SHARE": h_shares,
        "H_STOCK_PRICE": h_price,
        "H_price_is_stale": h_stale,
        "DIFFERENCE": None,       # ORI is None, so the difference can't be computed
        "DIFFERENCE_pct": None,
    }
