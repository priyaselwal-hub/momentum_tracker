"""
indicators.py — the math. Pure functions, no I/O, easy to unit-test.

The only non-obvious one is the momentum score, which is Andreas Clenow's
"adjusted slope" momentum (from 'Stocks on the Move'):

    1. fit a straight line to LOG(price) over the last N days
       (a straight line on log price == exponential/compounding fit on price)
    2. annualise the daily slope  -> exp(slope * 252) - 1
    3. multiply by R^2 of the fit -> rewards SMOOTH, persistent trends and
       penalises jumpy ones (a one-day 20% spike has a high slope but low R^2).

Higher score = stronger, cleaner uptrend = closer to the top of the buy list.
"""
import numpy as np
import pandas as pd
import config as C


def moving_average(close: pd.Series, window: int) -> pd.Series:
    return close.rolling(window, min_periods=window).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series,
        period: int = C.ATR_PERIOD) -> pd.Series:
    """Average True Range (simple-mean variant)."""
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _make_score_fn(length: int):
    """Return a fast closure computing the adjusted-momentum score for one window
    of LOG prices. x (0..L-1) is fixed, so its deviations are precomputed."""
    x = np.arange(length, dtype=float)
    x_dev = x - x.mean()
    denom = float(np.dot(x_dev, x_dev))  # constant: sum of squared x deviations

    def score(logwin: np.ndarray) -> float:
        if np.any(~np.isfinite(logwin)):
            return np.nan
        y_dev = logwin - logwin.mean()
        cov = float(np.dot(x_dev, y_dev))
        slope = cov / denom
        ss_tot = float(np.dot(y_dev, y_dev))
        if ss_tot <= 0.0:
            return np.nan
        r2 = (cov * cov) / (denom * ss_tot)
        annualised = np.exp(slope * C.ANNUALISATION) - 1.0
        return annualised * r2

    return score


def momentum_score_series(close: pd.Series,
                          length: int = C.LOOKBACK_DAYS) -> pd.Series:
    """Rolling adjusted-momentum score for a single stock's close series.
    Value at date t uses ONLY closes up to and including t (no lookahead)."""
    fn = _make_score_fn(length)
    logp = np.log(close.astype(float))
    return logp.rolling(length, min_periods=length).apply(fn, raw=True)
