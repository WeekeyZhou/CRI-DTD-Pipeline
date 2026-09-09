# Part 1 Report: Vanke Production-Oriented DTD Pipeline

## 1. Task Overview

The Vanke (China Vanke Co., A-share 000002.SZ + H-share 2202.HK) DTD input
data provided by CRI covers 2023-12-12 to 2025-12-12, 493 trading days in
total (8 columns: `Comp_no`, `Date`, `CUR_MKT_CAP(HKD)`,
`BS_CUR_LIAB(HKD)`, `BS_LT_BORROW(HKD)`, `BS_TOT_LIAB2(HKD)`,
`BS_TOT_ASSET(HKD)`, `Risk_Free_Rate`).

Task requirements:

1. On top of the historical data, supplement market cap and risk-free-rate
   data for **at least 5 new trading days**, carrying forward the 4
   balance-sheet columns under the assumption that "no new financial
   statements are released";
2. Build a **staged, production-runnable** pipeline (data ingestion /
   transformation / consistency checks / output), rather than a one-off
   script that runs once and is done.

This report is split into two parts corresponding to these two
requirements: Section 2 covers the methodology and accuracy validation for
market-cap reconstruction and the risk-free rate; Section 3 covers the
architecture design of the daily incremental update pipeline. Section 4
summarizes assumptions and known limitations, and Section 5 covers several
explicit trade-off decisions.

## 2. Methodology and Accuracy Validation

### 2.1 Market-Cap Reconstruction

Vanke is dual-listed in Shenzhen (A-shares) and Hong Kong (H-shares);
`CUR_MKT_CAP(HKD)` is the combined market cap of both, converted into HKD.
Reconstruction formula:

```
CUR_MKT_CAP(HKD) (computed value, in HKD millions)
    = A-share closing price (CNY) × A-share count × CNY/HKD FX rate
    + H-share closing price (HKD) × H-share count
```

**Data sources**: A-share price, H-share price, and the CNY/HKD FX rate are
all taken from yfinance (tickers `000002.SZ`, `2202.HK`, and `CNYHKD=X`
respectively); when the direct FX rate is unavailable, a cross rate
`USD/HKD ÷ USD/CNY` is used as a fallback.

**Share count**: 9,724,196,533 A-shares and 2,206,512,938 H-shares, cross-
checked against four official periodic reports (Vanke's 2023 annual report
through the 2025 Q3 report) and confirmed constant over the entire
computation window (through 2025-12-31). Vanke's B-shares were fully
converted to H-shares via a "B-to-H" conversion in 2014 and no independent
B-shares remain outstanding, so no separate B-share market-cap term is
needed.

**Accuracy validation**: the computed value `CUR_MKT_CAP_CUL(HKD)` was
compared day by day against `CUR_MKT_CAP_ORI(HKD)` in CRI's original
dataset (comparison data available for all 493 historical trading days),
with `DIFFERENCE_pct = (CUL - ORI) / ORI × 100`:

- The mean/median absolute error is within 0.1%, judged to be a reasonable
  data-source convention discrepancy (e.g. minor differences in the closing-
  price timestamp or FX-rate source), not requiring an additional
  adjustment term;
- The day-by-day error shows no systematic bias in either direction and no
  drift over time, indicating the methodology itself holds up and is not
  merely matching on a couple of coincidental days.

### 2.2 Risk-Free Rate

`Risk_Free_Rate` corresponds to the Hong Kong Monetary Authority's (HKMA)
publicly available 12-month Exchange Fund Bill yield (the `efb_364d`
field), endpoint:

```
https://api.hkma.gov.hk/public/market-data-and-statistics/
monthly-statistical-bulletin/efbn/efbn-yield-daily
```

**Validation**: the `efb_364d` values fetched from HKMA were compared day
by day against the historical `Risk_Free_Rate` already present in
vanke.xlsx, over the 7 historical trading days 2025-12-04 ~ 2025-12-12,
with the result **matching exactly day by day** (2.55 / 2.55 / 2.48 / 2.50
/ 2.53 / 2.50 / 2.46, no difference even to one decimal place), confirming
that HKMA's `efb_364d` is indeed the data source for this CRI column.

**An operational detail on pagination**: the `from`/`to` parameters
documented for the HKMA endpoint proved unstable in practice (either
ignored or causing request timeouts), so pagination was switched to
`offset`/`pagesize` combined with local date filtering. When fetching a
target date from several months back, paging backward one page at a time
starting from `offset=0` means any single failed request along the way
causes the whole function to give up (observed in testing: an `offset=20`
request timing out, ultimately resulting in "0 records fetched"). The fix
estimates a starting offset close to the target based on the number of
business days between the target date and "today," compressing the total
number of requests from over a dozen down to one or two, while also adding
retry-with-backoff to each request. This improvement was applied to both
the methodology validation script and the `dtd_pipeline` package.

### 2.3 The 4 Balance-Sheet Columns

The task explicitly assumes no new financial statements are released
within the new window, so the 4 columns `BS_CUR_LIAB(HKD)`,
`BS_LT_BORROW(HKD)`, `BS_TOT_LIAB2(HKD)`, and `BS_TOT_ASSET(HKD)` are
carried forward unchanged from the last day of the historical window
(2025-12-12). Checking roughly the past 200 historical trading days, these
4 columns changed only 5 times in total, each corresponding to a financial-
statement release — consistent with the prior that "values stay constant
between two statement releases," confirming the carry-forward treatment is
reasonable.

However, "unchanged within this specific window" does not mean "never
needs attention again": Vanke will continue to release quarterly/annual
reports going forward, so rather than hard-coding the 2025-12-12 values,
they are handled through the same checkpoint mechanism used for share
count (see Section 3 for details).

## 3. Pipeline Architecture

### 3.1 Division of Labor Between the Two Scripts

- **`scripts/ingestion_full.py`**: a one-off methodology validation script
  that produces the complete 2023-12-12 ~ 2025-12-31 range (493 historical
  days + new trading days) and performs the accuracy validation described
  in Section 2. It needs to run once and does not need to be re-run daily.
- **`dtd_pipeline/`**: the **production-grade daily update pipeline** the
  task requires — each run processes exactly **one** new trading day,
  reading the existing output table, computing the new row, and appending
  it, never recomputing or overwriting existing historical rows.

### 3.2 Four Stages

| Stage | File | Responsibility |
|---|---|---|
| Data ingestion | `ingestion.py` | Solely responsible for "requesting a given day's raw data from external sources" (A-share price, H-share price, FX rate, HKMA rate); makes no business-logic judgments, returns `None` if data can't be obtained |
| Transformation / computation | `transform.py` | Checkpoint lookups (share count, balance sheet), carry-forward fallback, market-cap computation formula, assembling the row |
| Consistency checks | `validate.py` | Errors (duplicate date / earlier than existing data, which block the write) + warnings (single-day market-cap jump, rate outside a reasonable range, data entirely missing — these only alert, they don't block) |
| Output | `output.py` | Reads the existing table (or bootstraps from `vanke.xlsx` as a starting point), appends after validation passes, and persists to disk |

`run_daily_update.py` is the orchestration entry point that chains the four
stages together. CLI usage:

```bash
python run_daily_update.py                 # process only "the next pending trading day"
python run_daily_update.py --days 13       # process the next 13 candidate trading days consecutively
python run_daily_update.py --date 2025-12-15   # process a specific given day
```

### 3.3 Key Design: Carry-Forward Reads the Pipeline's Own Output, Not a Re-Fetched History

In `ingestion_full.py`, "look backward for the most recent valid value when
a given day is missing data" is done against a **bulk-fetched historical
series**; `dtd_pipeline`, on the other hand, processes only one day at a
time, and what it looks backward against is **the output table the
pipeline itself has already computed and persisted**, not a re-fetched
historical window from an external source. This is what "daily incremental
update" should actually look like: the "last valid value" needed for today
comes from what the pipeline itself computed yesterday (or earlier), not
from re-querying history.

### 3.4 is_stale: Three States, Not Binary

The three columns `A_price_is_stale`, `H_price_is_stale`, and
`Risk_Free_Rate_is_stale` are not simple True/False:

- `False`: fresh data was fetched for that day;
- `True`: no new data for that day, a prior value was borrowed from the
  output table;
- `None`: no new data for that day, and looking backward found nothing at
  all — this cannot be written as `False` (which would misleadingly imply
  "this is fresh data"), nor can it simply be treated as equivalent to
  `True`.

This three-state design wasn't there from the start — it was a bug
discovered while testing `dtd_pipeline` (see Section 5.3 for details).
After the fix, `validate.py` also added a separate warning specifically for
the `None` state, distinct from the "borrowed a prior value" case.

### 3.5 Idempotency and "History Is Immutable"

`output.py`'s `append_row_and_save` only allows appending at the end, and
runs the `validate.py` checks first: a duplicate date, or one earlier than
the latest existing date, is rejected outright with an exception raised —
never handled silently, and never "corrected" by going back and modifying
historical rows. This ensures the pipeline can be safely called repeatedly
(e.g. accidentally run twice on the same day) without corrupting existing
data.

## 4. Assumptions and Limitations

- **Share-count assumption**: assumes the A-share/H-share counts will not
  suddenly change before the 2025 annual report (expected in H1 2026) is
  released. An update entry point for when this assumption breaks has
  already been reserved via the SHARE_CHECKPOINTS mechanism.
- **Balance-sheet assumption**: continues the task's stated assumption of
  "no new financial statements within this window," carrying forward the
  last verifiable figures via the BS_CHECKPOINTS mechanism; if a temporary
  change occurs between two statement releases (e.g. a share placement, a
  supplementary debt-restructuring announcement), the current checkpoint
  mechanism will not catch it, and a temporary checkpoint would need to be
  added manually.
- **Trading-day calendar**: the CRI historical dataset actually follows the
  Hong Kong Exchange (HKEX) calendar (12/25, 12/26, and 1/1 of the
  following year for both 2023 and 2024 are entirely absent from the 493
  historical rows, even though A-shares traded normally on those days). The
  new window **does not** copy this convention — see the trade-off
  discussion in Section 5.1: this is an explicit, documented departure, not
  an oversight.
- **Suspended single stock vs. market-wide closure**: when `H_STOCK_PRICE`
  has no new price for a given day, it is uniformly treated as "the Hong
  Kong market as a whole is closed" and the prior value is carried forward;
  no case of "the broad market is open but Vanke's H-share specifically is
  suspended" was observed within the sample window — if this occurs in the
  future, the current logic will not distinguish between the two cases.
- **Consistency-check thresholds are empirical**: the thresholds in
  `validate.py` — a 15% single-day market-cap move, a [0, 20] reasonable
  range for the rate — are judgment calls, not statistically rigorous
  anomaly detection; the intent is to demonstrate "what's being guarded
  against," not to build a mature anomaly-detection system.
- **Excel read/write dtype behavior**: the three `*_is_stale` columns are a
  mixed bool/None three-state value in Python; after being written to Excel
  and read back, pandas/openpyxl forcibly casts this kind of mixed column
  to `float64` (`True/False/None` become `1.0/0.0/NaN`). The numeric
  meaning is unchanged and can be correctly interpreted via
  `.notna()`/`bool()` conversion — this was not specifically fixed to
  preserve the Python bool type; it is simply noted here as known behavior.
- **`next_candidate_date` only skips Saturdays and Sundays**: it does not
  hook into an actual HKEX/SZSE public-holiday calendar. Whether a public
  holiday gets processed depends on whether A-share/H-share/HKMA-rate data
  actually exists for that day; if none of them do, `validate.py` will
  print a "both sides stale" warning, prompting manual judgment on whether
  that day should really count as a trading day, but it will not be
  skipped automatically.

## 5. Key Trade-offs

### 5.1 Trading-Day Definition for the New Window: Not Copying CRI's Historical Convention

Upon checking vanke.xlsx, it turns out CRI's historical definition of
"trading day" actually follows the HKEX calendar, rather than "a day counts
as a trading day if any one market is open." This historical convention
could have been copied (skip the entire row when H-shares are closed), but
after discussion this approach was rejected: on 12/25 and 12/26, Shenzhen
is clearly open for normal trading — dropping the entire row (along with
the A-share's genuine price movement that day) just because the Hong Kong
market is closed would effectively let the H-share holiday "drag down" the
A-share as well, discarding real information that actually exists.

The final rule: as long as at least one market is open that day with a
real price, that day is kept as a row — whichever market has no new price
that day simply carries forward its own last closing price with an
explicit `is_stale` flag, rather than dropping the whole row.

Cost: the new window will include rows for 12/25 and 12/26, dates that
never had corresponding rows in CRI's historical window (2023, 2024) — so
the new window's and the historical window's definitions of "trading day"
are not fully consistent. This is the result of a deliberate, weighed
trade-off.

**A subsequently added exception**: the rule above only covers the case of
"at least one market open that day." If neither A-shares nor H-shares have
fresh data on a given day (e.g. New Year's Day, when both markets are
closed simultaneously), keeping a row that is "entirely propped up by
borrowed prior values on both sides" has little meaning, so both
`ingestion_full.py` and `dtd_pipeline/run_daily_update.py` were
consistently updated to: skip generating/writing that row entirely in this
case. Both scripts use the same criterion, avoiding a situation where they
independently evolve and give different answers to "does this day count as
a trading day" down the line.

### 5.2 Checkpoint Mechanism Rather Than Hard-Coded Carry-Forward

The 4 balance-sheet columns could have simply been hard-coded to "carry
forward the 2025-12-12 values," which would have been sufficient for this
task's scope (through 2025-12-31). Instead, the same checkpoint + manual
quarterly-maintenance pattern used for share count was chosen
(`BS_CHECKPOINTS`), along with a mechanism that prints a reminder once more
than `BS_STALENESS_WARN_DAYS` (default 100 days) have passed without an
update. The extra complexity buys this: the next time Vanke releases a new
financial statement, only a new record needs to be appended to the list —
no code logic needs to change. This better fits the intended nature of a
"production pipeline" that should run indefinitely, rather than being
custom-built for this one task.

### 5.3 An is_stale Semantics Bug Found and Fixed During Testing

The original carry-forward branch in `dtd_pipeline/transform.py` was
written as:

```python
a_stale = a_price is not None
```

The intent was "mark True when a prior value was successfully borrowed,"
but it didn't account for the case where "the borrow also fails (there's
no even-earlier value in the output table either)" — in that case
`a_price` is `None`, and the line above would compute `a_stale` as
`False`, incorrectly implying "this is fresh data." This was discovered
during testing and changed to explicitly distinguish three states (see
Section 3.4), with a separate warning added in `validate.py` specifically
for the `None` state. This kind of "inverted boundary condition" is
exactly what having a consistency-checks stage is for: without
`validate.py` flagging this state separately, this bug could have quietly
kept producing misleadingly-flagged data indefinitely.

### 5.4 Duplication Between the Two Checkpoint Configs

`ingestion_full.py` and `dtd_pipeline/config.py` each maintain their own
copy of `SHARE_CHECKPOINTS`/`BS_CHECKPOINTS`, rather than sharing them via
a common import. This duplication is accepted, because the two have
clearly separated responsibilities (the former is a one-off validation
script, the latter a continuously-running production module), and forcing
them to share would introduce an unnecessary inter-module dependency; the
cost is that future checkpoint updates need to be manually synced in both
places, which is noted in a comment in `dtd_pipeline/config.py` as a known
maintenance cost.

## 6. Summary

The market-cap reconstruction method was validated day by day against two
years of historical data, with mean/median error within 0.1%; the risk-
free-rate data source (HKMA's `efb_364d`) was cross-checked day by day
against 7 historical trading days and matched exactly; the balance-sheet
carry-forward follows the assumption given in the task and reserves a hook
for future statement updates. Built on this foundation, the
`dtd_pipeline` package is separated into four stages — data ingestion /
transformation / consistency checks / output — with its core design being
carry-forward that reads the pipeline's own historical output rather than
re-fetching external history, idempotency (rejecting duplicate/out-of-order
appends), and explicit three-state data-freshness flags, validated through
end-to-end tests covering scenarios such as bootstrapping, processing
multiple consecutive days, and idempotency rejection.
