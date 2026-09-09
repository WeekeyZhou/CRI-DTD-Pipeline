"""
ingestion.py
--------------------------------------------------------------------
Pipeline stage 1: data ingestion.

Responsible only for "asking an external data source for the raw data for a
given day" — it makes no business-logic decisions (it doesn't decide "what
to do when there's no data for this day"; that's transform.py's
carry-forward logic to handle), and it does no unit conversion or assembly
of the final table row. Every function at this layer follows the same
shape — "given a date, either get that day's raw value, or explicitly
return None" — which makes each one easy to test and retry in isolation.

This is what a "daily incremental" stage should look like: each run
requests only "one day" of data, unlike market_cap_full_series.py, which,
when validating the historical methodology, pulled two full years at once —
that was reasonable for a one-off validation job (pulling the whole range
once is cheaper than looping single-day requests over 2 years' worth of
dates), but in production only that day's new data point is needed, so
there's no reason to re-pull two years of history every day.
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
    The closing price for a given ticker on a given day. When the market is
    closed / the stock is halted that day, yfinance returns empty — this
    function faithfully returns None here rather than guessing at this
    layer "which older price should stand in instead".
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
    The CNY/HKD FX rate for a given day. Tries CNYHKD=X directly first; if
    that's unavailable, falls back to the cross rate USD/HKD ÷ USD/CNY; if
    neither is available, returns (None, "unavailable") and leaves it to
    the caller (transform.py) to decide whether to look up the previous
    day's value in existing_table.
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
    A rough estimate of how many pages you'd need to page through from
    offset=0 (the most recent record) to reach `end`. See the comments on
    the same-named logic in market_cap_full_series.py for the full
    rationale — the number of weekdays will be somewhat larger than the
    actual number of trading days (Hong Kong public holidays aren't
    subtracted out yet), so `margin` pulls the estimate back a bit to make
    sure over-estimating doesn't cause it to skip past the records near
    `end`.
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
    The HKMA 12-month (efb_364d) Exchange Fund Bill yield for a given day.

    Even for a single-day lookup, this uses the same "estimated starting
    offset + pagination + local filtering" approach (rather than just
    querying offset=0): since `date` is often not "today" (it's typically
    some past trading day still awaiting backfill), paging from 0 straight
    to the target date could likewise require many pages, so reusing the
    same robust pagination logic is the safer choice.
    """
    offset = _estimate_hkma_offset(date)
    page_size = 20  # Empirically more stable than a larger page size
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
            # Already paged past the target date, meaning there's no quote for this day (e.g. a public holiday)
            return None

        offset += page_size
        time.sleep(0.3)

    return None
