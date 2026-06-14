"""
run_backtest.py — run the REAL backtest on NSE data. Use on your own machine.

    pip install -r requirements.txt
    python run_backtest.py

What it does:
  * pulls daily OHLCV for the universe + the Nifty 500 index via yfinance
  * runs the momentum engine over the chosen date range
  * prints strategy-vs-benchmark metrics
  * saves equity_curve.png and trades.csv

READ THIS FIRST — honesty caveats baked in:
  1. Market caps from yfinance are CURRENT, not point-in-time, so the universe
     filter is applied with today's caps -> mild survivorship bias. For a clean
     result, supply point-in-time caps. The engine is honest; the free data is not.
  2. yfinance is delisting-biased: names that died are missing -> results are
     optimistic. Treat the number as an UPPER bound, not an expectation.
  3. Start with STARTER_UNIVERSE to sanity-check, then switch to the full Nifty 500.
"""
import sys
import pandas as pd
import config as C
import data, backtest as bt
import universe as U


def main(start="2018-01-01", end=None, use_full_500=False):
    end = end or pd.Timestamp.today().strftime("%Y-%m-%d")
    symbols = U.load_nifty500_symbols() if use_full_500 else U.STARTER_UNIVERSE
    print(f"Universe: {len(symbols)} symbols | {start} -> {end}")
    print("Downloading (this can take a few minutes for the full 500)...")

    panel, index, mcap = data.load_yfinance(symbols, start, end)
    print(f"Got data for {len(panel)} symbols + index ({len(index)} days).")
    if len(panel) < 5 or len(index) < C.MIN_HISTORY_DAYS:
        print("Not enough data — check your connection / symbols.")
        return

    res = bt.run(panel, index, mcap)
    m = res["metrics"]

    def pct(x): return f"{x*100:>8.2f}%"
    print("\n" + "=" * 58)
    print("BACKTEST RESULT  (real data — read with the caveats above)")
    print("=" * 58)
    print(f"{'':22}{'STRATEGY':>12}{'NIFTY500':>12}")
    print(f"{'Total return':22}{pct(m['strat_total_return']):>12}{pct(m['bench_total_return']):>12}")
    print(f"{'CAGR':22}{pct(m['strat_CAGR']):>12}{pct(m['bench_CAGR']):>12}")
    print(f"{'Volatility (ann.)':22}{pct(m['strat_vol']):>12}{pct(m['bench_vol']):>12}")
    print(f"{'Sharpe (rf=0)':22}{m['strat_Sharpe']:>12.2f}{m['bench_Sharpe']:>12.2f}")
    print(f"{'Max drawdown':22}{pct(m['strat_maxDD']):>12}{pct(m['bench_maxDD']):>12}")
    print("-" * 58)
    print(f"Buys/Sells: {m['n_buys']}/{m['n_sells']} | "
          f"closed trades: {m['n_closed_trades']} | win rate: {m['win_rate']:.0%}")
    print(f"Total cost paid: Rs.{m['total_cost']:,.0f} "
          f"({m['cost_pct_of_initial']:.1%} of starting capital)")
    print("=" * 58)
    print("\nHow to judge it: the strategy must beat the Nifty 500 line on a")
    print("RISK-ADJUSTED basis (higher Sharpe, shallower drawdown) AFTER costs —")
    print("not just on raw return. If it doesn't, the edge isn't there yet.")

    res["trades"].to_csv("trades.csv", index=False)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ax = (res["equity"] / res["equity"].iloc[0]).plot(label="Strategy", lw=1.6)
        (res["benchmark"] / res["benchmark"].iloc[0]).plot(ax=ax, label="Nifty 500", lw=1.2)
        ax.set_title("Momentum engine vs Nifty 500 (growth of 1)")
        ax.legend(); ax.grid(alpha=.3)
        ax.figure.savefig("equity_curve.png", dpi=130, bbox_inches="tight")
        print("\nSaved: equity_curve.png, trades.csv")
    except Exception as e:
        print(f"(plot skipped: {e}) — trades.csv saved.")


if __name__ == "__main__":
    full = "--full500" in sys.argv
    main(use_full_500=full)
