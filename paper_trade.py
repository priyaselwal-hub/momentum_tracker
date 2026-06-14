"""
paper_trade.py — forward paper-trading for the momentum engine.

Run this ONCE each morning (before the market opens). It uses data through
yesterday's close to:
  * exit any held paper-position that broke a rule (stop / rank / trend),
  * buy the top-ranked name(s) to fill empty slots (regime permitting),
and it keeps a running scoreboard of your paper portfolio vs just holding the
Nifty 500. No real money moves. The future can't be survivorship-biased or
curve-fit, so this is the most honest test there is.

    python paper_trade.py            # full Nifty 500 (best picks, slower)
    python paper_trade.py --starter  # quick starter universe
    python paper_trade.py --score    # just show the scoreboard, don't trade
    python paper_trade.py --force     # re-process today's data again

State + an append-only trade log are saved to your Google Drive (if mounted)
so they persist across sessions.

Honesty notes baked in:
  * Holds 2 names on Rs.10,000 — your REAL situation — so the swings here are
    representative, not the smoothed 10-name backtest.
  * "Fills" use yesterday's close as the reference price and charge full costs
    (~0.5% round trip), which is slightly conservative vs a real next-open fill.
"""
import os, sys, json, csv
import numpy as np
import pandas as pd
import config as C
import indicators as ind
import data, backtest as bt
import universe as U

PAPER_CAPITAL   = 10000.0
PAPER_POSITIONS = 2
COST = (C.COST_ONEWAY_BPS + C.SLIPPAGE_BPS) / 1e4


def _paper_dir():
    if os.path.isdir("/content/drive/MyDrive"):
        d = "/content/drive/MyDrive/momentum_paper"
    else:
        d = "paper_data"
    os.makedirs(d, exist_ok=True)
    return d


def _load_state(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"cash": PAPER_CAPITAL, "positions": {}, "start_date": None,
            "start_nifty": None, "last_run": None, "n_closed": 0, "wins": 0,
            "equity_history": [], "last_actions": [], "last_regime": None,
            "last_idx": None, "last_idx_ma": None, "last_asof": None}


def _save_state(path, st):
    with open(path, "w") as f:
        json.dump(st, f, indent=2, default=str)


def _applog(path, row, fields):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)


def _last(s):
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else np.nan


LOG_FIELDS = ["date", "action", "symbol", "price", "shares", "stop",
              "reason", "ret_pct", "entry_date", "entry_price"]


def _scoreboard(st, panel, index):
    idx_px = _last(index["close"])
    close_of = {t: _last(df["close"]) for t, df in panel.items()}
    mtm = st["cash"] + sum(p["shares"] * close_of.get(s, p["entry"])
                           for s, p in st["positions"].items())
    paper_ret = mtm / PAPER_CAPITAL - 1.0
    nifty_ret = (idx_px / st["start_nifty"] - 1.0) if st.get("start_nifty") else 0.0
    print("-" * 60)
    print(f"PAPER SCOREBOARD (since {st.get('start_date')})")
    print(f"  Paper portfolio : Rs.{mtm:,.0f}   ({paper_ret*100:+.1f}%)")
    print(f"  Nifty 500 (hold): {nifty_ret*100:+.1f}%")
    print(f"  Excess vs Nifty : {(paper_ret - nifty_ret)*100:+.1f}%")
    wr = (st["wins"] / st["n_closed"] * 100) if st["n_closed"] else float("nan")
    print(f"  Closed trades   : {st['n_closed']}  (win rate "
          f"{wr:.0f}%)" if st["n_closed"] else "  Closed trades   : 0")
    if st["positions"]:
        print("  Open positions  :")
        for s, p in st["positions"].items():
            cl = close_of.get(s, p["entry"])
            print(f"     {s:<12} entry {p['entry']:>8.1f}  now {cl:>8.1f}  "
                  f"({(cl/p['entry']-1)*100:+.1f}%)  stop {p['stop']:.1f}")
    else:
        print("  Open positions  : none (in cash)")
    print("-" * 60)


def main(use_full_500=True, score_only=False, force=False):
    pdir = _paper_dir()
    spath = os.path.join(pdir, "paper_state.json")
    lpath = os.path.join(pdir, "paper_log.csv")
    st = _load_state(spath)
    where = "Google Drive" if pdir.startswith("/content/drive") else "local folder"
    print(f"Paper records: {where}  ({pdir})")

    symbols = U.load_nifty500_symbols() if use_full_500 else U.STARTER_UNIVERSE
    end = pd.Timestamp.today()
    start = (end - pd.Timedelta(days=600)).strftime("%Y-%m-%d")
    print(f"Loading {len(symbols)} symbols up to {end.strftime('%Y-%m-%d')}...")
    panel, index, mcap = data.load_yfinance(symbols, start, end.strftime("%Y-%m-%d"))

    asof = index.index[-1]
    asof_str = asof.strftime("%Y-%m-%d")

    if score_only:
        _scoreboard(st, panel, index); return
    if st.get("last_run") == asof_str and not force:
        print(f"\nAlready processed data through {asof_str}. Nothing new to do today.")
        _scoreboard(st, panel, index); return

    idx_ma = _last(ind.moving_average(index["close"], C.DMA_INDEX))
    idx_px = _last(index["close"])
    regime_on = np.isfinite(idx_ma) and idx_px > idx_ma

    masks = bt.build_universe_mask(panel, mcap)
    rows = []
    for t, df in panel.items():
        try:
            elig = bool(masks[t].iloc[-1])
        except Exception:
            elig = False
        if not elig:
            continue
        sc = _last(ind.momentum_score_series(df["close"]))
        ma = _last(ind.moving_average(df["close"], C.DMA_STOCK))
        cl = _last(df["close"]); lo = _last(df["low"])
        at = _last(ind.atr(df["high"], df["low"], df["close"]))
        if not all(np.isfinite(v) for v in (sc, ma, cl, at, lo)):
            continue
        rows.append((t, sc, cl, lo, ma, at))
    R = (pd.DataFrame(rows, columns=["symbol", "score", "close", "low", "ma", "atr"])
         .sort_values("score", ascending=False).reset_index(drop=True))
    R["rank"] = R.index + 1
    rank_of = dict(zip(R["symbol"], R["rank"]))
    close_of = dict(zip(R["symbol"], R["close"]))
    ma_of = dict(zip(R["symbol"], R["ma"]))
    low_of = dict(zip(R["symbol"], R["low"]))
    n_elig = len(R)
    top_cut = max(1, int(np.ceil(C.TOP_QUANTILE * n_elig)))
    exit_cut = max(top_cut, C.EXIT_BUFFER_MULT * PAPER_POSITIONS)

    if st["start_date"] is None:
        st["start_date"] = asof_str
        st["start_nifty"] = idx_px

    actions = []

    # ---- EXITS ----
    for sym in list(st["positions"]):
        p = st["positions"][sym]
        cl = close_of.get(sym)
        reason = fill = None
        if sym in low_of and low_of[sym] <= p["stop"]:
            reason, fill = "atr_stop", p["stop"]
        elif rank_of.get(sym, 10**9) > exit_cut:
            reason, fill = "rank_exit", cl
        elif cl is not None and ma_of.get(sym) is not None and cl < ma_of[sym]:
            reason, fill = "trend_exit", cl
        elif sym not in rank_of:
            reason, fill = "ineligible", (cl if cl else p["entry"])
        if reason and fill:
            st["cash"] += p["shares"] * fill * (1 - COST)
            ret = fill / p["entry"] - 1.0
            st["n_closed"] += 1
            if ret > 0:
                st["wins"] += 1
            _applog(lpath, {"date": asof_str, "action": "SELL", "symbol": sym,
                            "price": round(fill, 2), "shares": p["shares"], "stop": "",
                            "reason": reason, "ret_pct": round(ret * 100, 2),
                            "entry_date": p["entry_date"], "entry_price": p["entry"]},
                    LOG_FIELDS)
            actions.append(f"SELL {sym} @ {fill:.1f}   ({reason}, {ret*100:+.1f}%)")
            del st["positions"][sym]

    # ---- BUYS ----
    if regime_on:
        free = PAPER_POSITIONS - len(st["positions"])
        if free > 0:
            equity_now = st["cash"] + sum(
                p["shares"] * close_of.get(s, p["entry"])
                for s, p in st["positions"].items())
            budget = equity_now / PAPER_POSITIONS
            for _, r in R.head(PAPER_POSITIONS).iterrows():
                if free <= 0:
                    break
                sym = r["symbol"]
                if sym in st["positions"] or r["close"] < r["ma"]:
                    continue
                unit = r["close"] * (1 + COST)
                shares = int(min(budget, st["cash"]) // unit)
                if shares <= 0:
                    continue
                st["cash"] -= shares * unit
                stop = r["close"] - C.ATR_MULT * r["atr"]
                st["positions"][sym] = {"shares": shares, "entry": round(float(r["close"]), 2),
                                        "entry_date": asof_str, "stop": round(float(stop), 2)}
                _applog(lpath, {"date": asof_str, "action": "BUY", "symbol": sym,
                                "price": round(float(r["close"]), 2), "shares": shares,
                                "stop": round(float(stop), 2), "reason": "entry",
                                "ret_pct": "", "entry_date": asof_str,
                                "entry_price": round(float(r["close"]), 2)}, LOG_FIELDS)
                actions.append(f"BUY  {sym} @ {r['close']:.1f}   (set GTT stop {stop:.1f})")
                free -= 1

    # ---- record data for the dashboard ----
    close_all = {t: _last(df["close"]) for t, df in panel.items()}
    for s, p in st["positions"].items():
        lp = close_all.get(s)
        if lp is not None and np.isfinite(lp):
            p["last_price"] = round(float(lp), 2)
    paper_value = st["cash"] + sum(p["shares"] * p.get("last_price", p["entry"])
                                   for p in st["positions"].values())
    nifty_value = (PAPER_CAPITAL * idx_px / st["start_nifty"]
                   if st.get("start_nifty") else PAPER_CAPITAL)
    hist = st.setdefault("equity_history", [])
    if not hist or hist[-1][0] != asof_str:
        hist.append([asof_str, round(float(paper_value), 2), round(float(nifty_value), 2)])
    st["last_regime"] = bool(regime_on)
    st["last_idx"] = round(float(idx_px), 2)
    st["last_idx_ma"] = round(float(idx_ma), 2) if np.isfinite(idx_ma) else None
    st["last_actions"] = actions
    st["last_asof"] = asof_str

    st["last_run"] = asof_str
    _save_state(spath, st)

    print("\n" + "=" * 60)
    print(f"PAPER TRADE — data through {asof_str}")
    print("=" * 60)
    print(f"Regime: {'RISK-ON' if regime_on else 'RISK-OFF (no new buys)'}  "
          f"(Nifty {idx_px:,.0f} vs 200DMA {idx_ma:,.0f})")
    print("Today's actions:")
    if actions:
        for a in actions:
            print("   " + a)
    else:
        print("   none — hold steady.")
    if regime_on and not R.empty:
        tops = ", ".join(f"{r.symbol}" for r in R.head(5).itertuples())
        print(f"Top of ranking today: {tops}")
    _scoreboard(st, panel, index)
    print("Reminder: in a REAL account you'd place these as orders + GTT stops.")


if __name__ == "__main__":
    a = sys.argv
    main(use_full_500=("--starter" not in a),
         score_only=("--score" in a), force=("--force" in a))
