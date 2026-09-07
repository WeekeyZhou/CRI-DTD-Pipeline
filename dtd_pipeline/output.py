"""
output.py
--------------------------------------------------------------------
Pipeline阶段4：输出(output)——读已有表、追加新行、写回去。

这一层是"历史数据不能被修改"这条规则真正落地的地方：load_existing_table
只读不改；append_row_and_save只允许在末尾追加新行(而且追加前会先过一遍
validate.py的检查)，historical那部分内容全程不会被重新计算或覆盖。
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import config
import validate


def historical_row_from_original(orig_row: pd.Series) -> dict:
    """
    把vanke.xlsx原始8列的一行，套进最终表的schema里——只在
    'vanke_input_extended.xlsx还不存在、需要从头bootstrap'这种情况下
    才会用到(正常情况下应该直接读已经算好的vanke_input_extended.xlsx，
    见load_existing_table)。

    这里CUL/A_STOCK_PRICE等"衍生"列留空，不在这里重新拉两年yfinance
    历史去算——那是market_cap_full_series.py专门做的一次性方法论验证
    工作，不属于这个"每日增量"pipeline的职责范围。
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
    优先读取已经存在的 vanke_input_extended.xlsx (通常是
    market_cap_full_series.py那次历史验证跑出来的、CUL/DIFFERENCE等
    衍生列都齐全的版本)；如果那个文件还不存在，退化成直接从
    config.ORIGINAL_XLSX(vanke.xlsx)的493行历史数据bootstrap一个
    最小可用的起点(衍生列留空，见historical_row_from_original的说明)。
    两个文件都没有的话没法起步，直接报错。
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
    校验通过就追加+落盘；校验不通过(errors非空)就拒绝写入、抛出异常，
    绝不会静默写入一行有问题的数据，也绝不会因为要"修正"新行而回头
    改动历史行。
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
