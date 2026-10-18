"""
LBO engine: a simplified but standard 5-year leveraged buyout model.

Given one company's financials and market cap, it answers the PE question:
"If we bought this company today at a normal takeover premium with typical
leverage, what return would we earn over 5 years?"
"""

from dataclasses import dataclass, asdict


@dataclass
class Assumptions:
    premium: float = 0.30            # takeover premium over current share price
    fees_pct: float = 0.02           # banking/financing fees, % of enterprise value
    total_leverage: float = 5.0      # total debt / EBITDA at entry
    tlb_share: float = 0.70          # share of debt that is the Term Loan B
    tlb_rate: float = 0.0775         # Term Loan B interest (SOFR + ~350bp)
    notes_rate: float = 0.0900       # senior notes interest
    tlb_amort: float = 0.01          # mandatory annual TLB repayment, % of original
    sweep: float = 1.00              # % of excess cash used to repay the TLB early
    min_interest_cover: float = 2.0  # EBITDA / interest must be >= this at entry
    min_equity_pct: float = 0.40     # lenders require the sponsor to fund >= 40% with equity
    tax_rate: float = 0.25
    nwc_pct_of_rev_change: float = 0.10  # working capital tied up by revenue growth
    growth_floor: float = 0.00
    growth_cap: float = 0.08
    exit_multiple_delta: float = 0.0 # exit EV/EBITDA minus entry (0 = no multiple expansion)
    years: int = 5


def run_lbo(c, a=Assumptions()):
    """
    c: dict with revenue, revenue_prior, ebitda, d_and_a, capex, debt, cash, market_cap
    Returns a dict of results, or None if the deal doesn't work.
    """
    rev0, ebitda0 = c["revenue"], c["ebitda"]
    if ebitda0 <= 0 or not c.get("market_cap"):
        return None

    # ---- Entry ---------------------------------------------------------------
    net_debt = c["debt"] - c["cash"]
    purchase_equity = c["market_cap"] * (1 + a.premium)
    entry_ev = purchase_equity + net_debt
    entry_multiple = entry_ev / ebitda0

    # Debt: target leverage, but cut it if interest would be too heavy
    blended_rate = a.tlb_share * a.tlb_rate + (1 - a.tlb_share) * a.notes_rate
    max_debt_by_cover = ebitda0 / (a.min_interest_cover * blended_rate)
    uses = entry_ev + a.fees_pct * entry_ev   # refinance existing net debt + buy equity + fees
    max_debt_by_equity = uses * (1 - a.min_equity_pct)
    total_debt = min(a.total_leverage * ebitda0, max_debt_by_cover, max_debt_by_equity)
    tlb0 = total_debt * a.tlb_share
    notes0 = total_debt - tlb0

    sponsor_equity = uses - total_debt
    if sponsor_equity <= 0:
        return None

    # ---- Projections -----------------------------------------------------------
    hist_growth = c["revenue"] / c["revenue_prior"] - 1 if c.get("revenue_prior") else 0.03
    g = min(max(hist_growth, a.growth_floor), a.growth_cap)
    margin = ebitda0 / rev0
    da_pct = c["d_and_a"] / rev0
    capex_pct = c["capex"] / rev0

    tlb, notes, rev = tlb0, notes0, rev0
    schedule = []
    for yr in range(1, a.years + 1):
        new_rev = rev * (1 + g)
        ebitda = new_rev * margin
        interest = tlb * a.tlb_rate + notes * a.notes_rate
        ebt = ebitda - new_rev * da_pct - interest
        taxes = max(ebt, 0) * a.tax_rate
        capex = new_rev * capex_pct
        d_nwc = (new_rev - rev) * a.nwc_pct_of_rev_change
        fcf = ebitda - interest - taxes - capex - d_nwc      # levered free cash flow

        mandatory = min(tlb0 * a.tlb_amort, tlb)
        optional = min(max(fcf - mandatory, 0) * a.sweep, tlb - mandatory)
        tlb -= mandatory + optional
        schedule.append(dict(year=yr, revenue=new_rev, ebitda=ebitda, interest=interest,
                             taxes=taxes, capex=capex, fcf=fcf, debt_paydown=mandatory + optional,
                             tlb=tlb, notes=notes, leverage=(tlb + notes) / ebitda))
        rev = new_rev

    # ---- Exit -------------------------------------------------------------------
    exit_multiple = entry_multiple + a.exit_multiple_delta
    exit_ebitda = schedule[-1]["ebitda"]
    exit_ev = exit_ebitda * exit_multiple
    # cash left after the sweep stays in the company and goes to equity at exit
    cash_build = sum(s["fcf"] - s["debt_paydown"] for s in schedule)
    exit_equity = exit_ev - (tlb + notes) + cash_build
    moic = exit_equity / sponsor_equity
    irr = moic ** (1 / a.years) - 1 if moic > 0 else -1.0

    return dict(
        entry_ev=entry_ev, entry_multiple=entry_multiple, purchase_equity=purchase_equity,
        total_debt=total_debt, entry_leverage=total_debt / ebitda0,
        sponsor_equity=sponsor_equity, equity_pct=sponsor_equity / uses,
        growth=g, ebitda_margin=margin,
        exit_ev=exit_ev, exit_equity=exit_equity, exit_leverage=(tlb + notes) / exit_ebitda,
        pct_debt_repaid=1 - (tlb + notes) / total_debt,
        moic=moic, irr=irr, schedule=schedule,
    )


def sensitivity(c, a=Assumptions()):
    """IRR grid: exit multiple change (rows) x entry premium (columns)."""
    grid = {}
    for dm in (-2.0, -1.0, 0.0, 1.0):
        row = {}
        for prem in (0.20, 0.30, 0.40):
            r = run_lbo(c, Assumptions(**{**asdict(a), "exit_multiple_delta": dm, "premium": prem}))
            row[f"{prem:.0%} premium"] = r["irr"] if r else None
        grid[f"exit {dm:+.0f}x"] = row
    return grid
