"""
backtest.py — the engine.

Design decisions baked in (all discussed during design):
  * No lookahead: signals use closes up to day t; orders fill at day t+1 OPEN.
  * Weekly re-ranking & rotation; the ATR catastrophe stop is checked DAILY
    (mirrors a GTT sitting at the broker).
  * Regime filter gates NEW buys (or exits all, if REGIME_EXIT_ALL).
  * Costs charged on every buy and sell (round trip ~0.5%).
  * Equal-weight sizing across held names (risk-parity is a v2 upgrade).

The output is an equity curve + a metrics dict + the trade blotter, plus a
buy-&-hold benchmark on the index so we can see if the engine beats just holding.
"""
import numpy as np
import pandas as pd
import config as C
import indicators as ind


# ---------------------------------------------------------------- universe
def build_universe_mask(panel, mcap):
    """Per-(date,ticker) boolean: is this name eligible today?
    Eligible = market cap >= floor AND median daily turnover >= floor
               AND enough history exists.
    Returns dict[ticker -> bool Series aligned to that ticker's index]."""
    masks = {}
    for t, df in panel.items():
        cap = mcap.get(t, np.nan)
        # unknown cap -> don't exclude on cap grounds; let turnover do the filtering
        cap_ok = True if not np.isfinite(cap) else (cap >= C.MCAP_FLOOR_CR)
        turnover_cr = (df["close"] * df["volume"]) / 1e7          # Rs. crore traded
        med_turn = turnover_cr.rolling(C.TURNOVER_WINDOW,
                                       min_periods=C.TURNOVER_WINDOW).median()
        liq_ok = med_turn >= C.TURNOVER_FLOOR_CR
        hist_ok = pd.Series(np.arange(len(df)) >= C.MIN_HISTORY_DAYS, index=df.index)
        masks[t] = (bool(cap_ok) & liq_ok & hist_ok).fillna(False)
    return masks


# ----------------------------------------------------- precomputed signals
def precompute(panel, index):
    sig = {}
    for t, df in panel.items():
        sig[t] = pd.DataFrame({
            "close": df["close"],
            "open":  df["open"],
            "low":   df["low"],
            "score": ind.momentum_score_series(df["close"]),
            "ma":    ind.moving_average(df["close"], C.DMA_STOCK),
            "atr":   ind.atr(df["high"], df["low"], df["close"]),
        })
    regime_on = index["close"] > ind.moving_average(index["close"], C.DMA_INDEX)
    return sig, regime_on


def _weekly_rebalance_dates(dates):
    # Return the last trading day of each ISO week as a set of pd.Timestamp.
    # (Built to be independent of pandas/numpy datetime type quirks across versions.)
    dti = pd.DatetimeIndex(dates)
    iso = dti.isocalendar()
    yw = iso["year"].astype(int).values * 100 + iso["week"].astype(int).values
    tmp = pd.DataFrame({"d": dti})
    tmp["yw"] = yw
    last = tmp.groupby("yw")["d"].max()
    return set(pd.Timestamp(x) for x in last)


# --------------------------------------------------------------- backtest
def run(panel, index, mcap, verbose=False):
    dates = index.index
    sig, regime_on = precompute(panel, index)
    masks = build_universe_mask(panel, mcap)
    rebal = _weekly_rebalance_dates(dates)

    cash = float(C.INITIAL_CAPITAL)
    positions = {}                 # ticker -> dict(shares, entry, stop)
    pending = []                   # orders to fill at NEXT open: (side,ticker,...)
    equity, eq_dates = [], []
    trades = []                    # closed-trade blotter
    buy_log = []                   # every ticker bought (for diagnostics)
    n_buys = n_sells = 0
    total_cost = 0.0

    cost_rate = (C.COST_ONEWAY_BPS + C.SLIPPAGE_BPS) / 1e4

    def px(t, col, dt):
        try:
            v = sig[t].at[dt, col]
            return float(v) if np.isfinite(v) else np.nan
        except KeyError:
            return np.nan

    for di, dt in enumerate(dates):
        # 1) fill yesterday's orders at today's OPEN ------------------------
        still = []
        for order in pending:
            side, t = order[0], order[1]
            o = px(t, "open", dt)
            if not np.isfinite(o):
                continue
            if side == "BUY":
                target_val = order[2]
                shares = int(target_val // o)
                if shares <= 0:
                    continue
                cost = shares * o * cost_rate
                cash_need = shares * o + cost
                if cash_need > cash:
                    shares = int((cash * (1 - cost_rate)) // o)
                    if shares <= 0:
                        continue
                    cost = shares * o * cost_rate
                    cash_need = shares * o + cost
                cash -= cash_need
                total_cost += cost
                a = px(t, "atr", dt)
                stop = o - C.ATR_MULT * a if np.isfinite(a) else o * 0.80
                positions[t] = {"shares": shares, "entry": o, "stop": stop,
                                "entry_dt": dt}
                n_buys += 1
                buy_log.append(t)
            else:  # SELL
                if t not in positions:
                    continue
                p = positions.pop(t)
                fill = o
                proceeds = p["shares"] * fill
                cost = proceeds * cost_rate
                cash += proceeds - cost
                total_cost += cost
                n_sells += 1
                trades.append({"ticker": t, "entry": p["entry"], "exit": fill,
                               "ret": fill / p["entry"] - 1.0, "reason": order[2]})
        pending = still

        # 2) DAILY catastrophe-stop check (acts like a resting GTT) ---------
        for t in list(positions):
            p = positions[t]
            lo = px(t, "low", dt); o = px(t, "open", dt)
            if not np.isfinite(lo):
                continue
            if lo <= p["stop"]:
                # gap through the stop -> fill at open; else fill at stop
                fill = o if (np.isfinite(o) and o < p["stop"]) else p["stop"]
                positions.pop(t)
                proceeds = p["shares"] * fill
                cost = proceeds * cost_rate
                cash += proceeds - cost
                total_cost += cost
                n_sells += 1
                trades.append({"ticker": t, "entry": p["entry"], "exit": fill,
                               "ret": fill / p["entry"] - 1.0, "reason": "atr_stop"})

        # 3) WEEKLY rebalance: decide on today's CLOSE, queue for next open --
        if dt in rebal:
            ranked = []
            for t in panel:
                if not bool(masks[t].get(dt, False)):
                    continue
                sc = px(t, "score", dt)
                if not np.isfinite(sc):
                    continue
                ranked.append((t, sc))
            ranked.sort(key=lambda x: x[1], reverse=True)

            n_elig = len(ranked)
            top_cut = max(1, int(np.ceil(C.TOP_QUANTILE * n_elig)))
            exit_cut = max(top_cut, C.EXIT_BUFFER_MULT * C.N_POSITIONS)  # hysteresis
            order_map = {t: i for i, (t, _) in enumerate(ranked)}

            regime = bool(regime_on.get(dt, False))
            if C.REGIME_EXIT_ALL and not regime:
                for t in list(positions):
                    pending.append(("SELL", t, "regime_off"))
            else:
                # SELLs: fell out of the WIDE exit band, or trend broke (<100DMA)
                for t in list(positions):
                    rank = order_map.get(t, 10**9)   # ineligible today -> far down
                    close_t = px(t, "close", dt); ma_t = px(t, "ma", dt)
                    if rank >= exit_cut:
                        pending.append(("SELL", t, "rank_exit"))
                    elif np.isfinite(close_t) and np.isfinite(ma_t) and close_t < ma_t:
                        pending.append(("SELL", t, "trend_exit"))

                # BUYs: only names inside the top-N_POSITIONS BUY ZONE, regime on.
                # If too few qualify, we deliberately hold fewer (never reach into junk).
                if regime:
                    queued_sell = {o[1] for o in pending if o[0] == "SELL"}
                    held = (set(positions) - queued_sell) | {
                        o[1] for o in pending if o[0] == "BUY"}
                    free = C.N_POSITIONS - len(held)
                    if free > 0:
                        equity_now = cash + sum(
                            p["shares"] * px(t, "close", dt)
                            for t, p in positions.items()
                            if np.isfinite(px(t, "close", dt)))
                        target = equity_now / C.N_POSITIONS
                        added = 0
                        for t, _ in ranked[:C.N_POSITIONS]:   # buy zone = top N
                            if added >= free:
                                break
                            if t in held or t in queued_sell:
                                continue
                            close_t = px(t, "close", dt); ma_t = px(t, "ma", dt)
                            if not (np.isfinite(close_t) and np.isfinite(ma_t)):
                                continue
                            if close_t < ma_t:           # must be above its 100DMA
                                continue
                            pending.append(("BUY", t, target))
                            held.add(t); added += 1

        # 4) mark to market at today's close -------------------------------
        mtm = cash
        for t, p in positions.items():
            c = px(t, "close", dt)
            if np.isfinite(c):
                mtm += p["shares"] * c
        equity.append(mtm); eq_dates.append(dt)

    eq = pd.Series(equity, index=pd.DatetimeIndex(eq_dates))
    bench = C.INITIAL_CAPITAL * index["close"] / index["close"].iloc[0]
    m = _metrics(eq, bench, trades, n_buys, n_sells, total_cost)
    return {"equity": eq, "benchmark": bench, "metrics": m,
            "trades": pd.DataFrame(trades),
            "buy_log": buy_log, "final_holdings": list(positions)}


# ---------------------------------------------------------------- metrics
def _ann_stats(eq):
    r = eq.pct_change().dropna()
    n = len(r)
    if n < 2:
        return 0.0, 0.0, 0.0
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (C.ANNUALISATION / n) - 1.0
    vol = r.std() * np.sqrt(C.ANNUALISATION)
    sharpe = ((r.mean() * C.ANNUALISATION) - C.RF_ANNUAL) / vol if vol > 0 else 0.0
    return cagr, vol, sharpe


def _max_dd(eq):
    roll = eq.cummax()
    return float((eq / roll - 1.0).min())


def _metrics(eq, bench, trades, n_buys, n_sells, total_cost):
    cagr, vol, sharpe = _ann_stats(eq)
    bcagr, bvol, bsharpe = _ann_stats(bench)
    tdf = pd.DataFrame(trades)
    win = float((tdf["ret"] > 0).mean()) if len(tdf) else float("nan")
    return {
        "strat_total_return": eq.iloc[-1] / eq.iloc[0] - 1.0,
        "strat_CAGR": cagr, "strat_vol": vol, "strat_Sharpe": sharpe,
        "strat_maxDD": _max_dd(eq),
        "bench_total_return": bench.iloc[-1] / bench.iloc[0] - 1.0,
        "bench_CAGR": bcagr, "bench_vol": bvol, "bench_Sharpe": bsharpe,
        "bench_maxDD": _max_dd(bench),
        "n_buys": n_buys, "n_sells": n_sells, "n_closed_trades": len(tdf),
        "win_rate": win,
        "total_cost": total_cost,
        "cost_pct_of_initial": total_cost / C.INITIAL_CAPITAL,
    }
