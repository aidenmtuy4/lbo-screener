"""
LBO Project -- add market caps to prescreened.csv (no installs needed).

Market cap = shares outstanding (from the company's latest SEC filing)
             x current share price (from Yahoo Finance's public chart data)

Put this file in the same folder as prescreened.csv, set YOUR_EMAIL, press F5.
Takes ~4-6 minutes for ~1,000 companies. Overwrites prescreened.csv with two
new columns: price, shares_out, market_cap.
"""

import os
import time
import requests
import pandas as pd

os.chdir(os.path.dirname(os.path.abspath(__file__)))

YOUR_EMAIL = "your.name@example.com"   # <-- change this (SEC requirement)
SEC_HEADERS = {"User-Agent": f"UTampa student LBO project {YOUR_EMAIL}"}
WEB_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def shares_outstanding(cik):
    """Latest shares outstanding from the cover page of the company's SEC filings.
    Companies with several share classes report one number per class -- we add them up."""
    url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{int(cik):010d}/dei/EntityCommonStockSharesOutstanding.json"
    time.sleep(0.12)
    r = requests.get(url, headers=SEC_HEADERS, timeout=30)
    if r.status_code != 200:
        return None
    facts = r.json().get("units", {}).get("shares", [])
    if not facts:
        return None
    latest_end = max(f["end"] for f in facts)
    latest = [f for f in facts if f["end"] == latest_end]
    # if the same class was reported twice for that date, keep one value per filing
    latest_filing = max(f["accn"] for f in latest)
    return sum(f["val"] for f in latest if f["accn"] == latest_filing)


def share_price(ticker):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.replace('.', '-')}?range=5d&interval=1d"
    try:
        r = requests.get(url, headers=WEB_HEADERS, timeout=15)
        return r.json()["chart"]["result"][0]["meta"]["regularMarketPrice"]
    except Exception:
        return None


if __name__ == "__main__":
    if "example.com" in YOUR_EMAIL:
        raise SystemExit("Put your email in YOUR_EMAIL at the top of the script first.")
    df = pd.read_csv("prescreened.csv")
    df = df[df["ticker"].notna()].reset_index(drop=True)
    print(f"Getting market data for {len(df):,} companies...")
    prices, shares = [], []
    for i, row in df.iterrows():
        prices.append(share_price(row["ticker"]))
        shares.append(shares_outstanding(row["cik"]))
        if (i + 1) % 50 == 0:
            print(f"    {i + 1}/{len(df)}")
    df["price"] = prices
    df["shares_out"] = shares
    df["market_cap"] = df["price"] * df["shares_out"]
    df.to_csv("prescreened.csv", index=False)
    ok = df["market_cap"].notna().sum()
    print(f"\nDone. Market cap found for {ok:,} of {len(df):,} companies.")
    if ok == 0:
        print("No prices came back -- send Claude a screenshot.")
