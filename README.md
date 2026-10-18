# Take-Private Screener + Automated LBO Engine

A Python pipeline that screens **every US public company** for leveraged buyout potential, runs an LBO on each candidate, and ranks them by projected private equity returns. The #1 candidate, **Stride, Inc. (NYSE: LRN)**, is then modeled in a full, formula-driven Excel LBO with an investment memo.

**Result:** 6,154 SEC filers → 107 qualified candidates → Stride ranked #1. The detailed model shows an **18.1% IRR / 2.30x MOIC** base case at a 30% takeover premium, rising to 21–23% with modest margin improvement.

---

## How it works

```
SEC EDGAR XBRL API ──► fetch_data.py ──► market_data.py ──► screen_and_rank.py ──► Stride_LBO_Model.xlsx
 (6,154 companies)      financials +       share price ×       10 filters +           full model +
                        industry codes     shares outstanding  LBO on survivors       investment memo
```

| Step | File | What it does |
|---|---|---|
| 1 | `fetch_data.py` | Pulls FY2025 and FY2024 financials for every SEC filer from the free EDGAR XBRL "frames" API. It tries several XBRL tags per line item, because companies label things differently. |
| 2 | `market_data.py` | Market cap = shares outstanding from each company's latest SEC cover page × current share price. |
| 3 | `screen_and_rank.py` | Applies the screen, applies hand-verified data corrections from `manual_adjustments.csv`, runs the LBO engine on every survivor, and ranks them by IRR. |
| 4 | `lbo_engine.py` | A 5-year LBO: entry at a takeover premium, debt sized by three lender constraints, cash sweep, exit, IRR/MOIC. |
| 5 | `build_excel.py` | Generates `Stride_LBO_Model.xlsx`: 241 live formulas, sources & uses, debt schedule, returns, and a sensitivity grid. |

## The screen

| Filter | Why a PE firm cares | Companies left |
|---|---|---|
| FY2025 XBRL financials | Universe | 6,154 |
| Loose pre-screen | Limits API calls | 1,034 |
| Listed on NYSE / Nasdaq | Liquid, real public company | 940 |
| Debt data complete | Can't price a deal with unknown debt | 896 |
| Exclude financials, utilities, oil & gas, shipping, LPs | EBITDA-based LBO math doesn't apply, or earnings are commodity-driven | 707 |
| Market cap ≥ $250M | Big enough for institutional PE | 570 |
| EBITDA $50M–$1B | Financeable in the leveraged-loan market | 457 |
| EBITDA margin ≥ 15% | Healthy, defensible business | 263 |
| FCF ≥ 40% of EBITDA | Cash actually shows up to repay debt | 216 |
| Net debt ≤ 2.0x EBITDA | Room to add LBO debt | 159 |
| Revenue growth −5% to +40% | Not in decline; not a one-off spike | 133 |
| Profitable both years, EBIT not spiking | Stable, repeatable earnings | **107** |

## LBO engine assumptions

- **Entry:** 30% premium to current share price, 2% transaction fees
- **Debt:** the *smallest* of 5.0x EBITDA, 60% of the funding need (sponsor funds ≥ 40% equity), or the amount that keeps EBITDA/interest ≥ 2.0x
- **Structure:** 70% Term Loan B (7.75%, 1% amortization), 30% senior notes (9.0%)
- **Operations:** revenue growth = last year's growth, capped at 0–8%; margins held flat
- **Exit:** year 5 at the entry multiple, so no multiple expansion is assumed

## Data quality: what I found and fixed

Automated screens break on messy data, and catching that is part of the work. The first ranking had companies with 100%+ IRRs. Investigating them surfaced five problems:

1. **Model flaw:** at low entry multiples, 5x debt covered almost the whole purchase price, so the sponsor equity went to near zero and the IRR exploded. **Fix:** a 40% minimum equity rule, matching what lenders require.
2. **Capex reported as $0** because companies used a tag I didn't pull. **Fix:** use D&A as a maintenance-capex proxy.
3. **Missing debt:** RH (~$2.4B) and Collegium (~$1.1B) carry debt the pulled tags missed. **Fix:** excluded after checking filings; logged in `manual_adjustments.csv` with sources.
4. **One-off earnings:** biotech and energy names that swung from losses to large profits. **Fix:** stability filters and industry exclusions.
5. **Partnerships:** Westlake Chemical Partners consolidates a business it only partly owns, which overstates its EBITDA. **Fix:** LPs excluded.

## Top 10 candidates

| Rank | Company | Ticker | Entry EV/EBITDA | IRR |
|---|---|---|---|---|
| 1 | Stride | LRN | 9.2x | 22.8% |
| 2 | MiMedx Group | MDXG | 8.8x | 20.9% |
| 3 | NICE Ltd. | NICE | 10.0x | 20.3% |
| 4 | Innoviva | INVA | 10.1x | 20.0% |
| 5 | Yelp | YELP | 6.0x | 19.1% |
| 6 | Gentex | GNTX | 9.7x | 18.9% |
| 7 | Harmony Biosciences | HRMY | 11.0x | 18.5% |
| 8 | Perdoceo Education | PRDO | 11.1x | 16.9% |
| 9 | Korn Ferry | KFY | 9.8x | 16.1% |
| 10 | Bristow Group | VTOL | 8.2x | 16.1% |

Screen-level figures use FY2025 data. The detailed Stride model uses FY2026 actuals and is more conservative: it keeps $100M of cash in the business and the 40% equity rule binds. That produces the 18.1% IRR, and the gap between the two is explained in the memo.

## Stride deal summary

| | |
|---|---|
| Offer price | $107.11 per share (30% premium) |
| Entry EV / EBITDA | 7.0x |
| New debt | $2.53B (4.4x EBITDA) |
| Sponsor equity | $1.68B (40%) |
| Debt / EBITDA at exit | 1.5x |
| **IRR / MOIC** | **18.1% / 2.30x** |

## Run it yourself

```bash
pip install pandas requests openpyxl
python fetch_data.py        # set YOUR_EMAIL first (SEC requirement)
python market_data.py
python screen_and_rank.py
python build_excel.py
```

## Limitations

- XBRL tag coverage is imperfect. Top candidates were verified by hand, but the full list was not.
- GAAP EBITDA is used, with no stock-comp add-back. That is conservative, but different from how sponsors and lenders usually quote EBITDA.
- The screen-level engine is simplified: no transaction-specific debt terms, no management rollover, no interim dividends.
- Educational project built from public data. Not investment advice.
