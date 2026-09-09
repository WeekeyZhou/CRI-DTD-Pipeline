# Part 2 — Case Study Reflection: DTD and Real-World Credit Events

**Firm:** China Vanke Co., Ltd. (万科, 000002.SZ / 2202.HK)
**DTD sample window:** 2023-12-12 to 2025-12-12 (493 trading days, CRI production output)

![China Vanke DTD vs. public credit events](assets/dtd_vs_events_en.png)

## 1. How DTD is computed (methodological background)

This section draws on three official CRI Technical Report addenda: **Addendum 8** (Version 2012, Update 2; published 15 May 2013) — the full DTD computation methodology; **Addendum 1** (Version 2020, Update 1; published 14 Sep 2020) — a change to the calibration frequency of σ; and **Addendum 4** (Version 2021, Update 1; published 11 May 2022) — a stabilization treatment for δ. I was not able to obtain the original base Technical Report itself, so some details (e.g. the exact estimation-window length, the DTD-to-PD mapping) are inferred rather than directly confirmed.

**The formula.** DTD is a Merton structural-credit-model quantity:

$$\text{DTD}_t = \frac{1}{\sigma\sqrt{T-t}}\log\left(\frac{\hat V_t}{L_t}\right)$$

where $\hat V_t$ is the firm's **implied (unobservable) market value of assets**, solved from the standard equity-as-a-call-option relationship:

$$E_t = V_t N(d_1) - e^{-r(T-t)} L_t N(d_2), \qquad d_{1,2} = \frac{\log(V_t/L_t) + \left(r \pm \tfrac{\sigma^2}{2}\right)(T-t)}{\sigma\sqrt{T-t}}$$

given the observed equity value $E_t$ (market cap), the risk-free rate $r$, and a fixed one-year horizon ($T-t=1$). $L_t$ is the **default point**:

$$L_t = \text{current liabilities} + \tfrac{1}{2}\times\text{long-term borrowings} + \delta \times \text{other liabilities}$$

Mapped onto `vanke.xlsx`: `CUR_MKT_CAP` is $E_t$; `BS_CUR_LIAB` and `BS_LT_BORROW` feed $L_t$ directly; the residual (`BS_TOT_LIAB2` − `BS_CUR_LIAB` − `BS_LT_BORROW`) is the "other liabilities" term weighted by δ; `BS_TOT_ASSET` (book asset value) is used as a sanity-check/seed in the estimation process rather than entering the DTD formula directly; `Risk_Free_Rate` is $r$.

**Where σ and δ come from.** Neither is observed directly — both are estimated by maximum likelihood over a historical window of the firm's implied-asset-value path (Addendum 8, Eq. 1). Addendum 4 describes δ estimates as unstable "due to a limited number of changes in balance sheet items over a course of **two years**," which implies the estimation window is on that order. σ was originally calibrated **monthly**, but changed to **daily** from 14 Sep 2020 (Addendum 1) to avoid a documented "double-jump" artifact — illustrated with a Singapore Airlines rights-issue case study — where a market-cap move plus a delayed monthly σ update could combine to produce a spurious swing in DTD/PD unrelated to any real change in credit risk. δ remains estimated on a slower cadence and, since 10 May 2022 (Addendum 4), is smoothed across a firm's industry sector (12-sector CRI classification) so that it does not jump around when the number of comparable firms in a calibration group hovers near a 10-firm threshold.

**DTD is not the same object as PD.** All three documents describe how DTD itself is computed; none describes how CRI turns DTD into a probability of default. That is a separate, downstream model (publicly, CRI describes a forward-intensity approach rather than a simple normal-CDF transform of DTD), so DTD and a published PD are related but not numerically interchangeable — a large move in one does not necessarily produce a proportionate move in the other.

## 2. Event timeline (public information)

| Date | Event | Source |
|---|---|---|
| 2023-10-26 *(pre-window)* | Vanke offshore USD bonds plunge on an unfounded "major shareholder selling" rumor; A-shares hit an ~8-year low (¥11.07, 2023-11-03) | [中国基金报](https://www.chnfund.com/article/AR2023110618095550109416) |
| 2023-11-06 *(pre-window, context)* | Shenzhen SASAC (国资委) holds a briefing stating Vanke has "no financial risk, no management risk," pledges market-based support | [中国基金报](https://www.chnfund.com/article/AR2023110618095550109416) |
| **2023-12-12** | **DTD sample window opens** (DTD = 1.57) | vanke.xlsx |
| 2024-03-11/12 | Moody's revokes Vanke's investment-grade issuer rating, Baa3 → Ba1 (junk); cites ~40% YoY contract-sales decline and insurer-debt extension talks | [Mingtiandi](https://www.mingtiandi.com/real-estate/finance/moodys-cancels-china-vanke-issuer-rating-downgrades-bonds/) |
| 2024-04-10/11 | Jinan GM taken away for investigation by police (unrelated personal matter, per company); S&P downgrades Vanke 3 notches, BBB+ → BB+ (junk), negative outlook, same day | [Yahoo Finance](https://finance.yahoo.com/news/china-vanke-shares-bonds-fall-093702212.html) |
| 2024-09-24 – 10-07 | Beijing's broad stimulus package ("9·24 行情") triggers a market-wide China-equity rally; Vanke A-shares hit limit-up | [北京商报](https://www.bbtnews.com.cn/2024/1024/534382.shtml), [新浪财经](https://finance.sina.com.cn/roll/2024-09-25/doc-incqknpk5036713.shtml) |
| 2025-01-27/28 | 郁亮 steps down as board chairman (→ executive VP); Shenzhen Metro (深铁, controlling shareholder) effectively takes over operations; Vanke discloses an approx. RMB 45bn loss for FY2024; Shenzhen SASAC states it has "enough bullets" to support Vanke | [澎湃新闻](https://m.thepaper.cn/newsDetail_forward_32345333), [深圳新闻网](https://www.sznews.com/news/content/2025-01/27/content_31453012.htm) |
| 2025-11-03 | Shenzhen Metro tightens rescue-loan terms — demands new collateral on RMB 20.37bn of previously *unsecured* loans — while Vanke's Q3 loss deepens | [Bloomberg](https://www.bloomberg.com/news/articles/2025-11-03/vanke-bonds-plunge-as-biggest-backer-tightens-rescue-loan-terms) |
| 2025-11-25 | Vanke seeks its **first-ever onshore bond payment extension**; bonds slump amid mounting doubt over the durability of state support | [US News/Reuters](https://money.usnews.com/investing/news/articles/2025-11-25/china-vanke-bonds-slump-as-concerns-mount-over-state-support) |
| 2025-11-28 | S&P's **second** downgrade inside a month, CCC → CCC-; flags ~RMB 11.4bn of bonds due Dec 2025–May 2026 and expected negative operating cash flow over the next 6 months | [SCMP](https://www.scmp.com/business/china-business/article/3334541/china-vanke-hit-fresh-sp-downgrade-amid-mounting-default-concerns) |
| **2025-12-12** | **DTD sample window closes** (DTD = 1.36) | vanke.xlsx |
| 2025-12-14 *(2 days after window closes)* | Holders reject a one-year extension on a RMB 2bn medium-term note (76.7% against a required 90% approval); 5-business-day grace period begins | [MarketScreener](https://uk.marketscreener.com/news/china-vanke-bondholders-reject-payment-extension-raising-default-risk-ce7d50d8df80fe26) |

## 3. DTD vs. reality: six phases

I split the series into six stretches that behave differently against the timeline above.

**Phase 1 — Dec 2023 to early Sep 2024: slow, orderly decline (DTD 1.57 → ~0.9).**
DTD drifts down steadily through both rating downgrades. It does *not* spike on the exact announcement dates — around 2024-03-11 it is still ~1.4–1.6, in the same band it had occupied since December; around 2024-04-11 it has already fallen to ~0.87–0.91, having started dropping in late March, a few days *before* the S&P action. Read charitably, DTD in this phase behaves as a slow-moving fundamental gauge that trended the right direction alongside the rating actions rather than reacting sharply to either announcement on the day.

**Phase 2 — late Sep to late Oct 2024: a market-wide noise spike, not a Vanke signal.**
DTD jumps from 1.02 (Sep 19) to 1.62 (Sep 27) in six trading days, then reverses just as fast, falling to 0.58 by Oct 8 and 0.27 by Oct 25. This lines up exactly with the "9·24" nationwide stimulus rally that lifted Chinese equities broadly (Vanke A-shares hit limit-up). Nothing about Vanke's own credit standing changed in that window — this is a textbook case of market-wide beta showing up in a firm-specific credit signal, and it should be treated as **noise**, not information.

**Phase 3 — Nov 2024 to Jan 2025: the real trough, and DTD gets there too.**
DTD keeps falling after the Phase-2 reversal, through 0.27–0.4 in Q4 2024, down to a series low around 2025-01-21/22 (0.025 – 0.063, with the series minimum of -0.031 nearby) — landing almost exactly on the week of the management reshuffle and RMB 45bn loss disclosure (2025-01-27). This is the strongest coincidence in the whole window: the operational and market crisis and the model's own floor arrive together. The one blemish is the missing value on 2025-01-28 — the pipeline goes dark the day after the event it should be most useful for.

**Phase 4 — Feb to Sep 2025: eight months of a muted, flat-lined signal (DTD 0.0–0.3).**
For roughly eight months DTD barely moves off the floor, while the real story in the background was a series of Shenzhen Metro "blood transfusion" loans (reported around RMB 120bn across four rounds) keeping Vanke current on obligations. DTD in this stretch reads as "still distressed" but gives very little information about *direction* — it neither confirms things are stabilizing nor flags the specific deterioration that would culminate in November.

**Phase 5 — Oct to late Nov 2025: DTD rises to a two-year high while the real situation is breaking down. This is the counter-intuitive part.**
DTD climbs from ~0.65 (early Oct) to a peak around 1.81 (Nov 20-21) — its best reading since March 2024. This rise runs *through* the Nov 3 rescue-loan tightening (DTD = 1.76 that day) and is still elevated on Nov 25, the day Vanke seeks its first-ever onshore bond extension (DTD = 1.75). In other words: at the exact moments its own controlling shareholder was hardening rescue terms and Vanke was asking bondholders for relief for the first time, the model's own default-distance reading said Vanke was safer than at almost any point in nearly two years.

**Phase 6 — late Nov to Dec 12, 2025: DTD turns down, but only after the news does, and the window ends before the real climax.**
DTD peaks Nov 20-21 and begins falling only after the Nov 25 extension request, dropping to 1.48 by Nov 28 (S&P's second downgrade) and 1.36 by the window's close on Dec 12. It is heading the right direction by the end of the sample, but the sample stops two days before bondholders actually reject the RMB 2bn extension (Dec 14) — the event that arguably matters most is just outside the data we were given.

## 4. Answering the reflection questions directly

**Does DTD anticipate, coincide with, or lag the observed distress?**
All three, at different times, which is itself the finding. It roughly *coincides* with the slow 2024 deterioration (Phase 1) and *lands almost exactly on* the January 2025 trough (Phase 3) — its best showing. But heading into the actual near-default event, it clearly *lags*: it was rising through the early-warning signs in Phase 5 (a controlling shareholder tightening terms is about as strong an insider signal as exists) and only turned down after the bond-extension request became public — and even then, the window closes before the actual bondholder rejection. If I had to rank the leading indicators in this case study by timeliness, the shareholder's own change in lending terms (Nov 3) came before the S&P downgrade (Nov 28), which came before DTD's turn (also ~Nov 25-28) — DTD was not the earliest signal here.

**Are there periods where the signal is noisy, muted, or counter-intuitive?**
Yes, one clean example of each: Phase 2 (Sep-Oct 2024) is **noisy** — a market-wide rally masquerading as firm-specific credit improvement. Phase 4 (Feb-Sep 2025) is **muted** — eight months near the floor with little directional content while the underlying support arrangement was actively evolving. Phase 5 (Oct-Nov 2025) is **counter-intuitive** — DTD improving sharply while the controlling shareholder was visibly pulling back support, which is the most concerning of the three because it is the one most likely to mislead a reader into complacency right before the event that mattered.

## 5. Why might Phase 5 have happened? (revisited with CRI's own documentation)

- **The "double-jump" σ artifact (Addendum 1) can almost be ruled out.** That specific mechanism — monthly σ calibration lagging a market-cap move, producing a spurious jump-then-correction — was fixed in September 2020, more than three years before this DTD window opens. Throughout our entire Dec 2023–Dec 2025 sample, σ should already be calibrated daily, so this exact bug doesn't apply here.
- **A δ-smoothing artifact (Addendum 4) is possible but seems unlikely to be primary.** That mechanism depends on the number of comparable firms in Vanke's CRI calibration-group-sector hovering near a 10-firm threshold; China's real-estate sector, within CRI's global coverage, almost certainly has well above 10 firms, so the specific group-proxy-switching behavior Addendum 4 describes is a less likely driver here than it might be for a firm in a thinly covered sector or a small economy.
- **The ~2-year MLE estimation window (Addendum 8, corroborated by the wording in Addendum 4) remains the most plausible mechanical explanation, and the dates line up.** If σ — and the underlying implied-asset-value path used to estimate it — is estimated over a rolling window on the order of two years, then two episodes of extreme daily equity-return moves — the October 2023 rumor-driven crash (just before this window opens) and the September–October 2024 "9·24" stimulus spike-and-reversal (Phase 2, §3) — would sit inside that trailing window through most of 2024 and 2025, mechanically keeping estimated asset volatility elevated (and DTD depressed) until those episodes roll out of a ~2-year lookback. Both would start rolling out of a 2-year window around September–October 2025, close to when DTD begins its climb (§3, Phase 5).
- Two non-exclusive, fundamentals-based contributors remain plausible alongside the estimation-window story: total liabilities fell by roughly 30% in absolute terms over the two-year window (presumably mostly forced asset disposals under the Shenzhen-Metro-backed restructuring rather than organic deleveraging), and the market may have been pricing in continued implicit state support for most of 2025 (market cap held in a fairly narrow band rather than collapsing) until the shareholder's own November 2025 tightening of rescue-loan terms shook that assumption.

## 6. Limitations of this reflection

- The three CRI addenda referenced in §1 and §5 document specific parameter-calibration changes; I did not obtain the base Technical Report itself, so the exact estimation-window length, Vanke's specific CRI calibration-group-sector composition, and the DTD→PD mapping methodology are inferred or unconfirmed rather than directly documented.
- Event dates are drawn from news-reported dates, which are not always the date the market first had the information (rumors, leaks, and selective disclosure routinely precede formal announcements in this case, e.g. the Oct 2023 rumor cycle).
- This is one company in one sector (Chinese state-adjacent real estate) going through a state-managed restructuring rather than a clean market default — the "implicit support" dynamic that plausibly drove Phase 5 is, to some extent, sector- and situation-specific.

## Sources

**News and event timeline:**
- [China Vanke bondholders reject payment extension, raising default risk – MarketScreener](https://uk.marketscreener.com/news/china-vanke-bondholders-reject-payment-extension-raising-default-risk-ce7d50d8df80fe26)
- [Moody's Cancels China Vanke Issuer Rating, Downgrades Bonds – Mingtiandi](https://www.mingtiandi.com/real-estate/finance/moodys-cancels-china-vanke-issuer-rating-downgrades-bonds/)
- [China Vanke hit with fresh S&P downgrade amid mounting default concerns – SCMP](https://www.scmp.com/business/china-business/article/3334541/china-vanke-hit-fresh-sp-downgrade-amid-mounting-default-concerns)
- [China Vanke shares, bonds fall after rating cut and government probe – Yahoo Finance](https://finance.yahoo.com/news/china-vanke-shares-bonds-fall-093702212.html)
- [万科大消息！深圳国资委发声 – 中国基金报](https://www.chnfund.com/article/AR2023110618095550109416)
- [突发！郁亮辞去万科所有职务 – 澎湃新闻](https://m.thepaper.cn/newsDetail_forward_32345333)
- [多方积极支持 万科发展迎来重大转机 深圳国资：有足够"子弹"支持万科 – 深圳新闻网](https://www.sznews.com/news/content/2025-01/27/content_31453012.htm)
- [Vanke bonds plunge as biggest backer tightens rescue loan terms – Bloomberg](https://www.bloomberg.com/news/articles/2025-11-03/vanke-bonds-plunge-as-biggest-backer-tightens-rescue-loan-terms)
- [China Vanke bonds slump as concerns mount over state support – US News/Reuters](https://money.usnews.com/investing/news/articles/2025-11-25/china-vanke-bonds-slump-as-concerns-mount-over-state-support)
- ["9·24"行情满月 – 北京商报](https://www.bbtnews.com.cn/2024/1024/534382.shtml)
- [重磅政策刺激地产股连续上涨 – 新浪财经](https://finance.sina.com.cn/roll/2024-09-25/doc-incqknpk5036713.shtml)
- CRI public site (context, optional per task brief): [nuscri.org](https://nuscri.org/en/)

**CRI methodology documents:**
- Credit Research Initiative, "Addendum 8 to the CRI Technical Report (Version: 2012, Update 2) — Changes to Distance-to-Default (DTD) computation," published 15 May 2013.
- Credit Research Initiative, "Addendum 1 to the CRI Technical Report (Version: 2020, Update 1) — Increase the updating frequency for one DTD parameter from monthly to daily," published 14 Sep 2020.
- Credit Research Initiative, "Addendum 4 to the CRI Technical Report (Version: 2021, Update 1) — Stabilizing treatment for the weight parameter δ," published 11 May 2022.
