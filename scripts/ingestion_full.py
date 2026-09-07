"""
market_cap_full_series.py
--------------------------------------------------------------------
Task 1 (Part 1) — 万科 CUR_MKT_CAP(HKD) 全区间计算 + Risk_Free_Rate 补充
                   + 新增交易日抓取

    这一版加入了 Risk_Free_Rate 的补充逻辑（在市值这条线的基础上直接扩展，
    不是另开文件）。跟市值不一样的地方：
        - 历史区间(2023-12-12~2025-12-12)的 Risk_Free_Rate 不重新抓取、
          不做 ORI/CUL 对比校验，直接沿用 vanke.xlsx 里的原始值——这一点
          代码本来就是这么做的(orig["Risk_Free_Rate"])，这一版没有改动。
        - 只有新增区间(2025-12-13~2025-12-31)原来写死的 None，这一版换成
          从 HKMA API 实时抓取的真实利率。
    详见下面【Risk_Free_Rate补充】一节。

    这一版还补上了资产负债表4列(BS_CUR_LIAB/BS_LT_BORROW/BS_TOT_LIAB2/
    BS_TOT_ASSET)：新增区间原样结转历史区间最后一天(2025-12-12)的值，
    不用抓取、不用fallback——任务书明确假设这段窗口内没有新的财务报表
    发布，这四个数在整个新增区间就是常量。详见下面【资产负债表结转】一节。

【输出表结构】
    Comp_no, Date 打头，之后是：

        CUR_MKT_CAP_ORI(HKD), CUR_MKT_CAP_CUL(HKD),
        BS_CUR_LIAB(HKD), BS_LT_BORROW(HKD), BS_TOT_LIAB2(HKD), BS_TOT_ASSET(HKD),
        Risk_Free_Rate, Risk_Free_Rate_is_stale,
        A_STOCK_SHARE, A_STOCK_PRICE, A_price_is_stale,
        EXCHANGE_RATE,
        H_STOCK_SHARE, H_STOCK_PRICE, H_price_is_stale,
        DIFFERENCE, DIFFERENCE_pct

    输出文件是 vanke_input_extended.xlsx，单个sheet，sheet名叫"Input"
    （跟原始vanke.xlsx的sheet名对齐，方便以后对比）。

    CUR_MKT_CAP_ORI(HKD) 和 CUR_MKT_CAP_CUL(HKD) 是两个独立的列（不再像早期
    版本那样一列两用）：
        - ORI = vanke.xlsx里的原始真实值。只有历史区间(2023-12-12~2025-12-12,
          对应现有493行)才有，新增区间没有"官方真实值"，这一列是NaN。
        - CUL = 我们自己用A股价格+H股价格+汇率+股本算出来的市值。历史区间、
          新增区间都会算，两边都有值。
        - DIFFERENCE = CUR_MKT_CAP_CUL(HKD) - CUR_MKT_CAP_ORI(HKD)，
          DIFFERENCE_pct = DIFFERENCE / CUR_MKT_CAP_ORI(HKD) x 100。
          因为ORI在新增区间本来就是NaN，这两列在新增区间会自动变成NaN
          （NaN参与减法/除法的结果还是NaN），不需要额外分支判断。

    历史区间（2023-12-12 ~ 2025-12-12）：
        BS_*、Risk_Free_Rate 直接取自vanke.xlsx原始数据，不做任何修改。

    新增区间（2025-12-13 ~ 2025-12-31，vanke.xlsx里没有的日期）：
        Comp_no固定填5338；BS_*四列原样结转2025-12-12(历史区间最后一天)的
        值；Risk_Free_Rate从HKMA API抓取真实值。

【已验证的方法论】
    CUR_MKT_CAP(HKD)(计算值) = A股收盘价(CNY) x A股股数 x CNY/HKD汇率
                                + H股收盘价(HKD) x H股股数
    已用真实数据验证，历史两天的误差在0.1%以内，判定为合理误差，不需要额外加
    "流通B股"——万科B股已于2014年通过"B转H"全部转换为H股，现已无独立存续的
    B股。

【为什么"整段区间一次性抓"，而不是"每天单独发一次请求"】
    对每一天单独调用yfinance，2年多数据意味着上千次网络请求，慢且容易被限流。
    这里对每个ticker只发一次"整段区间"的请求，存成pandas Series，后续所有
    "按天查值/前向填充"都是纯本地pandas操作，不再触发额外网络请求。

【股本】
    A股9,724,196,533股、H股2,206,512,938股，来自万科2023年报~2025三季报
    四份官方定期报告交叉验证，在本次计算区间(到2025-12-31)内确认为常量。
    2025年年报要到2026年才发布，所以这是一个需要写进报告的假设：假设2025年报
    发布前股本不会突然变化。

【停牌/缺数据处理】
    某一天某个市场没有价格数据时，向前查找最近一个有效交易日的价格代替，
    并显式标记 is_stale，保证可追溯，不做静默处理。

【交易日日历——一个明确讨论过、故意做出的取舍】
    核实了一下原始vanke.xlsx：2023年和2024年的12/25、12/26、以及次年1/1，
    在历史493行里全部缺失——即使A股(深圳)在这些日子正常交易，CRI的原始
    数据集里也没有对应的行。也就是说CRI历史上对"交易日"的定义实际跟随的是
    港交所(HKEX)日历，不是"只要有一个市场开盘就算交易日"。

    这里本来考虑过照抄CRI这个历史口径（H股休市就整行跳过），但讨论后决定
    不这样做：12/25、12/26这两天深圳明明正常开盘，如果因为港股休市就把
    这一整行(连同A股当天真实的价格变动)一起丢弃，等于让H股的假期"连坐"
    到了A股头上，损失了本来存在的真实信息。所以新增区间的规则改成：只要
    有一个市场当天开盘、有真实价格，这一天就保留成一行——A股当天有新价格
    就用新价格，H股当天没有(港股休市)就沿用上一个收盘价并标记is_stale，
    反之亦然。

    这么处理的代价是：新增区间会出现12/25、12/26这两天的行，而这两个具体
    的日历日期在CRI历史上(2023、2024年)从来没有出现过对应的行——也就是说
    新增区间和历史区间对"交易日"的定义不完全一致，这是一个明确的、需要写
    进报告里的偏离，不是疏漏。

【已知限制】
    "H股当天无新价格 = 港股休市"这个判断，没有排除"大盘开市但万科H股个股
    单独停牌"的可能——样本区间内没有观察到这种情况，暂时按港股整体休市处理。

【Risk_Free_Rate补充】
    数据源跟之前验证过的一样：HKMA官方API的 efb_364d 字段(12个月期Exchange
    Fund Bill利率)——
    https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/efbn/efbn-yield-daily

    只抓新增区间(EXTENSION_START~RANGE_END)需要的这一小段日期，不像市值
    那样抓整个2年历史区间——历史区间的Risk_Free_Rate已经在vanke.xlsx里了，
    不需要重新抓取或者对比校验。

    分页方式：不从offset=0开始一页页往回翻——实测过，`end`(2025-12-31)
    离"今天"隔了大半年，从0翻到那里可能要翻十几页，中途任何一次请求超时
    就会导致整个函数直接放弃(第一次实测就是这么栽的)。改成用
    estimate_start_offset 按日期差估算一个离`end`很近的起始offset，把
    总请求数压到一两次；每次请求也加了重试(带退避)，单次超时不再导致
    直接放弃整个区间。

    这个利率本身也是港元货币市场里EFB实际交易/报价倒算出来的市场化数值，
    不是每天都有：跟H股价格是同一套港交所/香港货币市场假期日历(比如12/25、
    12/26 HKMA的数据里当天就没有这一条记录)。所以处理方式跟H_STOCK_PRICE
    完全一样：复用 lookup_with_fallback，当天没有报价就沿用最近一个有效值，
    并且用 Risk_Free_Rate_is_stale 显式标记出来，不做静默处理。

    历史区间的 Risk_Free_Rate_is_stale 统一填 False——这些是vanke.xlsx里
    的原始真实值，不是我们自己补的，不存在"借用前值"的问题。

    已用真实数据验证过准确性：2025-12-04~2025-12-12这7个历史交易日，
    HKMA抓到的efb_364d跟vanke.xlsx原始Risk_Free_Rate逐日完全一致
    （2.55/2.55/2.48/2.50/2.53/2.50/2.46，一位小数都没差）。

【资产负债表结转——checkpoint模式，需要人工每季度维护】
    任务书明确说了：假设这段窗口内(2025-12-13~2025-12-31)没有新的财务
    报表发布，BS_CUR_LIAB/BS_LT_BORROW/BS_TOT_LIAB2/BS_TOT_ASSET这四个
    数应该原样结转、保持不变。但"这段特定窗口不变"不等于"以后也一直不用
    管"——万科之后还会持续发新的季报/年报，所以这一版没有直接写死"结转
    2025-12-12"，而是照抄SHARE_CHECKPOINTS(股本)那一套模式，做成
    BS_CHECKPOINTS + get_balance_sheet_snapshot()：
        - BS_CHECKPOINTS是一个需要人工维护的列表，每条记录是
          (生效日期, 4个资产负债表数字, 来源)；
        - get_balance_sheet_snapshot(date) 找"生效日期<=date"里最新的
          那一条，逻辑跟get_shares_outstanding()完全一样；
        - 现在列表里只有一条(2025-12-12，从vanke.xlsx历史区间最后一天
          取的)，够覆盖这次的2025-12-31为止；
        - !!! 每次万科发布新一期财报，需要有人核对最新的资产负债表数字，
          在BS_CHECKPOINTS末尾手动加一条新记录 !!! ——代码不会自己去抓
          新财报，只会老老实实用列表里"生效日期"最新且不晚于当前日期的
          那一条，用旧就是没人更新的问题，不是代码逻辑的问题。
        - 加了check_bs_checkpoint_freshness()：如果最新checkpoint距离
          脚本实际运行日期超过BS_STALENESS_WARN_DAYS(默认100天)，会打印
          警告提醒人工去核对是不是有新财报没跟上——纯粹的"太久没更新就
          报警"土办法，代码本身不知道万科什么时候发新财报。

    没有加对应的is_stale标记：这四个数在原始vanke.xlsx里本来就是"两次
    财报之间保持不变"(实测过去200个历史交易日里，这四列只变过5次，对应
    5次财报更新)，checkpoint模式只是把这个已有模式往后延续、并加上人工
    维护提醒，不是我们臆造出来的borrow行为，所以跟历史区间保持同样的
    "没有is_stale列"处理方式。

    已知限制：如果万科在两次checkpoint之间突然发布补充公告调整了资产
    负债表(比如临时增发、债务重组)，这套按"财报发布日"更新的checkpoint
    机制没法捕捉到这种"非常规、非季度节奏"的变化——任务书里说了"没有新
    财务报表发布"是明确允许的假设，这个限制不在这一版的处理范围内，但
    值得写进报告的limitations。
"""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

# ---------- 配置 ----------
# 跟dtd_pipeline/config.py同样的处理：用__file__定位仓库根目录下的data/，
# 不用相对当前工作目录的裸文件名，这样不管从哪个目录调用这个脚本都能稳定
# 找到数据文件。目录假设：<repo_root>/scripts/market_cap_full_series.py
# 和 <repo_root>/data/vanke*.xlsx。
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
INPUT_XLSX = DATA_DIR / "vanke.xlsx"
OUTPUT_XLSX = DATA_DIR / "vanke_input_extended.xlsx"
RANGE_START = dt.date(2023, 12, 12)
RANGE_END = dt.date(2025, 12, 31)
EXTENSION_START = dt.date(2025, 12, 13)  # 历史数据集(截至2025-12-12)之后第一天

MAX_STALE_LOOKBACK_DAYS = 30  # 兜底上限（避免序列异常时死循环），实际由序列最早日期决定

# 股本 checkpoint（A股、H股，均已确认在此区间内为常量）
SHARE_CHECKPOINTS = [
    # (生效日期, A股股数, H股股数, 来源)
    ("2023-12-31", 9_724_196_533, 2_206_512_938, "2023年年度报告"),
    ("2024-12-31", 9_724_196_533, 2_206_512_938, "2024年年度报告"),
    ("2025-12-31", 9_724_196_533, 2_206_512_938, "2025年年度报告"),
]

# 资产负债表4列 checkpoint——跟SHARE_CHECKPOINTS同一套模式：财报是季度/年度
# 发布的，代码没办法自己"感知"新报表出了没有，只能靠人工每次财报发布后
# 核对最新数字、在列表末尾加一条新checkpoint。
#
# !!! 每个季度需要人为检查并且修改 !!!
# 这里现在只有一条：2025-12-12(历史数据集最后一天)的值，直接从vanke.xlsx
# 里取出来的——具体对应万科哪一期财报(比如2025年三季报)没有单独核实过，
# 这是需要人工确认、写进报告的一个点。等万科发布下一期财报(大概率是
# 2025年年报，预计2026年上半年发布)，需要有人核对最新的资产负债表数字，
# 在下面列表末尾加一条新的checkpoint，而不是让代码一直悄悄沿用这个旧值。
BS_CHECKPOINTS = [
    # (生效日期, BS_CUR_LIAB, BS_LT_BORROW, BS_TOT_LIAB2, BS_TOT_ASSET, 来源)
    (
        "2025-12-12",
        655_360.632475,
        221_894.376752,
        913_130.657295,
        1_242_105.617464,
        "vanke.xlsx历史区间最后一天(具体对应哪一期财报未核实，需人工确认)",
    ),
]

# 如果最新一条BS_CHECKPOINTS距离脚本实际运行日期超过这么多天，就打印警告
# 提醒人工去核对是不是有新财报没跟上——纯粹的"太久没更新就报警"土办法，
# 代码本身不知道万科什么时候发新财报。
BS_STALENESS_WARN_DAYS = 100

A_SHARE_TICKER = "000002.SZ"
H_SHARE_TICKER = "2202.HK"
FX_TICKER = "CNYHKD=X"
# 备用交叉汇率：直接的 CNYHKD=X 拿不到数据时，用 USDCNY 和 USDHKD 交叉算出来
# CNY/HKD = (USD/HKD) / (USD/CNY)
FX_FALLBACK_USD_HKD_TICKER = "HKD=X"      # USD -> HKD
FX_FALLBACK_USD_CNY_TICKER = "CNY=X"      # USD -> CNY

# HKMA 12个月期(efb_364d) Exchange Fund Bill利率——已验证过跟vanke.xlsx
# 原始Risk_Free_Rate列完全对得上(见risk_free_rate_fetch.py的验证结果)
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
# 阶段1：股本 / 资产负债表（都是低频参考数据，checkpoint + 前向填充；
#         两者都需要人工每季度核对财报后手动维护checkpoint列表）
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
    资产负债表4列，跟get_shares_outstanding()同一套checkpoint+backward-fill
    逻辑——见BS_CHECKPOINTS上面那段"!!! 每个季度需要人为检查并且修改 !!!"
    的注释：这四个数不会自动更新，需要人工每次财报发布后手动在列表末尾
    加一条新记录，否则会一直沿用上一个checkpoint的旧值。
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
    跑pipeline的时候提醒一下：如果BS_CHECKPOINTS最新一条已经很久没更新了，
    很可能是漏了一次季度财报没跟上——代码本身不知道万科什么时候发新财报，
    只能靠"距离上次checkpoint太久就报警"这种土办法提醒人工去核对。
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
# 阶段2：批量抓价格 / 汇率（整段区间一次性请求，其余是本地操作）
# ---------------------------------------------------------------------------
def fetch_price_series(ticker: str, start: dt.date, end: dt.date) -> pd.Series:
    """一次性拉取整段区间的收盘价，返回以日期为索引、已排序去重的Series。"""
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
    CNY/HKD 汇率序列。

    之前的版本这里只有"直连成功"的分支，直连失败时函数会隐式返回 None，
    调用处 `fx_series, fx_source_label = get_fx_series(...)` 对 None 解包
    会直接抛 TypeError，报错信息完全看不出是汇率数据缺失。这一版补上：
        1) 直连 CNYHKD=X 失败时，退化成 USD/HKD 除以 USD/CNY 的交叉汇率；
        2) 交叉汇率也失败的话，明确抛出有意义的 RuntimeError，而不是让
           调用处解包时莫名其妙地崩溃。
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
    粗略估算：要从offset=0(最新一条)翻到能覆盖`end`这天，大概要翻多少页。
    按"今天"到`end`之间的工作日(周一~周五)天数来估，工作日天数只会比实际
    交易日天数多(因为还没扣掉港股公众假期)，所以这个估计值会比真实offset
    偏大——用margin把它往回拉一点，确保不会因为估多了而跳过target窗口
    最靠近`end`的那几天。

    为什么要有这个函数：实测发现从offset=0开始一页一页往回翻，翻到
    2025年12月这种几个月前的日期，中途随便一次请求超时/失败就会导致
    整个序列拿不到数据(第一版就是这么栽的，offset=20直接超时，最后
    "抓到0条记录")。直接从估算出来的offset附近开始翻，能把总请求数从
    十几次压到一两次，大幅降低中途失败的概率。
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
    抓取HKMA 12个月期(efb_364d) Exchange Fund Bill利率，只覆盖[start, end]
    这一小段区间（不是市值那种整整两年）。

    用offset分页 + 本地按日期过滤，不依赖文档里没验证过的from/to参数——
    之前实测过这两个参数不稳定(要么被忽略、要么请求直接超时)。

    第一版这里是从offset=0开始一页页往回翻——逻辑上没错，但实测暴露了
    一个问题：`end`(2025-12-31)离"今天"隔了大半年，从offset=0翻到那里
    可能要翻十几页，其中任何一次请求超时/失败，整个函数就直接放弃、
    返回空序列(第一次实测就是offset=20那次超时，最后"抓到0条记录")。
    这一版改成先用 estimate_start_offset 估算一个离`end`很近的起始
    offset，直接从那附近开始翻，把总请求数从十几次压到一两次；同时给
    每次请求加上重试(带退避)，单次超时不再导致直接放弃整个区间。
    """
    all_records: list[dict] = []
    offset = estimate_start_offset(end)
    page_size = 20  # 之前实测过，比更大的分页更稳
    max_pages = 50  # 安全上限，防止接口异常时死循环，不代表预期会翻这么多页
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
                time.sleep(2 * attempt)  # 退避: 2s, 4s, 6s, 8s

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
            # 估算的offset比真实值偏小，往回退到0都没翻到end——理论上不该
            # 发生(estimate_start_offset本来就是往"更靠近今天"的方向拉的
            # margin)，但真出现的话打个日志方便排查，而不是静默漏数据。
            print(f"[警告] offset已经到0，最新记录({newest_date})还是早于目标end({end})，可能漏数据")

        offset += page_size
        if earliest_date <= start:
            break
        time.sleep(0.3)  # 对公开API客气一点
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
    在一个已经批量拉好的价格Series里查某天的值（纯本地操作，不触发网络请求）；
    当天没有数据时（停牌/假期），往前找最近一个有效交易日的值代替。

    往前找的边界是这个Series自己最早的日期，而不是固定天数——像春节这种能
    连续放9天以上的长假，固定"最多往前找5天"会导致假期中间几天找不到值
    (返回None)。只要序列里在这天之前存在过任何一个有效交易日，就一定能
    往回填到；max_lookback只作为一个兜底上限，防止序列异常(比如整个序列
    都是空的)时死循环。
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
# 阶段3：构建目标日期网格（历史交易日 + 新增交易日候选）
# ---------------------------------------------------------------------------
def load_historical_input(xlsx_path: Path) -> pd.DataFrame:
    """读入vanke.xlsx原始Input sheet，按Date建索引，供历史区间直接取用原始8列。"""
    df = pd.read_excel(xlsx_path, sheet_name="Input")
    return df.set_index("Date")


def extension_trading_day_candidates(start: dt.date, end: dt.date) -> list[dt.date]:
    """
    新增区间的"交易日候选"——只跳过周六周日，公众假期留给下一步用H股价格
    是否新鲜来过滤掉（见 build_final_table 里的过滤逻辑和模块docstring里
    "交易日日历"一节的说明）。这里故意保持简单，只做候选，不在这一步就
    下最终判断。
    """
    days = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:  # 0=周一 ... 4=周五
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
# 阶段4：组装最终表 —— 原始8列 + 我们算出来的过程列/校验列
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

    # 只抓新增区间需要的这一小段利率，历史区间直接用vanke.xlsx原始值，
    # 不重新抓取、不做对比校验（见模块docstring【Risk_Free_Rate补充】）。
    rate_series = fetch_hkma_rate_series(EXTENSION_START, RANGE_END)
    print(f"HKMA利率数据: 抓到 {len(rate_series)} 条记录 "
          f"({EXTENSION_START} ~ {RANGE_END})")

    # 资产负债表4列：新增区间用BS_CHECKPOINTS(checkpoint+backward-fill，
    # 跟股本SHARE_CHECKPOINTS同一套模式)，不是简单写死"结转最后一天"——
    # 这样下次财报发布、人工在BS_CHECKPOINTS末尾加新记录之后，这里会自动
    # 切换到新数字，不需要改代码。跑之前先检查一下checkpoint是不是太久
    # 没更新了(见check_bs_checkpoint_freshness)。
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

        # 故意不因为"H股休市"或"A股休市"就整行跳过——见模块docstring里
        # "交易日日历"一节：只要有一个市场当天真实开盘，这一行就保留，
        # 避免把另一个市场的假期"连坐"到本来有真实价格变动的市场头上。
        # （这跟利率序列合并时可能出现的日期不对齐，是一个需要在报告里
        # 说明的已知限制，不在这一步用"丢数据"来强行对齐。）
        #
        # 但如果A股和H股当天都没有新鲜数据(is_stale都不是False)，说明
        # 两地大概率是共同假期(比如元旦)，这种情况不写这一行——保持跟
        # dtd_pipeline/run_daily_update.py里同一条规则一致(那边是应用户
        # 要求加的)，避免以后重跑/扩大区间时，这两个脚本对"这天算不算
        # 交易日"给出不一样的答案。只对新增区间生效，历史区间的行来自
        # CRI原始数据，本身就是真实交易日，不做这个判断。
        if is_extension and a_stale is not False and h_stale is not False:
            print(f"[跳过] {date}：A股和H股当天都没有新鲜数据(可能是两地共同假期)，不生成这一行")
            continue

        computed_total_million = None
        if a_price is not None and h_price is not None and fx_rate is not None:
            a_cap_hkd = a_price * a_shares * fx_rate
            h_cap_hkd = h_price * h_shares
            computed_total_million = (a_cap_hkd + h_cap_hkd) / 1e6

        if not is_extension:
            # 历史区间：原始几列直接取自vanke.xlsx，不做任何修改。
            # Risk_Free_Rate是CRI的原始真实值，不是我们补的，不存在
            # "借用前值"的问题，is_stale统一填False。
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
            # 新增区间：没有CRI原始值，ORI留空。
            # BS_*四列从BS_CHECKPOINTS按当前日期取(checkpoint+backward-
            # fill)，不是写死结转某一天——等下次财报发布、人工加了新
            # checkpoint之后，同一份代码会自动切到新数字。
            # Risk_Free_Rate改成从HKMA实时抓取，跟H_STOCK_PRICE一样用
            # lookup_with_fallback补停牌/假期缺口，并显式标记is_stale。
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

        # DIFFERENCE = CUL - ORI。ORI在新增区间本来就是None，None参与运算
        # 会报错（不像pandas的NaN那样自动传播），所以这里显式判断一下；
        # 效果和"NaN自动传播"是一样的：新增区间这两列最终还是空的。
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