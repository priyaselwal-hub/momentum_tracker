"""
build_site.py — turn the paper-trade records into a friendly web page.

Reads paper_data/paper_state.json (+ paper_log.csv) and writes docs/index.html,
a self-contained dashboard: a paper-vs-Nifty chart, the scoreboard, open
positions, and recent trades. No external libraries, no live data fetch — it
just renders what paper_trade.py already saved, so it's fast and always works.
"""
import os, json, csv, html, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PDIR = os.path.join(HERE, "paper_data")
DOCS = os.path.join(HERE, "docs")


def _load_state():
    p = os.path.join(PDIR, "paper_state.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        return json.load(f)


def _load_log(limit=20):
    p = os.path.join(PDIR, "paper_log.csv")
    if not os.path.exists(p):
        return []
    with open(p) as f:
        rows = list(csv.DictReader(f))
    return rows[-limit:][::-1]   # most recent first


def _svg_chart(hist, w=720, h=320, pad=44):
    """Two-line SVG (paper vs Nifty), both indexed to 10,000 at the start."""
    if not hist or len(hist) < 2:
        return ('<p class="muted">The chart appears once there are at least two '
                'days of history. Check back tomorrow.</p>')
    xs = list(range(len(hist)))
    paper = [float(r[1]) for r in hist]
    nifty = [float(r[2]) for r in hist]
    lo = min(min(paper), min(nifty)); hi = max(max(paper), max(nifty))
    if hi == lo:
        hi = lo + 1
    def X(i): return pad + (w - 2 * pad) * (i / (len(xs) - 1))
    def Y(v): return pad + (h - 2 * pad) * (1 - (v - lo) / (hi - lo))
    def poly(series):
        return " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(series))
    # y gridlines at 4 levels
    grid = ""
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        y = Y(v)
        grid += (f'<line x1="{pad}" y1="{y:.1f}" x2="{w-pad}" y2="{y:.1f}" '
                 f'class="grid"/><text x="6" y="{y+4:.1f}" class="axis">'
                 f'{v/10000:.2f}x</text>')
    start_lbl = html.escape(hist[0][0]); end_lbl = html.escape(hist[-1][0])
    return f'''<svg viewBox="0 0 {w} {h}" class="chart" xmlns="http://www.w3.org/2000/svg">
  {grid}
  <polyline points="{poly(nifty)}" class="line-nifty"/>
  <polyline points="{poly(paper)}" class="line-paper"/>
  <text x="{pad}" y="{h-12}" class="axis">{start_lbl}</text>
  <text x="{w-pad}" y="{h-12}" class="axis" text-anchor="end">{end_lbl}</text>
</svg>'''


def _fmt_money(x):
    try:
        return f"&#8377;{float(x):,.0f}"
    except Exception:
        return "&#8377;0"


def main():
    os.makedirs(DOCS, exist_ok=True)
    st = _load_state()
    updated = datetime.datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")

    if not st or not st.get("equity_history"):
        body = ('<div class="card"><h2>No data yet</h2><p class="muted">The first '
                'daily run hasn\'t produced results yet. Once the workflow runs, '
                'this page will fill in automatically.</p></div>')
        _write(_page(body, updated)); print("Wrote placeholder dashboard."); return

    hist = st["equity_history"]
    paper_val = hist[-1][1]; nifty_val = hist[-1][2]
    paper_ret = paper_val / 10000 - 1
    nifty_ret = nifty_val / 10000 - 1
    excess = paper_ret - nifty_ret
    wr = (st["wins"] / st["n_closed"] * 100) if st.get("n_closed") else None
    regime = st.get("last_regime")
    regime_txt = ("RISK-ON" if regime else "RISK-OFF") if regime is not None else "—"
    regime_cls = "on" if regime else "off"

    # scoreboard cards
    def stat(label, value, cls=""):
        return f'<div class="stat"><div class="lbl">{label}</div><div class="val {cls}">{value}</div></div>'
    sign = "pos" if excess >= 0 else "neg"
    cards = (
        stat("Paper portfolio", _fmt_money(paper_val), "pos" if paper_ret >= 0 else "neg")
        + stat("Paper return", f"{paper_ret*100:+.1f}%", "pos" if paper_ret >= 0 else "neg")
        + stat("Nifty 500 (hold)", f"{nifty_ret*100:+.1f}%", "pos" if nifty_ret >= 0 else "neg")
        + stat("Excess vs Nifty", f"{excess*100:+.1f}%", sign)
        + stat("Closed trades", f"{st.get('n_closed',0)}" + (f" &middot; {wr:.0f}% win" if wr is not None else ""))
        + stat("Market regime", regime_txt, regime_cls)
    )

    # open positions
    pos = st.get("positions", {})
    if pos:
        rows = ""
        for s, p in pos.items():
            now = p.get("last_price", p["entry"])
            chg = (now / p["entry"] - 1) * 100
            cls = "pos" if chg >= 0 else "neg"
            rows += (f'<tr><td>{html.escape(s)}</td><td>{p["entry"]:.1f}</td>'
                     f'<td>{now:.1f}</td><td class="{cls}">{chg:+.1f}%</td>'
                     f'<td>{p["stop"]:.1f}</td><td>{p["shares"]}</td></tr>')
        positions = (f'<table><tr><th>Stock</th><th>Entry</th><th>Now</th>'
                     f'<th>P&amp;L</th><th>Stop</th><th>Qty</th></tr>{rows}</table>')
    else:
        positions = '<p class="muted">In cash &mdash; no open positions.</p>'

    # recent trades
    log = _load_log(20)
    if log:
        rows = ""
        for r in log:
            act = r.get("action", "")
            acls = "buy" if act == "BUY" else "sell"
            ret = r.get("ret_pct", "")
            rcls = ""
            if ret not in ("", None):
                try:
                    rcls = "pos" if float(ret) >= 0 else "neg"
                    ret = f"{float(ret):+.1f}%"
                except Exception:
                    pass
            rows += (f'<tr><td>{html.escape(r.get("date",""))}</td>'
                     f'<td class="{acls}">{html.escape(act)}</td>'
                     f'<td>{html.escape(r.get("symbol",""))}</td>'
                     f'<td>{html.escape(str(r.get("price","")))}</td>'
                     f'<td>{html.escape(str(r.get("reason","")))}</td>'
                     f'<td class="{rcls}">{html.escape(str(ret))}</td></tr>')
        trades = (f'<table><tr><th>Date</th><th>Action</th><th>Stock</th>'
                  f'<th>Price</th><th>Reason</th><th>Return</th></tr>{rows}</table>')
    else:
        trades = '<p class="muted">No trades recorded yet.</p>'

    actions = st.get("last_actions") or []
    today = ("<ul class='actions'>" + "".join(f"<li>{html.escape(a)}</li>" for a in actions)
             + "</ul>") if actions else '<p class="muted">No actions on the latest run &mdash; holding steady.</p>'

    body = f'''
    <div class="scoreboard">{cards}</div>
    <div class="card"><h2>Paper portfolio vs Nifty 500 <span class="muted">(growth of &#8377;10,000)</span></h2>
       {_svg_chart(hist)}
       <div class="legend"><span class="k-paper"></span> Strategy &nbsp;&nbsp; <span class="k-nifty"></span> Nifty 500</div>
    </div>
    <div class="grid2">
      <div class="card"><h2>Latest run &mdash; {html.escape(st.get("last_asof","") or "")}</h2>{today}</div>
      <div class="card"><h2>Open positions</h2>{positions}</div>
    </div>
    <div class="card"><h2>Recent trades</h2>{trades}</div>
    <p class="disclaimer">Paper trading only &mdash; no real money. 2-stock portfolio on &#8377;10,000,
    so results are high-variance; judge it over months, not days. Backtests for this strategy did not
    show a reliable recent edge, so treat this as a test, not a recommendation.</p>
    '''
    _write(_page(body, updated))
    print(f"Wrote dashboard with {len(hist)} day(s) of history.")


def _page(body, updated):
    return f'''<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Momentum Paper Trading</title>
<style>
 :root{{--bg:#0f1216;--card:#171c23;--ink:#e7edf3;--mut:#8a97a6;--pos:#3fb950;--neg:#f0626b;--paper:#4aa8ff;--nifty:#c9a227;--line:#232a33}}
 *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}}
 .wrap{{max-width:860px;margin:0 auto;padding:20px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:var(--mut);font-size:13px;margin-bottom:18px}}
 .card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;margin-bottom:16px}}
 h2{{font-size:15px;margin:0 0 12px;font-weight:600}}
 .scoreboard{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}}
 .stat{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}}
 .stat .lbl{{color:var(--mut);font-size:12px;margin-bottom:6px}} .stat .val{{font-size:20px;font-weight:700}}
 .pos{{color:var(--pos)}} .neg{{color:var(--neg)}} .on{{color:var(--pos)}} .off{{color:var(--mut)}}
 .muted{{color:var(--mut)}}
 table{{width:100%;border-collapse:collapse;font-size:14px}}
 th,td{{text-align:left;padding:8px 6px;border-bottom:1px solid var(--line)}} th{{color:var(--mut);font-weight:600;font-size:12px}}
 td.buy{{color:var(--pos);font-weight:600}} td.sell{{color:var(--neg);font-weight:600}}
 .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
 .actions{{margin:0;padding-left:18px}} .actions li{{margin:4px 0}}
 .chart{{width:100%;height:auto;display:block}}
 .grid{{stroke:var(--line);stroke-width:1}} .axis{{fill:var(--mut);font-size:10px}}
 .line-paper{{fill:none;stroke:var(--paper);stroke-width:2.4}} .line-nifty{{fill:none;stroke:var(--nifty);stroke-width:2;stroke-dasharray:5 4}}
 .legend{{font-size:12px;color:var(--mut);margin-top:8px}} .legend span{{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:4px}}
 .k-paper{{background:var(--paper)}} .k-nifty{{background:var(--nifty)}}
 .disclaimer{{color:var(--mut);font-size:12px;line-height:1.5;margin-top:6px}}
 @media(max-width:620px){{.scoreboard{{grid-template-columns:repeat(2,1fr)}}.grid2{{grid-template-columns:1fr}}}}
</style></head><body><div class="wrap">
<h1>Momentum Paper Trading</h1>
<div class="sub">Auto-updated daily &middot; last built {updated}</div>
{body}
</div></body></html>'''


def _write(htmltext):
    os.makedirs(DOCS, exist_ok=True)
    with open(os.path.join(DOCS, "index.html"), "w") as f:
        f.write(htmltext)


if __name__ == "__main__":
    main()
