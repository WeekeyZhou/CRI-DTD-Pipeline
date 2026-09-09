# dtd_pipeline — Daily Incremental Update Pipeline

The daily incremental update pipeline for Vanke's DTD input data, corresponding to the "daily update" requirement in Part 1 of the task brief.

## What this package does

Each run processes exactly **one** new trading day: it takes that day's market-cap inputs (A-share price, H-share price, FX rate), the interest rate, and the 4 balance-sheet columns, computes one row, and appends it to `vanke_input_extended.xlsx` — it never recomputes or overwrites existing historical rows.

## Relationship to `ingestion_full.py`

`ingestion_full.py` is a **one-off methodology validation script**: it compares the market-cap reconstruction method (A-share price × share count × FX rate + H-share price × share count) day by day against CRI's real market-cap values over two years of history, and computes the error, demonstrating that the method is accurate. This script has already done its job — it **does not need to be re-run daily**.

`dtd_pipeline/` (this package) is the "daily production pipeline" the task brief actually asks for: run once after each day's market close, it processes only "today" — one new trading day — with no historical methodology validation involved.

If `ingestion_full.py` has already produced a `vanke_input_extended.xlsx` (506 rows — 493 historical + 13 newly added days), this pipeline picks up right where it left off and keeps appending; if that file doesn't exist yet, it falls back to bootstrapping a starting point from the 493 rows of historical data in `vanke.xlsx` (though in that case the historical rows' derived columns such as CUL will be blank — for the complete version, run `ingestion_full.py` first).

## File structure (corresponding to the task brief's "staged" requirement)

| File | Stage | Responsibility |
|---|---|---|
| `config.py` | — | Shared configuration: ticker symbols, HKMA endpoint, checkpoint lists, file paths |
| `ingestion.py` | Data ingestion | Only responsible for "asking an external source for a given day's raw data" — no business-logic decisions |
| `transform.py` | Transform / compute | Checkpoint lookups, carry-forward fallback, market-cap computation, row assembly |
| `validate.py` | Consistency checks | Dates can't be duplicated or earlier than history; value sanity checks |
| `output.py` | Output | Read the existing table (or bootstrap), append the new row, persist |
| `run_daily_update.py` | Orchestration | The command-line entry point that chains the four stages above together |

## How to run

```bash
# Process only "the next pending trading day" (the most common everyday use)
python run_daily_update.py

# Successfully write 13 trading days in a row (candidate days where neither market has fresh data are automatically skipped and don't count toward the 13)
python run_daily_update.py --days 13

# Process a specific date (must be newer than existing data)
python run_daily_update.py --date 2025-12-15
```

Usage in production: run `python run_daily_update.py` once after each Hong Kong / Shenzhen trading day's close, via cron (or another scheduler), with no arguments needed — it automatically finds "the next trading day not yet processed" and handles it.

## What needs to be done manually each quarter (not something the code can handle on its own)

`SHARE_CHECKPOINTS` (share count) and `BS_CHECKPOINTS` (balance sheet) in `config.py` are lists that require manual maintenance. Each time Vanke publishes a new financial statement:

1. Check the latest share count and the 4 balance-sheet figures;
2. Manually add a new record `(effective date, ..., source)` at the end of the corresponding list;
3. No other code needs to change — from the next run onward, `transform.py` automatically switches to the new checkpoint.

If `BS_CHECKPOINTS` hasn't been updated in more than `BS_STALENESS_WARN_DAYS` (100 days by default), `run_daily_update.py` prints a reminder on every run — don't ignore it.

## Known limitations

- `next_candidate_date` only skips Saturdays and Sundays; it doesn't hook into an actual Hong Kong Stock Exchange / Shenzhen Stock Exchange holiday calendar. But if neither A-shares nor H-shares have fresh data that day (is_stale is not False for either — covering both "a prior value was carried forward" and "no value at all"), `run_daily_update.py` judges that day to most likely be a shared holiday for both markets (e.g. New Year's Day), and skips it without writing the row; when run with `--days` / with no arguments (automatic mode) it automatically moves on to try the next candidate trading day, giving up after `MAX_CONSECUTIVE_SKIPS` (10 by default) consecutive skips and prompting a manual check of the data source. When `--date` explicitly specifies a day, there's no such "automatically look further ahead" behavior — if that day has no fresh data on either side, it's skipped and the run simply ends, without unilaterally processing some other date the user didn't ask for. This rule only covers the case where "neither market has data"; it doesn't conflict with "don't drop the whole row just because one market is closed" (see Section 5.1 of the Part 1 report).
- The thresholds in the consistency checks (`validate.py`) are all judgment-call numbers, not rigorous statistical anomaly detection — the goal is to demonstrate awareness of what needs guarding against, not to build a mature anomaly-detection system.
- The share-count and balance-sheet checkpoint mechanism assumes "changes only happen at the point a financial statement is published" — if the company undergoes an interim change between two statements (e.g. a share placement, a supplementary announcement for a debt restructuring), this mechanism won't catch it, and a temporary checkpoint needs to be added manually.
- The three `*_is_stale` columns (True/False/None) are a mixed bool/None tri-state value in Python, but after being written to Excel and read back, pandas/openpyxl coerces this kind of mixed column to `float64` — `True/False/None` becomes `1.0/0.0/NaN`. The numeric meaning is completely unchanged (1.0=True, 0.0=False, NaN=None), and converting with `.notna()`/`bool()` still reads it correctly; this isn't specially "fixed" to preserve the Python bool type — it's just documented here as a known behavior of the Excel round-trip, so nobody later compares a value read back from Excel with `is True`/`is None` and gets a surprising result.
