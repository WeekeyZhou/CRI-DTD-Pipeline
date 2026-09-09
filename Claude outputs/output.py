"""
output.py
--------------------------------------------------------------------
Pipeline stage 4: output — read the existing table, append the new row,
write it back.

This is where the rule "historical data can never be modified" is actually
enforced: load_existing_table only reads, never mutates; append_row_and_save
only ever appends a new row at the end (and runs it through validate.py's
checks first) — the historical portion is never recomputed or overwritten,
anywhere in this flow.
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import config
import validate


def historical_row_from_original(orig_row: pd.Series) -> dict:
    """
    Maps one row of vanke.xlsx's original 8 columns into the final table's
    schema — only used for the case where 'vanke_input_extended.xlsx
    doesn't exist yet and needs to be bootstrapped from scratch' (normally
    you should just read the already-computed vanke_input_extended.xlsx
    directly, see load_existing_table).

    The "derived" columns here (CUL, A_STOCK_PRICE, etc.) are left blank —
    this function does not re-pull two years of yfinance history to
    compute them here. That's the one-off methodology-validation work that
    market_cap_full_series.py is specifically responsible for, and it's
    outside the scope of this "daily incremental" pipeline.
    """
    return {
        "Comp_no": int(orig_row["Comp_no"]),
        "Date": int(orig_row["Date"]),
        "CUR_MKT_CAP_ORI(HKD)": orig_row["CUR_MKT_CAP(HKD)"],
        "CUR_MKT_CAP_CUL(HKD)": None,
        "BS_CUR_LIAB(HKD)": orig_row["BS_CUR_LIAB(HKD)"],
        "BS_LT_BORROW(HKD)": orig_row["BS_LT_BORROW(HKD)"],
        "BS_TOT_LIAB2(HKD)": orig_row["BS_TOT_LIAB2(HKD)"],
        "BS_TOT_ASSET(HKD)": orig_row["BS_TOT_ASSET(HKD)"],
        "Risk_Free_Rate": orig_row["Risk_Free_Rate"],
        "Risk_Free_Rate_is_stale": False,
        "A_STOCK_SHARE": None,
        "A_STOCK_PRICE": None,
        "A_price_is_stale": None,
        "EXCHANGE_RATE": None,
        "H_STOCK_SHARE": None,
        "H_STOCK_PRICE": None,
        "H_price_is_stale": None,
        "DIFFERENCE": None,
        "DIFFERENCE_pct": None,
    }


def load_existing_table() -> pd.DataFrame:
    """
    Preferentially reads the already-existing vanke_input_extended.xlsx
    (usually the version produced by that historical validation run of
    market_cap_full_series.py, with the CUL/DIFFERENCE and other derived
    columns fully populated); if that file doesn't exist yet, falls back to
    bootstrapping a minimally usable starting point directly from the 493
    rows of historical data in config.ORIGINAL_XLSX (vanke.xlsx) (with the
    derived columns left blank, see historical_row_from_original). If
    neither file exists, there's nothing to start from and this raises.
    """
    if config.EXTENDED_XLSX.exists():
        df = pd.read_excel(config.EXTENDED_XLSX, sheet_name=config.SHEET_NAME)
        print(f"[output] 读取已有表 {config.EXTENDED_XLSX} ({len(df)} 行)")
        return df[config.FINAL_COLUMNS].sort_values("Date").reset_index(drop=True)

    if config.ORIGINAL_XLSX.exists():
        print(
            f"[output] {config.EXTENDED_XLSX} 还不存在，从原始"
            f"{config.ORIGINAL_XLSX} bootstrap(衍生列会留空，"
            f"完整版本请先跑market_cap_full_series.py)"
        )
        original = pd.read_excel(config.ORIGINAL_XLSX, sheet_name=config.SHEET_NAME)
        rows = [historical_row_from_original(r) for _, r in original.iterrows()]
        df = pd.DataFrame(rows)[config.FINAL_COLUMNS]
        return df.sort_values("Date").reset_index(drop=True)

    raise FileNotFoundError(
        f"既没有{config.EXTENDED_XLSX}也没有{config.ORIGINAL_XLSX}，"
        f"pipeline没有起点数据可以增量更新，请先准备好至少一个。"
    )


def append_row_and_save(existing_table: pd.DataFrame, new_row: dict) -> pd.DataFrame:
    """
    If validation passes, append and persist; if it fails (errors is
    non-empty), reject and raise — this never silently writes a row that
    has a problem, and it never modifies historical rows to "fix" the new
    one either.
    """
    errors, warnings = validate.validate_new_row(new_row, existing_table)

    for w in warnings:
        print(f"[validate警告] {new_row['Date']}: {w}")

    if errors:
        raise ValueError(
            f"新增日期{new_row['Date']}未通过一致性检查，拒绝写入: {errors}"
        )

    updated = pd.concat(
        [existing_table, pd.DataFrame([new_row])[config.FINAL_COLUMNS]],
        ignore_index=True,
    ).sort_values("Date").reset_index(drop=True)

    updated.to_excel(config.EXTENDED_XLSX, sheet_name=config.SHEET_NAME, index=False)
    print(f"[output] 已追加 {new_row['Date']} 这一行，写回 {config.EXTENDED_XLSX}（共{len(updated)}行）")
    return updated
