"""
run_subperiods.py — is the edge real, or just the post-COVID bull run?

Runs the full backtest ONCE over the whole history, then slices the resulting
equity curve into windows and compares the strategy against the Nifty 500 in
each. If the strategy only beats the index in one lucky window, you'll see it
here. If it beats it across most periods, that's a far stronger signal.

    python run_subperiods.py            # full Nifty 500
    python run_subperiods.py --starter  # quick starter universe

Boundaries are objective (calendar years + equal thirds of the date range) so
no judgement calls about "where COVID started" are baked into the numbers.
"""
import sys
import numpy as np
import pandas as pd
import config as C
import data, backtest as bt
import universe as U


def _stats(eq):
    """total return, CAGR, ann vol, Sharpe, max drawdown for an equity slice."""
    eq = eq.dropna()
    r = eq.pct_change().dropna()
    n = len(r)
    if n < 2 or eq.iloc[0] <= 0:
        return dict(tot=np.nan, cagr=np.nan, vol=np.nan, sharpe=np.nan, mdd=np.nan)
    tot = eq.iloc[-1] / eq.iloc[0] - 1.0
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (252.0 / n) - 1.0
    vol = r.std() * np.sqrt(252)
    sharpe = (r.mean() * 252) / vol if vol > 0 else np.nan
    mdd = (eq / eq.cummax() - 1.0).min()
    return dict(tot=tot, cagr=cagr, vol=vol, sharpe=sharpe, mdd=mdd)


def _pct(x):
    return "   n/a" if (x is None or not np.isfinite(x)) else f"{x*100:+6.1f}%"


def _num(x):
    return " n/a" if (x is None or not np.isfinite(x)) else f"{x:5.2f}"


def main(use_full_500=True, start="2018-01-01", end=None):
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    symbols = U.load_nifty500_symbols() if use_full_500 else U.STARTER_UNIVERSE
    print(f"Loading {len(symbols)} symbols, {start} -> {end}, running one full backtest...")
    panel, index, mcap = data.load_yfinance(symbols, start, end)
    res = bt.run(panel, index, mcap)
    eq, bench = res["equity"].dropna(), res["benchmark"].dropna()
    common = eq.index.intersection(bench.index)
    eq, bench = eq.loc[common], bench.loc[common]

    # ---------------- calendar-year table ----------------
    print("\n" + "=" * 70)
    print("YEAR-BY-YEAR  (total return; 'EXCESS' = strategy minus Nifty)")
    print("=" * 70)
    print(f"{'Year':<8}{'STRATEGY':>11}{'NIFTY500':>11}{'EXCESS':>11}   Winner")
    print("-" * 70)
    years = range(eq.index[0].year, eq.index[-1].year + 1)
    wins = 0; counted = 0
    for i, y in enumerate(years):
        e = eq.loc[f"{y}-01-01":f"{y}-12-31"]
        b = bench.loc[f"{y}-01-01":f"{y}-12-31"]
        if len(e) < 5:
            continue
        se, sb = _stats(e)["tot"], _stats(b)["tot"]
        excess = se - sb
        warm = " (warm-up)" if i == 0 else ""
        if not warm:
            counted += 1
            if excess > 0:
                wins += 1
        win = "—" if warm else ("STRATEGY" if excess > 0 else "Nifty")
        print(f"{y:<8}{_pct(se):>11}{_pct(sb):>11}{_pct(excess):>11}   {win}{warm}")
    print("-" * 70)
    print(f"Strategy beat the Nifty in {wins} of {counted} full years.")

    # ---------------- equal-thirds (risk-adjusted) ----------------
    t0, t1 = eq.index[0], eq.index[-1]
    cut1 = t0 + (t1 - t0) / 3
    cut2 = t0 + 2 * (t1 - t0) / 3
    thirds = [("Early third", t0, cut1),
              ("Middle third", cut1, cut2),
              ("Late third", cut2, t1)]
    print("\n" + "=" * 70)
    print("EQUAL THIRDS OF THE PERIOD  (risk-adjusted: CAGR / Sharpe / maxDD)")
    print("=" * 70)
    print(f"{'Window':<14}{'dates':<20}{'  CAGR  Sharpe   maxDD':>34}")
    for label, a, b in thirds:
        es, bs = _stats(eq.loc[a:b]), _stats(bench.loc[a:b])
        span = f"{a.strftime('%b%y')}-{b.strftime('%b%y')}"
        print(f"{label:<14}{span:<20}")
        print(f"   strategy {'':<22}{_pct(es['cagr'])} {_num(es['sharpe'])}  {_pct(es['mdd'])}")
        print(f"   nifty500 {'':<22}{_pct(bs['cagr'])} {_num(bs['sharpe'])}  {_pct(bs['mdd'])}")
    print("=" * 70)
    print("\nRead it like this: consistent EXCESS across years + a Sharpe edge in")
    print("ALL THREE thirds = a robust effect. Outperformance crammed into one")
    print("window (esp. 2020-21) = mostly the bull run, not a durable edge.")


if __name__ == "__main__":
    main(use_full_500=("--starter" not in sys.argv))
