import yfinance as yf
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

def get_smc_market_data():
    """Calculates live Gold S/R, liquidity sweeps, rejections, EMA 20/50, and DXY impact."""
    gold_15m = yf.download("XAUUSD=X", period="5d", interval="15m", progress=False)
    gold_5m = yf.download("XAUUSD=X", period="2d", interval="5m", progress=False)
    if gold_15m.empty:
        gold_15m = yf.download("GC=F", period="5d", interval="15m", progress=False)
        gold_5m = yf.download("GC=F", period="2d", interval="5m", progress=False)

    dxy_1h = yf.download("DX-Y.NYB", period="2d", interval="1h", progress=False)

    for df in (gold_15m, gold_5m, dxy_1h):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    live_price = round(float(gold_5m["Close"].iloc[-1]), 2)
    prev_day_close = round(float(gold_15m["Close"].iloc[-96]), 2)
    pct_change = round(((live_price - prev_day_close) / prev_day_close) * 100, 2)

    # 24H Dealing Range (Resistance / Equilibrium / Support)
    dealing_range = gold_15m.tail(96)
    strong_high = round(float(dealing_range["High"].max()), 2)
    strong_low = round(float(dealing_range["Low"].min()), 2)
    equilibrium = round((strong_high + strong_low) / 2.0, 2)

    # Intraday Key Support & Resistance (Last 8 hours / 32 x 15m candles)
    intraday = gold_15m.tail(32)
    intraday_res = round(float(intraday["High"].max()), 2)
    intraday_sup = round(float(intraday["Low"].min()), 2)

    # Detect Recent Liquidity Sweeps & Candle Rejections on 15m
    last_4 = gold_15m.tail(4)
    prior_20 = gold_15m.iloc[-24:-4]
    prior_high = float(prior_20["High"].max())
    prior_low = float(prior_20["Low"].min())

    recent_high = float(last_4["High"].max())
    recent_low = float(last_4["Low"].min())
    latest_close = float(last_4["Close"].iloc[-1])

    if recent_high > prior_high and latest_close < prior_high:
        sweep_event = f"Bearish buy-side liquidity sweep & rejection above ${round(prior_high, 2)}"
    elif recent_low < prior_low and latest_close > prior_low:
        sweep_event = f"Bullish sell-side liquidity sweep & rejection below ${round(prior_low, 2)}"
    elif latest_close > equilibrium:
        sweep_event = f"Holding bullish structure above ${equilibrium} equilibrium toward ${intraday_res} resistance"
    else:
        sweep_event = f"Pressing bearish structure below ${equilibrium} equilibrium toward ${intraday_sup} support"

    # 5-Minute EMA 20 & EMA 50
    ema20 = round(float(gold_5m["Close"].ewm(span=20, adjust=False).mean().iloc[-1]), 2)
    ema50 = round(float(gold_5m["Close"].ewm(span=50, adjust=False).mean().iloc[-1]), 2)
    ema_bias = "Bullish (EMA 20 above 50)" if ema20 > ema50 else "Bearish (EMA 20 below 50)"

    # Recent 6-hour High/Low (for verifying previous predictions)
    recent_6h = gold_5m.tail(72)
    recent_6h_high = round(float(recent_6h["High"].max()), 2)
    recent_6h_low = round(float(recent_6h["Low"].min()), 2)

    # DXY Live Price, Trend & Inverse Impact on Gold
    dxy_now = round(float(dxy_1h["Close"].iloc[-1]), 2)
    dxy_6h_ago = round(float(dxy_1h["Close"].iloc[-6]), 2)
    if dxy_now > dxy_6h_ago:
        dxy_bias = f"Bullish at {dxy_now} (adding downward pressure on Gold)"
    else:
        dxy_bias = f"Bearish at {dxy_now} (giving Gold upside relief)"

    # Overall Bias Score (0 to 100, >50 Bullish, <50 Bearish)
    score = 50
    score += 15 if live_price > equilibrium else -15
    score += 15 if ema20 > ema50 else -15
    score += 15 if dxy_now < dxy_6h_ago else -15
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
