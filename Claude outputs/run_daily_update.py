"""
run_daily_update.py
--------------------------------------------------------------------
The pipeline's entry point / orchestration layer — chains ingestion →
transform → validate → output together, processing one "trading day" at a
time.

This is where the "daily update" perspective of the task brief is actually
realized: instead of computing two years of history plus the new window all
at once, each run computes only "the next trading day not yet processed"
and appends one row. Backfilling several days in a row is just calling this
same single-day logic repeatedly (the --days flag), rather than writing a
separate "batch mode" — the single-day logic is the real substance; the
loop is just a thin wrapper around it.

Usage:
    python run_daily_update.py                 # Process only "the next pending trading day"
    python run_daily_update.py --days 13       # Successfully write 13 trading days in a row (candidate days where both markets are closed are skipped and don't count toward this total)
    python run_daily_update.py --date 2025-12-15   # Process a specific date (must be newer than existing data)
"""

from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd

import config
import output
import transform

# How many consecutive days of "neither A-shares nor H-shares have fresh
# data" before giving up on trying further — this purely guards against
# spinning pointlessly for a long time when the data source itself is down
# (e.g. HKMA/yfinance unreachable), not an expectation that this many
# consecutive days will genuinely be skipped in normal operation.
MAX_CONSECUTIVE_SKIPS = 10


def next_candidate_date(last_date: dt.date) -> dt.date:
    """
    The next "candidate" trading day — only skips Saturdays and Sundays; it
    does not recognize specific public holidays (e.g. New Year's Day,
    12/25). Whether a day should actually count as a trading day is left
    to the "does either market have fresh data" check in run_one_day (see
    below) — this function only skips weekends.
    """
    d = last_date + dt.timedelta(days=1)
    while d.weekday() >= 5:  # 5=Saturday, 6=Sunday
        d += dt.timedelta(days=1)
    return d


def run_one_day(existing_table: pd.DataFrame, target_date: dt.date) -> tuple[str, pd.DataFrame]:
    """
    Processes one trading day: transform computes the day → decide whether
    it should be written → (if so) validate+output append and persist.

    Returns (status, table):
        status="written": the row was successfully written; table is the
            table after appending.
        status="skipped": neither A-shares nor H-shares had fresh data that
            day (is_stale is not False for either — covering both "carried
            forward from a prior value" and "no value at all"), judged to
            most likely be a shared holiday for both markets (e.g. New
            Year's Day); the row is not written, and table is returned
            unchanged from the existing_table passed in.

    "Skip when neither market has fresh data" is a rule added at the user's
    explicit request, and it doesn't conflict with the rule discussed in
    Section 5.1 ("as long as one market is open that day, don't drop the
    whole row just because the other market is closed"): that rule is
    about the case where only one market is closed (e.g. Hong Kong closed
    on 12/25 while Shenzhen trades normally as usual), whereas this one is
    about the case where neither market has any data that day at all — in
    that case, writing a row entirely propped up by carried-forward values
    on both sides isn't very meaningful, so it's better to just skip it and
    try the next candidate trading day. The original "both sides stale"
    warning in validate.py is still kept as a backstop (in case some caller
    bypasses this and calls output.append_row_and_save directly) — the two
    layers don't conflict.
    """
    print(f"\n=== 处理交易日 {target_date} ===")
    new_row = transform.build_new_row(existing_table, target_date)

    a_has_fresh = new_row["A_price_is_stale"] is False
    h_has_fresh = new_row["H_price_is_stale"] is False
    if not a_has_fresh and not h_has_fresh:
        print(
            f"[run_daily_update] {target_date}：A股和H股当天都没有新鲜数据"
            f"(可能是两地共同的假期，比如元旦)，跳过这一天，不写入。"
        )
        return "skipped", existing_table

    updated_table = output.append_row_and_save(existing_table, new_row)
    return "written", updated_table


def main() -> None:
    parser = argparse.ArgumentParser(description="每日增量更新DTD输入数据(一次一天)")
    parser.add_argument(
        "--date", type=str, default=None,
        help="处理指定日期(YYYY-MM-DD)，必须比已有数据的最新日期新；不传就自动取下一个候选交易日",
    )
    parser.add_argument(
        "--days", type=int, default=1,
        help="连续成功写入多少个交易日(默认1天)；两地都没有新鲜数据的候选日会被跳过，不计入这个次数",
    )
    args = parser.parse_args()

    existing_table = output.load_existing_table()
    transform.check_bs_checkpoint_freshness(config.today())

    if args.date:
        # When an explicit date is given, try only that one day: if neither
        # market has fresh data, skip it and stop — this does not, just
        # because a day was skipped, go on to automatically process some
        # other day the user didn't ask for — respecting the fact that the
        # user explicitly specified which day they meant.
        run_one_day(existing_table, dt.date.fromisoformat(args.date))
        return

    last_date_int = int(existing_table["Date"].max())
    cursor = dt.datetime.strptime(str(last_date_int), "%Y%m%d").date()

    written = 0
    consecutive_skips = 0
    while written < args.days:
        cursor = next_candidate_date(cursor)
        status, existing_table = run_one_day(existing_table, cursor)

        if status == "skipped":
            consecutive_skips += 1
            if consecutive_skips >= MAX_CONSECUTIVE_SKIPS:
                print(
                    f"[run_daily_update] 连续{MAX_CONSECUTIVE_SKIPS}天都被跳过"
                    f"(两边都没有新鲜数据)，放弃继续尝试——这已经超出正常"
                    f"假期的长度，请检查数据源(yfinance/HKMA)是否连接正常。"
                )
                break
            continue

        consecutive_skips = 0
        written += 1


if __name__ == "__main__":
    main()
