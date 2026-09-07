"""
config.py
--------------------------------------------------------------------
共享配置——五个阶段文件(ingestion/transform/validate/output/
run_daily_update)都从这里读常量，不重复写。

这个包是"每日增量更新"的生产pipeline，跟之前那份 market_cap_full_series.py
是两回事：
    - market_cap_full_series.py 是"一次性"的历史验证脚本：把两年历史市值
      重构方法论跟CRI原始值逐日对比、算误差，本质是一次性的方法论验证 +
      第一次产出 vanke_input_extended.xlsx。这个脚本已经跑完了它的任务，
      不需要每天重跑。
    - 这个包(dtd_pipeline/)才是任务书Part 1真正要的"每日更新pipeline"：
      每次只处理"下一个交易日"这一天，读已有的输出表、算这一天、追加
      一行、写回去——不重新计算历史，也不重新验证方法论。

SHARE_CHECKPOINTS / BS_CHECKPOINTS 这两个"需要人工每季度维护"的列表，
在market_cap_full_series.py里已经有一份；这里保留自己的一份副本而不是
跨文件import，是故意的——这两个脚本的运行时机、维护的人可能不是同一拨
(一个是"做验证分析的时候跑一次"，一个是"每天/每次开盘后要跑的生产脚本")，
硬耦合在一起反而不利于"清晰、容易维护"这个任务书更看重的目标。
已知限制：这意味着两份checkpoint要人工保持同步，如果哪天嫌麻烦，可以后续
重构成一个共享的checkpoints.py，这次先不做（不过度设计）。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

# ---------- 文件路径 ----------
# 用__file__定位到仓库根目录下的data/，而不是用相对当前工作目录的裸文件名——
# 这样不管在终端里cd到哪个目录、用什么方式调用run_daily_update.py，都能稳定
# 找到同一份数据文件，不依赖"必须在某个特定目录下运行"这种脆弱的约定。
# 目录假设：<repo_root>/dtd_pipeline/config.py 和 <repo_root>/data/vanke*.xlsx。
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
ORIGINAL_XLSX = DATA_DIR / "vanke.xlsx"               # CRI提供的原始历史数据
EXTENDED_XLSX = DATA_DIR / "vanke_input_extended.xlsx"  # 本pipeline读取/追加/写回的表
SHEET_NAME = "Input"

# ---------- 股票/汇率数据源 ----------
A_SHARE_TICKER = "000002.SZ"
H_SHARE_TICKER = "2202.HK"
FX_TICKER = "CNYHKD=X"
FX_FALLBACK_USD_HKD_TICKER = "HKD=X"   # USD -> HKD
FX_FALLBACK_USD_CNY_TICKER = "CNY=X"   # USD -> CNY

# ---------- HKMA 利率数据源 ----------
HKMA_EFBN_DAILY_URL = (
    "https://api.hkma.gov.hk/public/market-data-and-statistics/"
    "monthly-statistical-bulletin/efbn/efbn-yield-daily"
)
RATE_FIELD = "efb_364d"  # 12个月期Exchange Fund Bill利率

# ---------- 兜底/重试参数 ----------
MAX_STALE_LOOKBACK_DAYS = 30   # 从已有输出表往回找有效值的兜底上限(交易日数)
MAX_RETRIES_PER_REQUEST = 4
REQUEST_TIMEOUT_SECONDS = 15

# ---------- 股本 checkpoint(需要人工每季度核对财报后维护) ----------
SHARE_CHECKPOINTS = [
    # (生效日期, A股股数, H股股数, 来源)
    ("2023-12-31", 9_724_196_533, 2_206_512_938, "2023年年度报告"),
    ("2024-12-31", 9_724_196_533, 2_206_512_938, "2024年年度报告"),
    ("2025-12-31", 9_724_196_533, 2_206_512_938, "2025年年度报告"),
]

# ---------- 资产负债表 checkpoint(同上，需要人工每季度维护) ----------
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

BS_STALENESS_WARN_DAYS = 100  # 最新checkpoint距今超过这么多天就报警提醒人工核对

# ---------- 最终表的列顺序 ----------
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

COMP_NO = 5338


def today() -> dt.date:
    """单独包一层，方便测试时monkeypatch（比如固定成某个日期）。"""
    return dt.date.today()