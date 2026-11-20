import yfinance as yf
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

def get_smc_market_data():
    """Calculates live Gold price, Strong High/Low, 50% Equilibrium, EMAs, and DXY bias."""
    gold_15m = yf.download("GC=F", period="5d", interval="15m", progress=False)
    gold_5m = yf.download("GC=F", period="2d", interval="5m", progress=False)
    dxy_1h = yf.download("DX-Y.NYB", period="2d", interval="1h", progress=False)

    for df in (gold_15m, gold_5m, dxy_1h):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    live_price = round(float(gold_5m["Close"].iloc[-1]), 2)
    prev_day_close = round(float(gold_15m["Close"].iloc[-96]), 2)
    pct_change = round(((live_price - prev_day_close) / prev_day_close) * 100, 2)

    # Smart Money Dealing Range (Last 24h / 96 x 15m candles)
    dealing_range = gold_15m.tail(96)
    strong_high = round(float(dealing_range["High"].max()), 2)
    strong_low = round(float(dealing_range["Low"].min()), 2)
    equilibrium = round((strong_high + strong_low) / 2.0, 2)

    # 5-Minute EMA 20 & EMA 50
    ema20 = round(float(gold_5m["Close"].ewm(span=20, adjust=False).mean().iloc[-1]), 2)
    ema50 = round(float(gold_5m["Close"].ewm(span=50, adjust=False).mean().iloc[-1]), 2)

    # Recent 6-hour High/Low (for verifying if previous session call played out)
    recent_6h = gold_5m.tail(72)
    recent_6h_high = round(float(recent_6h["High"].max()), 2)
    recent_6h_low = round(float(recent_6h["Low"].min()), 2)

    # DXY Trend
    dxy_now = float(dxy_1h["Close"].iloc[-1])
    dxy_6h_ago = float(dxy_1h["Close"].iloc[-6])
    dxy_bias = "BULLISH (pressuring Gold)" if dxy_now > dxy_6h_ago else "BEARISH (supporting Gold)"

    # Market Position Status
    if live_price > equilibrium:
        zone_status = "trading in the upper RED PREMIUM ZONE above 50% Equilibrium"
    elif live_price < equilibrium:
        zone_status = "trading in the lower BLUE DISCOUNT ZONE below 50% Equilibrium"
    else:
        zone_status = "testing exact 50% EQUILIBRIUM"

    return {
        "live_price": live_price,
        "pct_change": pct_change,
        "strong_high": strong_high,
        "equilibrium": equilibrium,
        "strong_low": strong_low,
        "ema20": ema20,
        "ema50": ema50,
        "dxy_bias": dxy_bias,
        "zone_status": zone_status,
        "recent_6h_high": recent_6h_high,
        "recent_6h_low": recent_6h_low
    }

def get_usd_high_impact_news():
    """Checks ForexFactory free weekly feed for red-folder USD events today."""
    try:
        resp = requests.get("https://faireconomy.media", timeout=10)
        root = ET.fromstring(resp.content)
        today_str = datetime.now(timezone.utc).strftime("%m-%d-%Y")
        events = []
        for ev in root.findall("event"):
            if ev.findtext("country") == "USD" and ev.findtext("impact") == "High" and ev.findtext("date") == today_str:
                events.append(f"{ev.findtext('title')} ({ev.findtext('time')} UTC)")
        return events if events else ["No major red-folder USD news today"]
    except Exception:
        return ["Standard session liquidity"]
