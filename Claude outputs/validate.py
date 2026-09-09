"""
validate.py
--------------------------------------------------------------------
Pipeline stage 3: consistency checks.

Before a newly-computed row (the output of transform.py) is actually
appended to the output table, it goes through a pass of checks here, at
two severities:
    - errors: block the row from being written (e.g. duplicate date, date
      earlier than existing data) — letting these through would break the
      output table's basic invariants (exactly one row per trading day,
      historical data never overwritten), so these must be blocked.
    - warnings: don't block the write, but are printed and left as a
      record — e.g. an unusually large single-day swing in market cap
      (could be a genuine move like the "924" rally, or could be a data
      error; it needs a human to take a look, rather than having the
      pipeline unilaterally decide "this data looks suspicious so I won't
      use it").

The checks in this version are fairly simple (the thresholds are
judgment-call numbers, not rigorous statistical anomaly detection) — the
task brief says an over-engineered framework isn't needed here; the goal is
to show that you've thought about which cases need guarding against, not to
build a mature anomaly-detection system.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import config

MARKET_CAP_JUMP_WARN_PCT = 15.0   # Flag for review if market cap changes by more than this percentage in a single day
RATE_SANE_MIN, RATE_SANE_MAX = 0.0, 20.0  # Rough sane range for the interest rate (%)


def validate_new_row(row: dict, existing_table: pd.DataFrame) -> tuple[list[str], list[str]]:
    """
    Returns (errors, warnings). The caller (output.py) should refuse to
    write the row if errors is non-empty; warnings are just printed as a
    heads-up.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- Structural check: does this row fully match the final table's schema ---
    missing_cols = [c for c in config.FINAL_COLUMNS if c not in row]
    if missing_cols:
        errors.append(f"缺少必要字段: {missing_cols}")
        return errors, warnings  # Structure is already wrong, no point in the remaining checks — return immediately

    # --- Date check: no duplicates, nothing earlier than existing data (keeps history from ever being overwritten) ---
    if not existing_table.empty:
        max_existing_date = int(existing_table["Date"].max())
        if row["Date"] in set(existing_table["Date"]):
            errors.append(f"日期{row['Date']}已经存在于输出表里，拒绝重复追加(pipeline应该是幂等的)")
        elif row["Date"] < max_existing_date:
            errors.append(f"日期{row['Date']}早于已有数据最新的{max_existing_date}，会破坏'历史不可修改'的假设")

    if errors:
        return errors, warnings

    # --- Value sanity checks (don't block the write, just a heads-up) ---
    cul = row["CUR_MKT_CAP_CUL(HKD)"]
    if cul is None:
        warnings.append("CUR_MKT_CAP_CUL(HKD)算不出来(A股/H股/汇率某一项彻底没有值，连历史兜底都没有)")
    elif not existing_table.empty:
        prev_cul_rows = existing_table[existing_table["CUR_MKT_CAP_CUL(HKD)"].notna()]
        if not prev_cul_rows.empty:
            prev_cul = float(prev_cul_rows.sort_values("Date").iloc[-1]["CUR_MKT_CAP_CUL(HKD)"])
            if prev_cul:
                pct_change = abs(cul - prev_cul) / prev_cul * 100
                if pct_change > MARKET_CAP_JUMP_WARN_PCT:
                    warnings.append(
                        f"市值较前一天变动{pct_change:.1f}%(阈值{MARKET_CAP_JUMP_WARN_PCT}%)，"
                        f"可能是真实的大行情(参考2024年924那波)，也可能是数据错误，建议人工看一眼"
                    )

    rate = row["Risk_Free_Rate"]
    if rate is not None and not (RATE_SANE_MIN <= rate <= RATE_SANE_MAX):
        warnings.append(f"Risk_Free_Rate={rate}超出合理区间[{RATE_SANE_MIN}, {RATE_SANE_MAX}]，可能是单位搞错了")

    # is_stale is three-valued (False=fresh / True=carried forward / None=no
    # value at all) — handled separately here; None must not be treated as
    # False ("not stale" would be the wrong reading).
    if row["A_price_is_stale"] is None:
        warnings.append("A_STOCK_PRICE彻底没有值(当天没抓到，existing_table里往前找也没有)")
    if row["H_price_is_stale"] is None:
        warnings.append("H_STOCK_PRICE彻底没有值(当天没抓到，existing_table里往前找也没有)")
    if row["A_price_is_stale"] and row["H_price_is_stale"]:
        warnings.append("A股和H股当天都是stale(都没有新价格)——两个市场可能同时休市，建议确认这天是否真的该算作交易日")

    return errors, warnings
