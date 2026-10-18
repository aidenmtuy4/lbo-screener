"""
Step 2: apply the real LBO screen to prescreened.csv, run the LBO engine on every
survivor, and rank them by IRR.  Output: ranked_candidates.csv, top25.csv
"""

import sys
import pandas as pd
from lbo_engine import run_lbo, Assumptions

# ---- Screening criteria (each one is something a PE associate would check) ----
MIN_EBITDA, MAX_EBITDA = 50e6, 1e9   # big enough to matter, small enough to finance
MIN_MARGIN = 0.15                    # healthy, defensible business
MIN_FCF_CONV = 0.40                  # EBITDA actually turns into cash
MAX_NET_LEVERAGE = 2.0               # room to add LBO debt
MIN_GROWTH = -0.05                   # not in steep decline
MIN_MARKET_CAP = 250e6               # real, liquid public company
# Industries where EBITDA-based LBO math doesn't apply (SIC code ranges)
MAX_GROWTH = 0.40                    # >40% one-year growth = likely a one-off, not a run-rate
EXCLUDE_SIC = [(6000, 6799, "Financials / insurance / real estate"),
               (4900, 4999, "Regulated utilities"),
               (1300, 1389, "Oil & gas producers (commodity-driven earnings)"),
               (4400, 4499, "Shipping (asset-heavy, cyclical)")]
OK_EXCHANGES = {"NYSE", "Nasdaq", "NYSE American", "NYSE MKT", "NYSEArca"}


def apply_manual_adjustments(df, path="manual_adjustments.csv"):
    """Corrections verified by hand against company filings (see the source column)."""
    import os
    df = df.copy()
    df["manually_verified"] = False
    if not os.path.exists(path):
        return df
    adj = pd.read_csv(path)
    for _, a in adj.iterrows():
        m = df["ticker"] == a["ticker"]
        if a["action"] == "exclude":
            df = df[~m]
        elif a["action"] == "set":
            df.loc[m, a["field"]] = float(a["value"])
            df.loc[m, "manually_verified"] = True
    return df


def screen(df):
    df = apply_manual_adjustments(df)
    # Partnerships (LPs) often consolidate businesses they only partly own -> EBITDA overstated
    df = df[~df["name"].str.contains(r"\bL\.?P\.?$", case=False, regex=True)]
    # Debt missing but interest being paid = the debt is tagged under a name we didn't pull.
    df["debt_missing"] = df["debt"].isna() & (df["interest"].fillna(0) > 0)
    # Capex of 0 almost always means a different XBRL tag; use D&A as the maintenance-capex proxy.
    df["capex_estimated"] = df["capex"].fillna(0) <= 0
    df.loc[df["capex_estimated"], "capex"] = df.loc[df["capex_estimated"], "d_and_a"]
    for col in ["d_and_a", "capex", "debt", "cash", "interest"]:
        df[col] = df[col].fillna(0)
    df["ebitda"] = df["ebit"] + df["d_and_a"]
    df["margin"] = df["ebitda"] / df["revenue"]
    df["fcf"] = df["cfo"] - df["capex"]
    df["fcf_conv"] = df["fcf"] / df["ebitda"]
    df["net_debt"] = df["debt"] - df["cash"]
    df["net_leverage"] = df["net_debt"] / df["ebitda"]
    df["growth"] = df["revenue"] / df["revenue_prior"] - 1

    steps = [
        ("listed on a major US exchange", df["exchange"].isin(OK_EXCHANGES)),
        ("debt data complete", ~df["debt_missing"]),
        ("stable industry (ex. financials, utilities, oil & gas, shipping)", ~df["sic"].apply(
            lambda s: any(lo <= float(s) <= hi for lo, hi, _ in EXCLUDE_SIC) if pd.notna(s) and str(s).strip() else False)),
        ("has market cap >= $250M", df["market_cap"].fillna(0) >= MIN_MARKET_CAP),
        ("EBITDA $50M-$1B", df["ebitda"].between(MIN_EBITDA, MAX_EBITDA)),
        ("EBITDA margin >= 15%", df["margin"] >= MIN_MARGIN),
        ("FCF conversion >= 40%", df["fcf_conv"] >= MIN_FCF_CONV),
        ("net leverage <= 2.0x", df["net_leverage"] <= MAX_NET_LEVERAGE),
        ("revenue growth between -5% and +40%", df["growth"].between(MIN_GROWTH, MAX_GROWTH)),
        ("profitable last year too", df["ebit_prior"] > 0),
        ("EBIT not spiking (< +50% vs last year)", df["ebit"] / df["ebit_prior"] < 1.5),
    ]
    mask = pd.Series(True, index=df.index)
    funnel = [("starting universe", len(df))]
    for label, cond in steps:
        mask &= cond
        funnel.append((label, int(mask.sum())))
    return df[mask], funnel


def rank(passed, a=Assumptions()):
    rows = []
    for _, c in passed.iterrows():
        r = run_lbo(c.to_dict(), a)
        if r:
            rows.append({**{k: c[k] for k in ["name", "ticker", "industry", "market_cap", "revenue",
                                                "ebitda", "margin", "fcf_conv", "net_leverage", "growth"]},
                         **{k: r[k] for k in ["entry_multiple", "entry_ev", "entry_leverage",
                                                "equity_pct", "pct_debt_repaid", "moic", "irr"]}})
    return pd.DataFrame(rows).sort_values("irr", ascending=False).reset_index(drop=True)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "prescreened.csv"
    df = pd.read_csv(path)
    passed, funnel = screen(df)
    print("Screening funnel:")
    for label, n in funnel:
        print(f"  {label:66s} {n:>5,}")
    ranked = rank(passed)
    ranked.to_csv("ranked_candidates.csv", index=False)
    ranked.head(25).to_csv("top25.csv", index=False)
    show = ranked.head(25)[["name", "ticker", "entry_multiple", "entry_leverage", "moic", "irr", "equity_pct"]]
    print(show.to_string(formatters={"entry_multiple": "{:.1f}x".format, "entry_leverage": "{:.1f}x".format,
                                     "moic": "{:.2f}x".format, "irr": "{:.1%}".format, "equity_pct": "{:.0%}".format}))
