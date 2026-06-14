"""
selftest.py — correctness checks on SYNTHETIC data.

Proves the MACHINERY is correct. Says NOTHING about real-world profit.
The synthetic market has 14 genuine up-trends, 8 choppy names, 5 down-trends,
one name that triples then crashes, and one sub-floor tiddler — so we can assert
the engine does the right STRUCTURAL things:

  [1] runs end-to-end and produces an equity curve
  [2] the cap floor screens out the sub-5000cr name (TINY_1 never bought)
  [3] buys are overwhelmingly trend names; down-trends are a tiny minority
  [4] it actually holds a diversified set of the trend names
  [5] the daily ATR catastrophe stop fires, and a crashed name is ejected (not held)
  [6] costs are charged and churn is controlled (cost drag stays modest)
"""
import re
from collections import Counter
import data, backtest as bt

def _grp(t):
    return re.sub(r"_\d+$", "", t).replace("_X", "")

def main():
    panel, index, mcap = data.make_synthetic(n_days=1000, seed=7)
    res = bt.run(panel, index, mcap)
    m, trades = res["metrics"], res["trades"]
    buys = res["buy_log"]
    final = set(res["final_holdings"])

    bc = Counter(_grp(t) for t in buys)
    total_buys = max(len(buys), 1)
    trend_share = bc.get("TREND", 0) / total_buys
    down_share  = bc.get("DOWN", 0) / total_buys
    distinct_trend_held = len({t for t in buys if t.startswith("TREND_")})
    atr_fired = int((trades["reason"] == "atr_stop").sum()) if len(trades) else 0

    checks = [
        ("[1] engine produced an equity curve",             len(res["equity"]) > 500),
        ("[2] TINY_1 (1200cr < 5000cr floor) never bought",  "TINY_1" not in buys),
        (f"[3] trends are the top bucket ({trend_share:.0%}) vs chop/down; downs rare ({down_share:.0%})",
                                                 trend_share > bc.get("CHOP",0)/total_buys
                                                 and trend_share > down_share
                                                 and down_share <= 0.10),
        (f"[4] holds a diversified set of trends ({distinct_trend_held} names)",
                                                 distinct_trend_held >= 8),
        (f"[5] ATR stop fired ({atr_fired}x) & CRASH_X ejected",
                                                 atr_fired >= 1 and "CRASH_X" not in final),
        (f"[6] costs charged & churn controlled (drag {m['cost_pct_of_initial']:.1%})",
                                                 m["total_cost"] > 0 and m["cost_pct_of_initial"] < 0.08),
    ]

    print("=" * 66)
    print("SELF-TEST ON SYNTHETIC DATA  (correctness only, NOT performance)")
    print("=" * 66)
    for label, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print("-" * 66)
    print("Structural diagnostics (synthetic — NOT real returns):")
    print(f"   buys by group        : {dict(bc)}")
    print(f"   total buys / sells   : {m['n_buys']} / {m['n_sells']}")
    print(f"   exit reasons         : "
          f"{dict(trades['reason'].value_counts()) if len(trades) else {}}")
    if len(trades):
        mr = trades.groupby('reason')['ret'].mean()
        print(f"   avg return by exit   : { {k: round(v,3) for k,v in mr.items()} }")
    print(f"   win rate             : {m['win_rate']:.0%}")
    print(f"   cost drag over run   : {m['cost_pct_of_initial']:.2%}")
    all_ok = all(ok for _, ok in checks)
    print("-" * 66)
    print("RESULT:", "ALL CHECKS PASSED" if all_ok else "SOME CHECKS FAILED")
    print("=" * 66)
    return all_ok

if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
