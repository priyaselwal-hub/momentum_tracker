"""
data.py — getting price data in.

Two sources:
  * load_yfinance(...)  -> REAL NSE data. Use this on your own machine.
  * make_synthetic(...) -> fake OHLCV with KNOWN properties, used only to prove
                           the engine's machinery is correct (it cannot tell you
                           anything about real-world profitability).

Both return the same structure:
    panel : dict[str -> DataFrame(open,high,low,close,volume)]  one per ticker
    index : DataFrame(open,high,low,close)  the benchmark (Nifty)
    mcap  : dict[str -> float]   market cap in Rs. crore (for the universe filter)
All frames share a common, sorted DatetimeIndex of trading days.
"""
import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# REAL DATA  (runs on your machine; this sandbox blocks Yahoo/NSE)
# --------------------------------------------------------------------------
def _flatten(df):
    """yfinance may return two-level (MultiIndex) columns even for one ticker.
    Flatten to single-level lowercase OHLCV and drop duplicate columns."""
    import pandas as pd
    if df is None or len(df) == 0:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)   # keep Open/High/Low/Close/Volume
    df = df.rename(columns=str.lower)
    df = df.loc[:, ~df.columns.duplicated()]
    return df


def load_yfinance(tickers, start, end, index_symbol="^CRSLDX"):
    """Download daily OHLCV for `tickers` (NSE symbols WITHOUT the .NS suffix)
    and the benchmark index. Requires `pip install yfinance`.

    index_symbol defaults to ^CRSLDX (Nifty 500). Use ^NSEI for Nifty 50.

    Market cap: only fetched if config.FETCH_MCAP is True (it's slow/unreliable
    in bulk). When off, the universe relies on the turnover filter; see config.
    """
    import yfinance as yf
    import config as C

    need = ["open", "high", "low", "close", "volume"]
    panel, mcap = {}, {}
    failed = []
    for t in tickers:
        try:
            raw = yf.download(f"{t}.NS", start=start, end=end,
                              auto_adjust=True, progress=False)
        except Exception:
            failed.append(t); continue
        df = _flatten(raw)
        if df is None or df.empty or not all(c in df.columns for c in need):
            failed.append(t); continue
        df = df[need].apply(pd.to_numeric, errors="coerce")
        df.index = pd.to_datetime(df.index)
        df = df.dropna(subset=["close"]).sort_index()
        if len(df) < 60:
            failed.append(t); continue
        panel[t] = df

        if C.FETCH_MCAP:
            try:
                mc = yf.Ticker(f"{t}.NS").info.get("marketCap", None)
                mcap[t] = (mc / 1e7) if mc else np.nan   # rupees -> crore
            except Exception:
                mcap[t] = np.nan
        else:
            mcap[t] = np.nan

    iraw = yf.download(index_symbol, start=start, end=end,
                       auto_adjust=True, progress=False)
    idx = _flatten(iraw)
    idx = idx[["open", "high", "low", "close"]].apply(pd.to_numeric, errors="coerce")
    idx.index = pd.to_datetime(idx.index)
    idx = idx.dropna(subset=["close"]).sort_index()

    common = idx.index
    for t in list(panel):
        panel[t] = panel[t].reindex(common).dropna(how="all")
    if failed:
        print(f"(skipped {len(failed)} symbols with no/short data: "
              f"{', '.join(failed[:12])}{' ...' if len(failed) > 12 else ''})")
    return panel, idx, mcap


# --------------------------------------------------------------------------
# SYNTHETIC DATA  (sandbox correctness test ONLY — not a performance signal)
# --------------------------------------------------------------------------
def _ohlc_from_close(close, rng, intraday=0.012):
    """Build plausible OHLC around a close path."""
    n = len(close)
    open_ = np.empty(n); high = np.empty(n); low = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1] * (1 + rng.normal(0, 0.003, n - 1))  # small overnight gap
    for i in range(n):
        hi = max(open_[i], close[i]) * (1 + abs(rng.normal(0, intraday)))
        lo = min(open_[i], close[i]) * (1 - abs(rng.normal(0, intraday)))
        high[i], low[i] = hi, lo
    return open_, high, low


def make_synthetic(n_days=1000, seed=7):
    """Generate a small synthetic market with deliberately KNOWN behaviour so we
    can verify the engine does the right thing:

      TREND_*   strong, smooth up-trends (low noise)  -> SHOULD rank top & be held
      CHOP_*    no drift, high noise                  -> SHOULD rarely be selected
      DOWN_*    persistent down-trends                -> SHOULD be filtered out
      CRASH_X   trends up, then GAPS DOWN ~35% one day-> SHOULD trip the ATR stop
      The index is a calm up-trend with one corrective dip (to exercise the regime
      filter switching new buys off and back on).
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-01", periods=n_days)
    panel, mcap = {}, {}

    def build(name, drift, vol, mc, shock=None):
        steps = rng.normal(drift, vol, n_days)
        if shock is not None:
            day, mag = shock
            steps[day] += mag            # inject a one-day gap (e.g. -0.35)
        close = 100 * np.exp(np.cumsum(steps))
        o, h, l = _ohlc_from_close(close, rng)
        # if a shock day, force a real gap-down open/low so the stop must fire
        if shock is not None:
            day, mag = shock
            o[day] = close[day - 1] * (1 + mag * 0.6)
            l[day] = min(l[day], close[day] * 0.99)
            h[day] = max(o[day], close[day])
        vol_series = rng.integers(3_000_000, 9_000_000, n_days).astype(float)
        panel[name] = pd.DataFrame(
            {"open": o, "high": h, "low": l, "close": close, "volume": vol_series},
            index=dates)
        mcap[name] = mc

    for i in range(14):
        build(f"TREND_{i}", drift=0.0009 + 0.00004 * i, vol=0.011, mc=6000 + 400 * i)
    for i in range(8):
        build(f"CHOP_{i}",  drift=0.0000, vol=0.020, mc=7000 + 300 * i)
    for i in range(5):
        build(f"DOWN_{i}",  drift=-0.0010, vol=0.013, mc=6000 + 400 * i)
    # a name that looks great then collapses ~ 2/3 through the sample
    build("CRASH_X", drift=0.0013, vol=0.010, mc=9000, shock=(int(n_days * 0.66), -0.35))
    # one illiquid tiddler that should be screened out by the cap floor
    build("TINY_1",  drift=0.0011, vol=0.015, mc=1200)

    # benchmark: calm uptrend with a corrective dip around day 300-420
    dip = np.zeros(n_days); dip[300:420] = -0.0018
    isteps = rng.normal(0.0006, 0.008, n_days) + dip
    iclose = 18000 * np.exp(np.cumsum(isteps))
    io, ih, il = _ohlc_from_close(iclose, rng, intraday=0.006)
    index = pd.DataFrame({"open": io, "high": ih, "low": il, "close": iclose},
                         index=dates)
    return panel, index, mcap
