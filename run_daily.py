"""
run_daily.py — your MORNING REPORT. Run before the market opens.

    python run_daily.py

It prints:
  * REGIME banner       — is the Nifty above its 200DMA? (if not: no new buys)
  * BUY LIST            — today's top-ranked names passing all filters, each with
                          the exact ATR stop price to set as a GTT
  * SELL SIGNALS        — for names you already hold (optional holdings.csv),
                          which ones the rules say to exit today, and why

holdings.csv (optional), one row per position you hold:
    symbol,entry_price
    TITAN,3450
    CUMMINSIND,3120

This is decision SUPPORT, not autopilot. You place every order yourself.
At Rs.10k you can realistically hold 1-2 names — so look at the top 1-2 of the
buy list, not all ten.
"""
import os, sys
import numpy as np
import pandas as pd
import config as C
import indicators as ind
import data, backtest as bt
import universe as U


def latest(s):
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else np.nan


def main(use_full_500=False, lookback_days=600):
    end = pd.Timestamp.today()
    start = (end - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    symbols = U.load_nifty500_symbols() if use_full_500 else U.STARTER_UNIVERSE
    panel, index, mcap = data.load_yfinance(symbols, start, end.strftime("%Y-%m-%d"))

    # --- regime ---
    idx_ma = latest(ind.moving_average(index["close"], C.DMA_INDEX))
    idx_px = latest(index["close"])
    regime_on = np.isfinite(idx_ma) and idx_px > idx_ma

    # --- score + filter every name as of the latest bar ---
    masks = bt.build_universe_mask(panel, mcap)
    rows = []
    for t, df in panel.items():
        try:
            elig = bool(masks[t].iloc[-1])
        except Exception:
            elig = False
        if not elig:
            continue
        score = latest(ind.momentum_score_series(df["close"]))
        ma100 = latest(ind.moving_average(df["close"], C.DMA_STOCK))
        close = latest(df["close"])
        atr = latest(ind.atr(df["high"], df["low"], df["close"]))
        if not all(np.isfinite(v) for v in (score, ma100, close, atr)):
            continue
        rows.append({"symbol": t, "score": score, "close": close,
                     "above_100dma": close > ma100,
                     "atr_stop": close - C.ATR_MULT * atr})
    R = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    R["rank"] = R.index + 1

    print("=" * 64)
    print(f"MORNING REPORT — {end.strftime('%a %d %b %Y')}")
    print("=" * 64)
    print(f"Nifty 500: {idx_px:,.0f}  |  200DMA: {idx_ma:,.0f}  ->  "
          f"REGIME: {'RISK-ON (new buys allowed)' if regime_on else 'RISK-OFF (NO new buys)'}")
    print("-" * 64)

    buyable = R[R["above_100dma"]].head(C.N_POSITIONS)
    if not regime_on:
        print("Regime is risk-off: skip new buys. Manage existing holdings only.")
    else:
        print(f"TOP BUY CANDIDATES (you can hold ~1-2 at Rs.10k — look at the top):")
        print(f"{'#':>2} {'SYMBOL':<12}{'CLOSE':>10}{'GTT STOP':>11}  (set stop as a GTT)")
        for _, r in buyable.iterrows():
            print(f"{int(r['rank']):>2} {r['symbol']:<12}{r['close']:>10.1f}"
                  f"{r['atr_stop']:>11.1f}")
    print("-" * 64)

    # --- sell signals for current holdings ---
    if os.path.exists("holdings.csv"):
        h = pd.read_csv("holdings.csv")
        n_elig = len(R)
        top_cut = max(1, int(np.ceil(C.TOP_QUANTILE * n_elig)))
        exit_cut = max(top_cut, C.EXIT_BUFFER_MULT * C.N_POSITIONS)
        rank_of = dict(zip(R["symbol"], R["rank"]))
        print("YOUR HOLDINGS:")
        for _, row in h.iterrows():
            sym = str(row["symbol"]).strip()
            rk = rank_of.get(sym, None)
            sub = R[R["symbol"] == sym]
            reasons = []
            if rk is None:
                reasons.append("no longer eligible/ranked")
            else:
                if rk > exit_cut:
                    reasons.append(f"fell out of top {exit_cut} (rank {rk})")
                if len(sub) and not bool(sub.iloc[0]["above_100dma"]):
                    reasons.append("closed below 100DMA")
            verdict = "SELL  -> " + "; ".join(reasons) if reasons else "HOLD"
            rk_txt = f"rank {rk}" if rk else "unranked"
            print(f"  {sym:<12} {rk_txt:<12} {verdict}")
        print("  (Plus: your GTT ATR stop exits you automatically if price craters.)")
    else:
        print("No holdings.csv found — create one to get SELL signals on positions.")
    print("=" * 64)


if __name__ == "__main__":
    main(use_full_500=("--full500" in sys.argv))
