# Vanke DTD Pipeline — CRI Production-Oriented DTD Pipeline

China Vanke Co.（000002.SZ / 2202.HK）Distance-to-Default (DTD) 输入数据的
生产级pipeline，CRI实习面试任务。

- **Part 1**：把CRI提供的历史DTD输入数据（2023-12-12 ~ 2025-12-12，493个
  交易日）扩展至少5个新交易日，并搭建一套分阶段（ingestion / transform /
  consistency checks / output）、可每日增量运行的生产pipeline。
- **Part 2**：结合DTD走势与万科近年真实的信用事件，做案例分析（见
  `report/part2_case_study.md`，撰写中）。

## 目录结构

```
vanke-dtd-pipeline/
├── README.md                          # 本文件：项目总览、怎么跑、目录导航
├── requirements.txt                   # Python依赖
│
├── data/
│   ├── vanke.xlsx                     # 任务方提供的原始数据（只读，不要覆盖）
│   └── vanke_input_extended.xlsx      # pipeline产出：历史493行 + 新增交易日
│
├── scripts/
│   └── ingestion_full.py      # 一次性方法论验证脚本(见下方说明)
│
├── dtd_pipeline/                      # 每日增量更新pipeline(任务书要的生产pipeline)
│   ├── config.py                      # 共享配置：ticker、HKMA接口、checkpoint列表
│   ├── ingestion.py                   # 阶段1: 数据摄取
│   ├── transform.py                   # 阶段2: 转换/计算
│   ├── validate.py                    # 阶段3: 一致性检查
│   ├── output.py                      # 阶段4: 输出(追加+落盘)
│   ├── run_daily_update.py            # 编排入口(命令行)
│   └── README.md                      # pipeline包自己的详细说明
│
└── report/
    ├── part1_report.md                # Part 1报告：方法论、假设、局限、取舍
    └── part2_case_study.md            # Part 2：DTD vs. 万科真实信用事件案例分析
```

## 两个脚本的分工(容易混淆，先说清楚)

- **`scripts/ingestion_full.py`** 是**一次性的方法论验证脚本**：
  用两年历史数据（2023-12-12 ~ 2025-12-31）逐日对比"CRI官方市值
  (`CUR_MKT_CAP_ORI`)"和"自己用A股价×股数×汇率 + H股价×股数重构出来的市值
  (`CUR_MKT_CAP_CUL`)"，验证市值重构方法的准确性（误差中位数约0.03%），
  同时把2023-12-12 ~ 2025-12-31整段区间（历史+新增）都算出来，落盘成
  `data/vanke_input_extended.xlsx`。这个脚本已经完成它的任务，**不需要
  每天重跑**。

- **`dtd_pipeline/`** 才是任务书要的"生产级每日更新pipeline"：每次运行只
  处理**一个**新交易日，读`data/vanke_input_extended.xlsx`现有内容、算出
  新的一行、追加进去，绝不重新计算或覆盖已有的历史行。日常生产用法是
  每个交易日收盘后跑一次 `python run_daily_update.py`。详见
  `dtd_pipeline/README.md`。

## 怎么跑

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. (只需跑一次)用两年历史数据验证方法论 + 生成初始的vanke_input_extended.xlsx
cd scripts
python ingestion_full.py

# 3. 日常生产：每个交易日收盘后跑一次，只处理"下一个待处理交易日"
cd ../dtd_pipeline
python run_daily_update.py

# 也可以一次连续处理多天，或指定某一天，见dtd_pipeline/README.md
```

## 数据来源

| 数据 | 来源 |
|---|---|
| A股价格 (000002.SZ) | yfinance |
| H股价格 (2202.HK) | yfinance |
| CNY/HKD汇率 | yfinance |
| 无风险利率 (12个月Exchange Fund Bill孳息率) | 香港金管局(HKMA)公开API |
| 股本、资产负债表4列 | 万科定期财报，人工按季度维护(见`dtd_pipeline/README.md`) |

## 报告

- `report/part1_report.md` — Part 1的方法论说明：市值重构方法、准确性验证、
  pipeline架构设计、假设与局限、关键取舍。
- `report/part2_case_study.md` — Part 2：结合DTD数值走势，分析万科近年的
  真实信用事件（撰写中）。
