"""
run_daily_update.py
--------------------------------------------------------------------
Pipeline的入口/编排层——把 ingestion → transform → validate → output
四个阶段串起来，一次只处理"一个交易日"。

这是任务书"daily update"视角要落地的地方：不是把两年历史+新增窗口
一次性算完，而是"每次运行，只算下一个还没处理过的交易日，追加一行"。
要连续补多天，就是把这个单日逻辑重复调用多次(--days参数)，而不是另外
写一套"批量模式"的代码——单日逻辑才是本体，循环只是薄薄一层外壳。

用法：
    python run_daily_update.py                 # 只处理"下一个待处理交易日"这一天
    python run_daily_update.py --days 13       # 连续成功写入13个交易日(两地都休市的候选日会被跳过、不计入这个次数)
    python run_daily_update.py --date 2025-12-15   # 处理指定的某一天(必须比已有数据新)
"""

from __future__ import annotations

import argparse
import datetime as dt

import pandas as pd

import config
import output
import transform

# 连续多少天"A股和H股都没有新鲜数据"就放弃继续往后试——纯粹是防止数据源
# 异常(比如HKMA/yfinance整体连不上)时陷入无意义的长时间空转，不代表预期
# 真的会连续跳过这么多天。
MAX_CONSECUTIVE_SKIPS = 10


def next_candidate_date(last_date: dt.date) -> dt.date:
    """
    下一个"候选"交易日——只跳过周六周日，不识别具体的公众假期(比如元旦、
    12/25)。是不是真的该算作交易日，交给run_one_day里"两边是否都有新鲜
    数据"的判断去处理(见下面的说明)，这里只管跳过周末。
    """
    d = last_date + dt.timedelta(days=1)
    while d.weekday() >= 5:  # 5=周六, 6=周日
        d += dt.timedelta(days=1)
    return d


def run_one_day(existing_table: pd.DataFrame, target_date: dt.date) -> tuple[str, pd.DataFrame]:
    """
    处理一个交易日：transform算这一天 → 判断要不要写入 → (要写入的话)
    validate+output追加落盘。

    返回 (status, table)：
        status="written"：成功写入这一行，table是追加后的新表。
        status="skipped"：A股和H股当天都没有新鲜数据(is_stale都不是
            False——包括"借用了前值"和"彻底没有值"两种情况)，判定为
            两地大概率共同休市(比如元旦)，不写入这一行，table跟传入的
            existing_table保持不变。

    "都没有新鲜数据就跳过"是应用户明确要求加的规则，跟第5.1节讨论过的
    "只要有一个市场当天开盘，就不因为另一个市场休市而丢弃整行"并不矛盾：
    那条规则针对的是"只有一个市场休市"的情况(比如12/25港股休市但深圳
    正常开盘)，这里针对的是"两个市场当天都没有开盘/没有数据"的情况——
    这时候写一行"两边全部靠借用前值撑出来"的数据意义不大，不如直接跳过、
    尝试下一个候选交易日。validate.py里原有的"两边都stale"警告继续保留
    作为兜底(万一有调用方绕开这里、直接调用output.append_row_and_save)，
    两层不冲突。
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
        # 显式指定某一天时，只尝试这一天：如果两边都没有新鲜数据就跳过
        # 并结束，不会因为跳过就自动去处理用户没有要求的别的日期——尊重
        # "用户明确指定了是哪一天"这个意图。
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