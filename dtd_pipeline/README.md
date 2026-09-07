# dtd_pipeline — 每日增量更新Pipeline

万科DTD输入数据的每日增量更新pipeline，对应任务书Part 1的"daily update"要求。

## 这个包是做什么的

每次运行，只处理**一个**新的交易日：拿这一天的市值输入(A股价、H股价、汇率)、
利率、资产负债表4列，算出一行，追加进 `vanke_input_extended.xlsx`，绝不
重新计算或覆盖已有的历史行。

## 跟 `ingestion_full.py` 的关系

`ingestion_full.py` 是**一次性的方法论验证脚本**：把市值重构方法
(A股价×股数×汇率 + H股价×股数)跟CRI两年历史的真实市值逐日对比、算误差，
证明这套方法准确。这个脚本已经跑完了它的任务，**不需要每天重跑**。

`dtd_pipeline/`(这个包)才是任务书要的"每日生产pipeline"：每天开盘后跑一次，
只处理"今天"这一个新交易日，不涉及历史方法论验证。

如果 `ingestion_full.py` 已经跑出过 `vanke_input_extended.xlsx`
(506行，历史493行+新增13天)，这个pipeline会直接接着它继续往后追加；
如果还没有这个文件，会退化成从 `vanke.xlsx` 的493行历史数据bootstrap一个
起点(但这种情况下历史行的CUL等衍生列会是空的——完整版本请先跑一次
`ingestion_full.py`)。

## 文件结构(对应任务书要求的"分阶段")

| 文件 | 阶段 | 职责 |
|---|---|---|
| `config.py` | — | 共享配置：ticker、HKMA接口、checkpoint列表、文件路径 |
| `ingestion.py` | 数据摄取 | 只管"跟外部要某一天的原始数据"，不做任何业务判断 |
| `transform.py` | 转换/计算 | checkpoint查表、carry-forward兜底、算市值、组装一行 |
| `validate.py` | 一致性检查 | 日期不能重复/不能比历史还早、数值合理性检查 |
| `output.py` | 输出 | 读已有表(或bootstrap)、追加新行、落盘 |
| `run_daily_update.py` | 编排 | 把以上四个阶段串起来的命令行入口 |

## 怎么跑

```bash
# 只处理"下一个待处理交易日"这一天(最常见的日常用法)
python run_daily_update.py

# 连续成功写入13个交易日(两地都没有新鲜数据的候选日会被自动跳过，不计入这13天)
python run_daily_update.py --days 13

# 处理指定的某一天(必须比已有数据的最新日期新)
python run_daily_update.py --date 2025-12-15
```

生产环境里的用法：每个港股/深股交易日收盘后，用cron(或者别的调度工具)
跑一次 `python run_daily_update.py`，不用传任何参数——它会自己找到"下一个
还没处理的交易日"去处理。

## 每季度需要人工做的事(不是代码能自动搞定的)

`config.py` 里的 `SHARE_CHECKPOINTS`(股本) 和 `BS_CHECKPOINTS`(资产负债表)
是需要人工维护的列表。万科每次发布新一期财报后：

1. 核对最新的股本、资产负债表4个数字；
2. 在对应的列表末尾手动加一条新记录 `(生效日期, ..., 来源)`；
3. 不需要改任何其他代码——从下一次运行开始，`transform.py` 会自动切到
   新的checkpoint。

如果超过 `BS_STALENESS_WARN_DAYS`(默认100天)还没更新过 `BS_CHECKPOINTS`，
`run_daily_update.py` 每次运行都会打印一条提醒，别忽略它。

## 已知限制

- `next_candidate_date` 只跳过周六周日，不对接真正的港交所/深交所假日
  日历。但如果A股和H股当天都没有新鲜数据(is_stale都不是False——包括
  "借用了前值"和"彻底没有值"两种情况)，`run_daily_update.py` 会判定这天
  大概率是两地共同的假期(比如元旦)，跳过、不写入这一行；用`--days`/不带
  参数(自动模式)运行时会自动接着尝试下一个候选交易日，最多连续跳过
  `MAX_CONSECUTIVE_SKIPS`(默认10)天后放弃并提醒人工检查数据源。用
  `--date`显式指定某一天时不会有这个"自动往后找"的行为——如果那天两边
  都没有新鲜数据，会跳过并直接结束，不会擅自处理用户没有要求的别的日期。
  这条规则只处理"两个市场都没数据"的情况，跟"只有一个市场休市时不整行
  丢弃"(见Part 1报告5.1节)并不矛盾。
- 一致性检查(`validate.py`)的阈值都是拍的，不是严谨的统计异常检测，
  目的是体现"有在防哪些情况"，不是一套成熟的异常检测系统。
- 股本、资产负债表的checkpoint机制假设"变化只发生在财报发布的时点"——
  如果公司在两次财报之间发生临时性变化(比如增发、债务重组的补充公告)，
  这套机制捕捉不到，需要人工手动干预加一条临时checkpoint。
- `*_is_stale`这三列(True/False/None)在Python里是bool/None混合的三态值，
  但写入Excel再读回来之后，pandas/openpyxl会把这种混合列强制转成
  `float64`——`True/False/None`变成`1.0/0.0/NaN`。数值上的含义完全
  不变(1.0=True, 0.0=False, NaN=None)，用`.notna()`/`bool()`转换后
  照样能正确解读，这里不特意"修复"成保留Python bool类型，只是记录这个
  Excel round-trip的已知行为，避免以后有人直接用`is True`/`is None`
  去比较从Excel里读回来的值而得到意外结果。
