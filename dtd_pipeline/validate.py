"""
validate.py
--------------------------------------------------------------------
Pipeline阶段3：一致性检查(consistency checks)。

在新算出来的一行(transform.py的产物)真正被追加进输出表之前，在这里做
一遍检查。分两个级别：
    - errors：会阻止这一行被写入(比如日期重复、日期比已有数据还早)——
      这种情况继续写下去会破坏输出表的基本假设(每个交易日恰好一行、
      历史数据不能被覆盖)，必须挡住。
    - warnings：不阻止写入，但要打印出来、留痕——比如市值单日波动异常
      大(可能是像"924"那样真实的行情，也可能是数据出错，需要人看一眼，
      而不是让pipeline自己决定"这个数据可疑所以我就不用了")。

这一版的检查都比较朴素(阈值是拍的，不是统计意义上严谨的异常检测)——
任务书说了不需要过度复杂的框架，这里的目标是"体现出你有在想哪些情况
需要防"，不是做一个成熟的异常检测系统。
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import config

MARKET_CAP_JUMP_WARN_PCT = 15.0   # 市值单日变动超过这个百分比就提醒看一眼
RATE_SANE_MIN, RATE_SANE_MAX = 0.0, 20.0  # 利率(%)的粗略合理区间


def validate_new_row(row: dict, existing_table: pd.DataFrame) -> tuple[list[str], list[str]]:
    """
    返回 (errors, warnings)。调用方(output.py)看到errors非空就应该拒绝
    写入这一行；warnings只是打印提醒。
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- 结构检查：这行是不是完整符合最终表的schema ---
    missing_cols = [c for c in config.FINAL_COLUMNS if c not in row]
    if missing_cols:
        errors.append(f"缺少必要字段: {missing_cols}")
        return errors, warnings  # 结构都不对，后面的检查没意义，直接返回

    # --- 日期检查：不能重复、不能比已有数据还早(保证historical不被覆盖) ---
    if not existing_table.empty:
        max_existing_date = int(existing_table["Date"].max())
        if row["Date"] in set(existing_table["Date"]):
            errors.append(f"日期{row['Date']}已经存在于输出表里，拒绝重复追加(pipeline应该是幂等的)")
        elif row["Date"] < max_existing_date:
            errors.append(f"日期{row['Date']}早于已有数据最新的{max_existing_date}，会破坏'历史不可修改'的假设")

    if errors:
        return errors, warnings

    # --- 数值合理性检查(不阻止写入，只是提醒) ---
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

    # is_stale是三态(False=新鲜/True=借用前值/None=彻底没有值)，这里
    # 分开处理，不要把None当成False("不是stale"是错误的解读)。
    if row["A_price_is_stale"] is None:
        warnings.append("A_STOCK_PRICE彻底没有值(当天没抓到，existing_table里往前找也没有)")
    if row["H_price_is_stale"] is None:
        warnings.append("H_STOCK_PRICE彻底没有值(当天没抓到，existing_table里往前找也没有)")
    if row["A_price_is_stale"] and row["H_price_is_stale"]:
        warnings.append("A股和H股当天都是stale(都没有新价格)——两个市场可能同时休市，建议确认这天是否真的该算作交易日")

    return errors, warnings
