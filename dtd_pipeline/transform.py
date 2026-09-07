"""
transform.py
--------------------------------------------------------------------
Pipeline阶段2：转换/计算(transform)。

输入是ingestion.py抓回来的"某一天的原始值(可能是None)"+已有的输出表
(existing_table，用来做carry-forward兜底)，输出是一行符合
config.FINAL_COLUMNS schema的dict。

这一层不发网络请求(ingestion.py才发)，也不负责"这行数据到底该不该被
接受"(validate.py才管)，只管"怎么从原始输入算出最终这几列"。

【carry-forward的关键设计】
    之前 market_cap_full_series.py 里的 lookup_with_fallback 是"整段
    历史批量拉下来的Series"里往回找；这里因为ingestion.py每次只拿"当天"
    这一份数据，所以往回找不是找一个刚抓下来的历史Series，而是找
    existing_table——也就是pipeline自己之前几天already算好、已经落盘
    的那些行。这正是"每日增量更新"该有的样子：今天要用到的"上一个有效值"，
    应该来自昨天(或更早)pipeline自己算出来存好的结果，而不是重新拉一遍
    历史数据。
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

import config
import ingestion


def _date_to_int(date: dt.date) -> int:
    return int(date.strftime("%Y%m%d"))


def get_shares_outstanding(date: dt.date) -> tuple[int, int, str]:
    """股本checkpoint + backward-fill，需要人工每季度核对财报后维护
    config.SHARE_CHECKPOINTS。"""
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
    """资产负债表4列checkpoint + backward-fill，需要人工每季度核对财报后
    维护config.BS_CHECKPOINTS。"""
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
    """距上次checkpoint太久没更新就打印警告，提醒人工核对是否有新财报。"""
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
    在existing_table(已经落盘的历史+此前新增的行，按Date升序)里，找严格
    早于`date`、且`column`不是空值的最近一行，返回(值, 那一天)。
    找不到就返回(None, None)——existing_table本身有值缺口(比如刚好是
    schema第一天)时的兜底，让上层决定要不要报警。
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
    """CUR_MKT_CAP(计算值，单位:百万港元) = A股市值(换算成HKD) + H股市值(HKD)。
    已在market_cap_full_series.py里用两年历史数据验证过，误差中位数
    0.03%，具体见那份脚本和Part 1报告里的方法论验证部分。"""
    a_cap_hkd = a_price * a_shares * fx_rate
    h_cap_hkd = h_price * h_shares
    return (a_cap_hkd + h_cap_hkd) / 1e6


def build_new_row(existing_table: pd.DataFrame, date: dt.date) -> dict:
    """
    组装"新增交易日"这一行——这是唯一对外的主入口，run_daily_update.py
    每天只调用这一个函数。历史区间的行不经过这里(那些是bootstrap时直接
    从vanke.xlsx原始数据搬过来的，见output.py)。
    """
    date_int = _date_to_int(date)

    # --- 阶段2.1：拿当天的原始值(ingestion)，拿不到就从existing_table
    #     carry-forward，两种情况都要记录is_stale ---
    a_price_fresh = ingestion.fetch_day_price(config.A_SHARE_TICKER, date)
    h_price_fresh = ingestion.fetch_day_price(config.H_SHARE_TICKER, date)
    fx_rate_fresh, fx_source = ingestion.fetch_day_fx_rate(date)
    rate_fresh = ingestion.fetch_day_risk_free_rate(date)

    # 注意is_stale三种取值，不是简单的True/False二元：
    #   False = 当天有新鲜数据
    #   True  = 当天没有新数据，从existing_table里借用了前值
    #   None  = 当天没有新数据，existing_table里往前找也完全没有(彻底没
    #           有值可用)——不能写成False，那样会误导成"这是新鲜数据"
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

    # --- 阶段2.2：低频参考数据(股本、资产负债表)，checkpoint查表 ---
    a_shares, h_shares, _share_src = get_shares_outstanding(date)
    bs_cur_liab, bs_lt_borrow, bs_tot_liab2, bs_tot_asset, _bs_src = (
        get_balance_sheet_snapshot(date)
    )

    # --- 阶段2.3：算市值(计算值)。三个输入只要有一个是None(比如
    #     existing_table里也没有更早的值可以兜底)，CUL就是None，不硬凑。
    cul = None
    if a_price is not None and h_price is not None and fx_rate is not None:
        cul = compute_market_cap_cul(a_price, a_shares, fx_rate, h_price, h_shares)

    return {
        "Comp_no": config.COMP_NO,
        "Date": date_int,
        "CUR_MKT_CAP_ORI(HKD)": None,   # 新增区间没有CRI官方真实值
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
        "DIFFERENCE": None,       # ORI是None，没法算差异
        "DIFFERENCE_pct": None,
    }
