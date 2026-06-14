# Momentum Engine — a rules-based relative-strength screener for NSE

A once-a-day, end-of-day stock screener for the Indian market. It ranks a
universe of liquid stocks by trend strength, and each morning tells you the
top names to consider buying and the exact stop price to set. **You place
every order yourself** — this is decision support, not an auto-trader.

> ⚠️ **Read `WHAT THIS IS NOT` at the bottom before risking a single rupee.**

---

## What it does

- **Universe:** liquid stocks only — market cap ≥ ₹5,000 cr and median daily
  turnover ≥ ₹5 cr. (Junk and illiquid traps are filtered out.)
- **Ranking:** 90-day exponential-regression slope × R² (Clenow "adjusted
  momentum") — rewards smooth, persistent up-trends, penalises jumpy ones.
- **Filters:** a stock must be above its 100-day MA to be bought; new buys only
  happen when the Nifty 500 is above its 200-day MA (crash guard).
- **Exits:** sell when a name falls out of the wide ranking band, closes below
  its 100-DMA, or hits its **3 × ATR(20) catastrophe stop** (set as a GTT).
- **Cadence:** re-rank and rotate **weekly**; the ATR stop is watched daily by
  your broker's GTT.

All parameters live in `config.py` — change them there, nowhere else.

---

## Setup (on your own machine)

```bash
pip install -r requirements.txt
```

> This sandbox where the code was built cannot reach Yahoo/NSE, so the **real**
> backtest must run on your machine. The engine was verified correct here on
> synthetic data (`python selftest.py` — all checks pass).

## 1. Backtest first — does it even work?

```bash
python run_backtest.py            # quick run on the starter universe
python run_backtest.py --full500  # the real thing: full Nifty 500
```

Prints a STRATEGY vs NIFTY 500 table and saves `equity_curve.png` + `trades.csv`.

**How to judge it (this is the whole point):** the strategy must beat the
Nifty 500 on a **risk-adjusted** basis — higher **Sharpe** and shallower
**max drawdown**, *after* costs — not just on raw return. A higher return with
double the drawdown is not an edge, it's just more leverage on beta. **If it
doesn't beat the benchmark, the edge isn't there and you should not trade it.**

## 2. Daily — the morning report

```bash
python run_daily.py            # or --full500
```

Prints: the regime banner, today's top buy candidates with their **GTT stop
prices**, and (if you keep a `holdings.csv`) which of your positions to sell.

`holdings.csv` format:
```
symbol,entry_price
TITAN,3450
```

At ₹10k you can realistically hold **1–2 names**, so act on the top 1–2 of the
list, not all ten.

---

## Files

| file | what it is |
|------|-----------|
| `config.py` | every parameter, with rationale |
| `indicators.py` | momentum score, ATR, moving averages (the math) |
| `data.py` | yfinance loader (real) + synthetic generator (for tests) |
| `backtest.py` | the engine: universe filter, weekly loop, daily stops, costs |
| `universe.py` | starter symbol list + full Nifty 500 loader |
| `run_backtest.py` | **run the historical test** |
| `run_daily.py` | **the morning report** |
| `selftest.py` | correctness checks on synthetic data |

---

## WHAT THIS IS NOT — read this

1. **Not a prediction.** It ranks *past* strength. It will hold losers through
   pullbacks and get chopped up in sideways/whippy markets. Momentum's failure
   mode is the sharp "momentum crash" after a bottom — expect it.
2. **The free-data backtest is optimistic.** yfinance is missing delisted/dead
   companies (survivorship bias) and only gives *current* market caps, not
   point-in-time. **Treat backtest numbers as an upper bound, not a forecast.**
3. **₹10k = tuition.** SEBI's own study found the majority of individual active
   traders *lose* money. Treat this capital as the price of learning the
   process, not as an investment expected to grow. Risk only what you can lose.
4. **One name at ₹10k is high-variance.** The backtest holds ~10 names to
   measure the edge; you'll hold 1–2, so your real path will swing far more
   wildly than the equity curve suggests.

## Known limitations / v2 roadmap

- **Fixed stop, not trailing.** Once a stock runs up a lot, the entry-based
  stop sits far below and stops protecting gains (the trend-exit catches the
  fall a week later). A **trailing ATR stop** is the obvious next upgrade.
- **Point-in-time market caps** would remove survivorship bias and let you
  expand below ₹5,000 cr safely.
- **Second engine + regime router** (mean-reversion for range-bound markets)
  was the long-term plan — only after this one proves itself.
- **ATR-based position sizing** once you hold enough names for it to matter.
