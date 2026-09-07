"""
ingestion.py
--------------------------------------------------------------------
Pipeline阶段1：数据摄取(ingestion)。

只负责"跟外部数据源要某一天的原始数据"，不做任何业务判断——不决定
"这天没数据该怎么办"(那是transform.py的carry-forward逻辑该管的事)，
不做单位换算、不组装最终表的行。这一层的函数全部是"给一个date，
要么拿到那天的原始值，要么明确返回None"，方便单独测试、单独重试。

这是"每日增量"该有的样子：每次只请求"一天"的数据，不像
market_cap_full_series.py里验证历史方法论时那样一次性拉两年整段——那
是一次性验证工作的合理做法(整段拉一次比循环调用2年份的单日请求更省
网络往返)，但生产环境里每天只需要当天这一份新数据，没有必要每天都去
重新拉一遍两年历史。
"""

from __future__ import annotations

import datetime as dt
import time

import pandas as pd
import requests
import yfinance as yf

import config


def fetch_day_price(ticker: str, date: dt.date) -> float | None:
    """
    某个ticker在某一天的收盘价。市场当天休市/停牌时yfinance会返回空，
    这里如实返回None，不在这一层猜测"该用哪天的旧价格代替"。
    """
    try:
        hist = yf.Ticker(ticker).history(
            start=date.isoformat(), end=(date + dt.timedelta(days=1)).isoformat()
        )
    except Exception as e:
        print(f"[ingestion警告] 抓取 {ticker} @ {date} 失败: {type(e).__name__}: {e}")
        return None

    if hist is None or hist.empty:
        return None
    return float(hist["Close"].iloc[-1])


def fetch_day_fx_rate(date: dt.date) -> tuple[float | None, str]:
    """
    CNY/HKD 汇率，某一天。先直连CNYHKD=X；拿不到就用 USD/HKD ÷ USD/CNY
    交叉汇率兜底；两个都拿不到就返回(None, "unavailable")，交给上层
    (transform.py)决定要不要往existing_table里找前一天的值。
    """
    direct = fetch_day_price(config.FX_TICKER, date)
    if direct is not None:
        return direct, "direct(CNYHKD=X)"

    usd_hkd = fetch_day_price(config.FX_FALLBACK_USD_HKD_TICKER, date)
    usd_cny = fetch_day_price(config.FX_FALLBACK_USD_CNY_TICKER, date)
    if usd_hkd is not None and usd_cny is not None and usd_cny != 0:
        return usd_hkd / usd_cny, "cross(HKD=X / CNY=X)"

    return None, "unavailable"


def _estimate_hkma_offset(end: dt.date, margin: int = 20, floor: int = 0) -> int:
    """
    粗略估算：从offset=0(最新一条)翻到能覆盖`end`这天大概要翻多少页。
    详细原理见market_cap_full_series.py里同名逻辑的注释——工作日天数会
    比实际交易日天数多(还没扣掉港股假期)，用margin往回拉一点保证不会
    因为估多了而跳过`end`附近的记录。
    """
    weekdays = 0
    d = end
    ref_today = config.today()
    while d < ref_today:
        d += dt.timedelta(days=1)
        if d.weekday() < 5:
            weekdays += 1
    return max(weekdays - margin, floor)


def fetch_day_risk_free_rate(date: dt.date) -> float | None:
    """
    HKMA 12个月期(efb_364d) Exchange Fund Bill利率，某一天。

    单天查询也用"估算起始offset + 分页 + 本地过滤"这套(而不是只查
    offset=0)：因为`date`往往不是"今天"(是过去某个待补的交易日)，直接
    从0翻到目标日期同样可能要翻很多页，复用同一套稳健分页逻辑更保险。
    """
    offset = _estimate_hkma_offset(date)
    page_size = 20  # 之前实测过比更大的分页更稳
    max_pages = 50

    for _ in range(max_pages):
        params = {
            "fields": f"end_of_day,{config.RATE_FIELD}",
            "pagesize": page_size,
            "offset": offset,
        }

        payload = None
        last_err = None
        for attempt in range(1, config.MAX_RETRIES_PER_REQUEST + 1):
            try:
                resp = requests.get(
                    config.HKMA_EFBN_DAILY_URL,
                    params=params,
                    timeout=config.REQUEST_TIMEOUT_SECONDS,
                )
                resp.raise_for_status()
                payload = resp.json()
                break
            except Exception as e:
                last_err = e
                time.sleep(2 * attempt)

        if payload is None:
            print(f"[ingestion警告] HKMA API请求失败 (offset={offset})，重试耗尽: {last_err}")
            return None

        if not payload.get("header", {}).get("success"):
            print(f"[ingestion警告] HKMA API返回失败: {payload.get('header')}")
            return None

        records = payload.get("result", {}).get("records", [])
        if not records:
            return None

        for rec in records:
            if rec["end_of_day"] == date.isoformat():
                return float(rec[config.RATE_FIELD])

        earliest_in_page = min(r["end_of_day"] for r in records)
        if dt.date.fromisoformat(earliest_in_page) < date:
            # 已经翻过目标日期了，说明这天没有报价(比如公众假期)
            return None

        offset += page_size
        time.sleep(0.3)

    return None
