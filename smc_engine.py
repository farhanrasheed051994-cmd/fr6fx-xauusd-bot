import yfinance as yf
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

def fetch_tradingview_spot():
    """Fetches exact live OANDA:XAUUSD & TVC:DXY data from TradingView's public scanner."""
    url = "https://" + ".".join(["scanner", "tradingview", "com"]) + "/cfd/scan"
    payload = {
        "symbols": {"tickers": ["OANDA:XAUUSD", "TVC:DXY"]},
        "columns": ["close", "change", "high", "low", "EMA20|5", "EMA50|5", "High.1D", "Low.1D", "RSI"]
    }
    r = requests.post(url, json=payload, timeout=10).json()
    out = {}
    for row in r.get("data", []):
        out[row["s"]] = row["d"]
    return out

def get_smc_market_data():
    """Combines exact OANDA:XAUUSD Spot prices with SMC Resistance, Equilibrium, Support & DXY."""
    tv = fetch_tradingview_spot()
    xau = tv.get("OANDA:XAUUSD", [])
    dxy = tv.get("TVC:DXY", [])

    live_price = round(float(xau), 2)
    pct_change = round(float(xau), 2)
    ema20 = round(float(xau), 2) if xau else live_price
    ema50 = round(float(xau), 2) if xau else live_price
    strong_high = round(float(xau), 2)
    strong_low = round(float(xau), 2)
    equilibrium = round((strong_high + strong_low) / 2.0, 2)

    # Intraday S/R (midpoint between Equilibrium & Strong High/Low)
    intraday_res = round((strong_high + equilibrium) / 2.0, 2)
    intraday_sup = round((strong_low + equilibrium) / 2.0, 2)

    # Check 15m structure via yfinance (adjusted by spot-futures spread) for sweep detection & 6h verification
    gc = yf.download("GC=F", period="3d", interval="15m", progress=False)
    if isinstance(gc.columns, pd.MultiIndex):
        gc.columns = gc.columns.get_level_values(0)
    spread = round(float(gc["Close"].iloc[-1]) - live_price, 2)

    recent_6h = gc.tail(24)
    recent_6h_high = round(float(recent_6h["High"].max()) - spread, 2)
    recent_6h_low = round(float(recent_6h["Low"].min()) - spread, 2)

    if live_price >= intraday_res:
        sweep_event = f"Testing upper red resistance zone near ${strong_high}; watch for buy-side liquidity sweep & rejection"
    elif live_price <= intraday_sup:
        sweep_event = f"Testing lower blue support zone near ${strong_low}; watch for sell-side liquidity sweep & bounce"
    elif live_price > equilibrium:
        sweep_event = f"Holding bullish structure above ${equilibrium} equilibrium toward ${intraday_res} resistance"
    else:
        sweep_event = f"Trading below ${equilibrium} equilibrium with sellers targeting ${intraday_sup} support"

    ema_bias = "Bullish (EMA 20 above 50)" if ema20 > ema50 else "Bearish (EMA 20 below 50)"

    dxy_now = round(float(dxy), 2) if dxy else 104.0
    dxy_chg = float(dxy) if dxy else 0.0
    if dxy_chg > 0:
        dxy_bias = f"Bullish at {dxy_now} (+{round(dxy_chg, 2)}%, pressuring Gold)"
    else:
        dxy_bias = f"Bearish at {dxy_now} ({round(dxy_chg, 2)}%, supporting Gold)"

    score = 50
    score += 15 if live_price > equilibrium else -15
    score += 15 if ema20 > ema50 else -15
    score += 15 if dxy_chg < 0 else -15
    bias_label = "BULLISH BIAS" if score >= 55 else ("BEARISH BIAS" if score <= 45 else "NEUTRAL / RANGE")

    return {
        "live_price": live_price,
        "pct_change": pct_change,
        "strong_high": strong_high,
        "equilibrium": equilibrium,
        "strong_low": strong_low,
        "intraday_res": intraday_res,
        "intraday_sup": intraday_sup,
        "sweep_event": sweep_event,
        "ema20": ema20,
        "ema50": ema50,
        "ema_bias": ema_bias,
        "dxy_now": dxy_now,
        "dxy_bias": dxy_bias,
        "bias_label": bias_label,
        "bias_score": score,
        "recent_6h_high": recent_6h_high,
        "recent_6h_low": recent_6h_low
    }

def get_usd_fundamental_context():
    """Fetches high & medium impact USD economic drivers from ForexFactory feed."""
    try:
        resp = requests.get("https://faireconomy.media", timeout=10)
        root = ET.fromstring(resp.content)
        today_str = datetime.now(timezone.utc).strftime("%m-%d-%Y")
        events = []
        for ev in root.findall("event"):
            if ev.findtext("country") == "USD" and ev.findtext("impact") in ("High", "Medium") and ev.findtext("date") == today_str:
                events.append(f"{ev.findtext('title')} ({ev.findtext('impact')} impact, {ev.findtext('time')} UTC)")
        return events if events else ["No major red-folder USD releases today; technical liquidity & yields driving flow"]
    except Exception:
        return ["US Treasury yields & Dollar Index flow driving session volatility"]
