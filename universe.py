"""
universe.py — which stocks to scan.

For a first real run, STARTER_UNIVERSE below is a hand-picked set of liquid
large/mid-cap NSE symbols (symbols only, no .NS suffix — the loader adds it).
It is a convenience sample, NOT the production universe.

For the real strategy you want the full Nifty 500 (then let the engine's own
market-cap + turnover filters trim it). load_nifty500_symbols() pulls the
official list from NSE's published CSV — this works on YOUR machine (this
sandbox blocks NSE). If it fails (NSE changes the URL/headers), download the
CSV manually from niftyindices.com and read the 'Symbol' column.
"""

STARTER_UNIVERSE = [
    "RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY","HINDUNILVR","ITC","SBIN",
    "BHARTIARTL","KOTAKBANK","LT","AXISBANK","BAJFINANCE","ASIANPAINT","MARUTI",
    "TITAN","SUNPHARMA","NESTLEIND","ULTRACEMCO","WIPRO","ONGC","NTPC","POWERGRID",
    "M&M","TATAMOTORS","TATASTEEL","JSWSTEEL","HCLTECH","TECHM","ADANIENT",
    "ADANIPORTS","COALINDIA","GRASIM","HINDALCO","DRREDDY","CIPLA","DIVISLAB",
    "BAJAJFINSV","BRITANNIA","EICHERMOT","HEROMOTOCO","BPCL","IOC","SHREECEM",
    "PIDILITIND","DABUR","GODREJCP","HAVELLS","SIEMENS","DLF","TRENT","VBL",
    "BANKBARODA","PNB","CANBK","INDUSINDBK","BEL","HAL","BOSCHLTD","PAGEIND",
    "ABB","CUMMINSIND","POLYCAB","TVSMOTOR","MUTHOOTFIN","TATAPOWER","ZOMATO",
    "PERSISTENT","COFORGE","MPHASIS","LTIM","NAUKRI","INDHOTEL","ASHOKLEY",
]

def load_nifty500_symbols():
    """Pull the official Nifty 500 constituents from NSE (runs on your machine).
    Returns a list of NSE symbols (no suffix)."""
    import io, requests, pandas as pd
    url = ("https://niftyindices.com/IndexConstituent/"
           "ind_nifty500list.csv")
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    # CSV has a 'Symbol' column
    col = next(c for c in df.columns if c.strip().lower() == "symbol")
    return df[col].astype(str).str.strip().tolist()
