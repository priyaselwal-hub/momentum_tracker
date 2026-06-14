"""
config.py — every strategy parameter in one place.

These are the values we locked while designing the engine. Change them HERE,
nowhere else. Each one has a short note on what it does and why it is set this way.
"""

# ---- Ranking signal (Clenow-style adjusted momentum) ----
LOOKBACK_DAYS   = 90      # window for the exponential-regression slope
ANNUALISATION   = 252     # trading days/yr, to annualise the daily log slope

# ---- Per-stock trend filter ----
DMA_STOCK       = 100     # a stock must be above its 100-day MA to be buyable

# ---- Market regime filter (the crash guard) ----
DMA_INDEX       = 200     # new buys only when the index is above its 200-day MA
REGIME_EXIT_ALL = False   # False = Clenow style: risk-off just stops NEW buys,
                          # existing positions still managed by their own exits.
                          # True  = aggressive: dump everything when regime flips.

# ---- Catastrophe stop ----
ATR_PERIOD      = 20      # ATR lookback
ATR_MULT        = 3.0     # stop = entry - 3 x ATR(20). Wide = disaster brake only.

# ---- Hold / rotate band ----
TOP_QUANTILE    = 0.20    # a held name is sold once it leaves the top 20% of ranks
EXIT_BUFFER_MULT = 2      # ...but never tighter than 2 x N_POSITIONS ranks.
                          # This is the HYSTERESIS gap: you BUY only names in the
                          # top N_POSITIONS, but don't SELL until a name falls past
                          # the WIDER of (top 20%) or (2 x N_POSITIONS). The gap
                          # between buy-zone and sell-zone is what stops whipsaw.
N_POSITIONS     = 10      # target number of holdings in the BACKTEST.
                          # NB: live at Rs.10k you will hold 1-2. The backtest uses
                          # a diversified basket to measure whether the EDGE is real;
                          # your live experience will be far higher variance.

# ---- Rebalance cadence ----
REBALANCE       = "weekly"  # re-rank + rotate once a week (last trading day of week)

# ---- Universe construction ----
MCAP_FLOOR_CR     = 5000.0  # market-cap floor, in Rs. crore
FETCH_MCAP        = False    # fetch per-stock market cap from yfinance .info?
                            # OFF by default: .info is slow & flaky over hundreds of
                            # names and can silently empty the universe. With it OFF,
                            # the cap floor is delegated to "you fed in a large-cap
                            # universe (e.g. Nifty 500) + the turnover filter below",
                            # which all Nifty-500 names satisfy anyway. Turn ON only
                            # with a small universe. (Point-in-time caps = a v2 job.)
TURNOVER_FLOOR_CR = 5.0     # median daily traded value floor, Rs. crore
TURNOVER_WINDOW   = 20      # window for the median-turnover test
MIN_HISTORY_DAYS  = 200     # a stock needs this much history to be eligible

# ---- Costs (applied per side: buy AND sell) ----
COST_ONEWAY_BPS = 20.0    # all-in charges per side (STT, exch, GST, stamp, DP...) ~0.20%
SLIPPAGE_BPS    = 5.0     # assumed slippage per side
# => round-trip drag ~= 2 x (20 + 5) = 50 bps = 0.50%. Deliberately a bit conservative.

# ---- Backtest bookkeeping ----
INITIAL_CAPITAL = 1_000_000  # notional, for readable rupee P&L. Results are scale-free in %.
RF_ANNUAL       = 0.0        # risk-free rate used in Sharpe (0 = simple; note in report)
EXECUTION       = "next_open"  # decide on close of day t, fill at open of day t+1 (no lookahead)
