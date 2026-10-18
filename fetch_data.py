"""
LBO Project -- data pull. Run this ONCE in Spyder (F5). Takes ~2-4 minutes.

It downloads:
  1. FY2025 + FY2024 financials for every US public company (SEC EDGAR)
  2. Ticker, industry code and exchange for companies that pass a loose pre-screen
  3. Current share price + market cap (Yahoo Finance via yfinance)

Output (saved next to this script):
  raw_financials.csv     -- everything
  prescreened.csv        -- loose pre-screen with ticker, industry and market cap
"""

import os
import time
import requests
import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))  # save files next to this script

# The SEC requires a contact email in every request. Any email of yours works.
YOUR_EMAIL = "your.name@example.com"   # <-- change this (SEC requirement)
HEADERS = {"User-Agent": f"UTampa student LBO project {YOUR_EMAIL}"}

YEAR = 2025          # latest full fiscal year
PRIOR = YEAR - 1     # used to check growth / stability

# Each item: list of XBRL tags tried in order, and whether it's a full-year
# figure ("duration") or a balance-sheet snapshot ("instant").
ITEMS = {
    "revenue":  (["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                  "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"], "duration"),
    "ebit":     (["OperatingIncomeLoss"], "duration"),
    "d_and_a":  (["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                  "DepreciationAmortizationAndAccretionNet", "Depreciation"], "duration"),
    "cfo":      (["NetCashProvidedByUsedInOperatingActivities"], "duration"),
    "capex":    (["PaymentsToAcquirePropertyPlantAndEquipment"], "duration"),
    "interest": (["InterestExpense", "InterestExpenseNonoperating"], "duration"),
    "debt":     (["LongTermDebt", "LongTermDebtAndCapitalLeaseObligations",
                  "LongTermDebtNoncurrent"], "instant"),
    "cash":     (["CashAndCashEquivalentsAtCarryingValue"], "instant"),
}
PRIOR_ITEMS = ["revenue", "ebit"]


def get(url):
    time.sleep(0.12)  # SEC limit is 10 requests/second
    return requests.get(url, headers=HEADERS, timeout=30)


def fetch_frame(tag, period):
    r = get(f"https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/{period}.json")
    if r.status_code != 200:
        print(f"    {tag} {period}: none (HTTP {r.status_code})")
        return pd.DataFrame(columns=["cik", "name", "value"])
    df = pd.DataFrame(r.json()["data"])
    print(f"    {tag} {period}: {len(df):,} companies")
    return df[["cik", "entityName", "val"]].rename(columns={"entityName": "name", "val": "value"})


def fetch_item(tags, kind, year):
    period = f"CY{year}" if kind == "duration" else f"CY{year}Q4I"
    combined = pd.concat([fetch_frame(t, period) for t in tags])
    return combined.drop_duplicates(subset="cik", keep="first")


def build_dataset():
    print(f"Step 1/3: SEC financials (FY{YEAR}, FY{PRIOR})")
    pulled = {item: fetch_item(tags, kind, YEAR) for item, (tags, kind) in ITEMS.items()}
    names = pd.concat(pulled.values())[["cik", "name"]].drop_duplicates(subset="cik")
    data = names
    for item, df in pulled.items():
        data = data.merge(df[["cik", "value"]].rename(columns={"value": item}), on="cik", how="left")
    for item in PRIOR_ITEMS:
        tags, kind = ITEMS[item]
        df = fetch_item(tags, kind, PRIOR).rename(columns={"value": f"{item}_prior"})
        data = data.merge(df.drop(columns="name"), on="cik", how="left")
    return data


def loose_prescreen(data):
    """Deliberately loose -- the real screen happens later. This just limits API calls."""
    df = data.copy()
    num_cols = [c for c in df.columns if c not in ("cik", "name")]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce").astype(float)
    df = df.dropna(subset=["revenue", "ebit", "cfo"])
    df = df[df["revenue"] > 0]   # some filers report zero revenue -- skip them
    df["d_and_a"] = df["d_and_a"].fillna(0)
    df["capex"] = df["capex"].fillna(0)
    df["ebitda"] = df["ebit"] + df["d_and_a"]
    df["fcf"] = df["cfo"] - df["capex"]
    keep = df[df["ebitda"].between(25e6, 2e9) & (df["fcf"] > 0) & (df["ebitda"] / df["revenue"] > 0.08)]
    return keep.copy()


def add_company_info(df):
    print(f"\nStep 2/3: ticker + industry for {len(df):,} companies")
    rows = []
    for i, cik in enumerate(df["cik"], 1):
        r = get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
        if r.status_code == 200:
            j = r.json()
            rows.append({"cik": cik,
                         "ticker": (j.get("tickers") or [None])[0],
                         "exchange": (j.get("exchanges") or [None])[0],
                         "sic": j.get("sic"),
                         "industry": j.get("sicDescription"),
                         "state": j.get("stateOfIncorporation"),
                         "fiscal_year_end": j.get("fiscalYearEnd")})
        if i % 50 == 0:
            print(f"    {i}/{len(df)}")
    return df.merge(pd.DataFrame(rows), on="cik", how="left")


def add_market_data(df):
    print("\nStep 3/3: share prices + market caps")
    try:
        import yfinance as yf
    except ImportError:
        print("    yfinance not installed -- skipping. In the Spyder console run:  %pip install yfinance")
        return df
    caps, prices = {}, {}
    tickers = df["ticker"].dropna().unique()
    for i, t in enumerate(tickers, 1):
        try:
            fi = yf.Ticker(t.replace(".", "-")).fast_info
            caps[t], prices[t] = fi["market_cap"], fi["last_price"]
        except Exception:
            pass
        if i % 50 == 0:
            print(f"    {i}/{len(tickers)}")
    df["market_cap"] = df["ticker"].map(caps)
    df["price"] = df["ticker"].map(prices)
    print(f"    got market data for {len(caps):,} of {len(tickers):,} tickers")
    return df


if __name__ == "__main__":
    if "example.com" in YOUR_EMAIL:
        raise SystemExit("Put your email in YOUR_EMAIL at the top of the script first.")
    if os.path.exists("raw_financials.csv"):
        print("Step 1/3: using raw_financials.csv already downloaded")
        raw = pd.read_csv("raw_financials.csv")
    else:
        raw = build_dataset()
        raw.to_csv("raw_financials.csv", index=False)
    pre = add_market_data(add_company_info(loose_prescreen(raw)))
    pre.to_csv("prescreened.csv", index=False)
    print(f"\nDone. {len(raw):,} companies in raw_financials.csv, "
          f"{len(pre):,} in prescreened.csv")
