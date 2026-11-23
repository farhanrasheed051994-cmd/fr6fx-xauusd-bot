import time
import yfinance as yf
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

def fetch_tradingview_spot():
    url = "https://tradingview.com"
    cols = ["close", "change", "high", "low", "EMA20|5", "EMA50|5", "High.1D", "Low.1D", "RSI"]
    payload = {
        "symbols": {"tickers": ["OANDA:XAUUSD", "TVC:DXY"]},
        "columns": cols
    }
    try:
        r = requests.post(url, json=payload, timeout=10).json()
        out = {}
        for row in r.get("data", []):
            out[row.get("s")] = dict(zip(cols, row.get("d", [])))
        return out
    except Exception as e:
        print(f"⚠️ TradingView scanner warning: {e}")
        return {}

def download_gold_candles():
    """Fetches 5 days of 15m candles with retry & spot ticker fallback."""
    for ticker in ["GC=F", "XAUUSD=X"]:
        for attempt in range(2):
            try:
                df = yf.download(ticker, period="5d", interval="15m", progress=False)
                if df is not None and not df.empty and len(df) >= 20:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    return df
            except Exception as e:
                print(f"⚠️ yfinance {ticker} attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    raise RuntimeError("Failed to fetch Gold 15m candle data from Yahoo Finance.")

def get_smc_market_data():
    tv = fetch_tradingview_spot()
    xau = tv.get("OANDA:XAUUSD", {})
    dxy = tv.get("TVC:DXY", {})

    gc = download_gold_candles()

    live_price = round(float(xau.get("close") or gc["Close"].iloc[-1]), 2)
    pct_change = round(float(xau.get("change") or 0.0), 2)
    ema20 = round(float(xau.get("EMA20|5") or live_price), 2)
    ema50 = round(float(xau.get("EMA50|5") or live_price), 2)
    rsi_val = round(float(xau.get("RSI") or 50.0), 1)

    # Align candles to Spot XAUUSD price
    spread = round(float(gc["Close"].iloc[-1]) - live_price, 2)
    df = gc.copy()
    for col in ["Open", "High", "Low", "Close"]:
        df[col] = df[col] - spread

    # 1. Previous Day High (PDH) & Previous Day Low (PDL)
    prev_day = df.iloc[-192:-96] if len(df) >= 192 else df.iloc[:-48]
    pdh = round(float(prev_day["High"].max()), 2)
    pdl = round(float(prev_day["Low"].min()), 2)

    # 2. Current 24H Dealing Range (Strong High / 50% Equilibrium / Strong Low)
    today_range = df.tail(96)
    strong_high = round(max(float(today_range["High"].max()), float(xau.get("High.1D") or 0)), 2)
    strong_low = round(min(float(today_range["Low"].min()), float(xau.get("Low.1D") or 99999)), 2)
    equilibrium = round((strong_high + strong_low) / 2.0, 2)

    # 3. Session Highs & Lows (Asian: 00-07 UTC | London: 07-13 UTC | NY: 13-21 UTC)
    df_utc = df.tz_convert("UTC") if df.index.tz is not None else df.tz_localize("UTC")
    last_24h = df_utc.tail(96)

    asia_df = last_24h[(last_24h.index.hour >= 0) & (last_24h.index.hour < 7)]
    london_df = last_24h[(last_24h.index.hour >= 7) & (last_24h.index.hour < 13)]
    ny_df = last_24h[(last_24h.index.hour >= 13) & (last_24h.index.hour < 21)]

    asia_high = round(float(asia_df["High"].max()), 2) if not asia_df.empty else strong_high
    asia_low = round(float(asia_df["Low"].min()), 2) if not asia_df.empty else strong_low
    london_high = round(float(london_df["High"].max()), 2) if not london_df.empty else strong_high
    london_low = round(float(london_df["Low"].min()), 2) if not london_df.empty else strong_low
    ny_high = round(float(ny_df["High"].max()), 2) if not ny_df.empty else strong_high
    ny_low = round(float(ny_df["Low"].min()), 2) if not ny_df.empty else strong_low

    # 4. Institutional Supply & Demand Order Block Zones (Top 14% & Bottom 14% of dealing range)
    zone_thickness = round(max((strong_high - strong_low) * 0.14, 3.5), 2)
    supply_zone = f"${round(strong_high - zone_thickness, 2)} – ${strong_high}"
    demand_zone = f"${strong_low} – ${round(strong_low + zone_thickness, 2)}"

    # Retest Pivot Levels
    retest_res = round((strong_high + equilibrium) / 2.0, 2)
    retest_sup = round((strong_low + equilibrium) / 2.0, 2)

    # 5. Detect 15m Fair Value Gap (FVG / Imbalance)
    fvg_note = "No fresh 15m Fair Value Gap; watching order block retests"
    for idx in range(len(df) - 3, max(len(df) - 20, 2), -1):
        c1_high = float(df["High"].iloc[idx - 2])
        c3_low = float(df["Low"].iloc[idx])
        c1_low = float(df["Low"].iloc[idx - 2])
        c3_high = float(df["High"].iloc[idx])
        if c3_low > c1_high + 1.5:
            fvg_note = f"Bullish 15m FVG (Imbalance) at ${round(c1_high, 2)} – ${round(c3_low, 2)}"
            break
        if c1_low > c3_high + 1.5:
            fvg_note = f"Bearish 15m FVG (Imbalance) at ${round(c3_high, 2)} – ${round(c1_low, 2)}"
            break

    # 6. Liquidity Sweep & Price Action Diagnostic
    recent_6h = df.tail(24)
    recent_6h_high = round(float(recent_6h["High"].max()), 2)
    recent_6h_low = round(float(recent_6h["Low"].min()), 2)

    if recent_6h_high > asia_high and live_price < asia_high:
        pa_signal = f"Buy-side liquidity swept above Asian High (${asia_high}) with bearish rejection back inside range"
    elif recent_6h_low < asia_low and live_price > asia_low:
        pa_signal = f"Sell-side liquidity swept below Asian Low (${asia_low}) with bullish rejection & reclaim"
    elif recent_6h_high > pdh and live_price < pdh:
        pa_signal = f"Fakeout liquidity raid above Previous Day High (${pdh}); sellers defending supply"
    elif recent_6h_low < pdl and live_price > pdl:
        pa_signal = f"Stop-hunt sweep below Previous Day Low (${pdl}); buyers defending demand"
    elif live_price > equilibrium:
        pa_signal = f"Bullish market structure holding above ${equilibrium} equilibrium; eyeing ${pdh} PDH liquidity"
    else:
        pa_signal = f"Bearish market structure below ${equilibrium} equilibrium; targeting ${pdl} PDL liquidity"

    ema_bias = "Bullish (EMA 20 above 50)" if ema20 > ema50 else "Bearish (EMA 20 below 50)"

    dxy_now = round(float(dxy.get("close") or 104.0), 2)
    dxy_chg = float(dxy.get("change") or 0.0)
    if dxy_chg > 0:
        dxy_bias = f"Bullish at {dxy_now} (+{round(dxy_chg, 2)}%, pressuring Gold lower)"
    else:
        dxy_bias = f"Bearish at {dxy_now} ({round(dxy_chg, 2)}%, supporting Gold upside)"

    score = 50
    score += 15 if live_price > equilibrium else -15
    score += 15 if ema20 > ema50 else -15
    score += 15 if dxy_chg < 0 else -15
    bias_label = "BULLISH BIAS" if score >= 55 else ("BEARISH BIAS" if score <= 45 else "NEUTRAL / RANGE")

    return {
        "live_price": live_price,
        "pct_change": pct_change,
        "pdh": pdh,
        "pdl": pdl,
        "asia_high": asia_high,
        "asia_low": asia_low,
        "london_high": london_high,
        "london_low": london_low,
        "ny_high": ny_high,
        "ny_low": ny_low,
        "strong_high": strong_high,
        "equilibrium": equilibrium,
        "strong_low": strong_low,
        "supply_zone": supply_zone,
        "demand_zone": demand_zone,
        "retest_res": retest_res,
        "retest_sup": retest_sup,
        "fvg_note": fvg_note,
        "pa_signal": pa_signal,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi_val,
        "ema_bias": ema_bias,
        "dxy_now": dxy_now,
        "dxy_bias": dxy_bias,
        "bias_label": bias_label,
        "bias_score": score,
        "recent_6h_high": recent_6h_high,
        "recent_6h_low": recent_6h_low
    }

def get_usd_fundamental_context():
    """Fetches today's High & Medium impact USD economic calendar events."""
    try:
        resp = requests.get(
            "https://faireconomy.media",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        root = ET.fromstring(resp.content)
        today_str = datetime.now(timezone.utc).strftime("%m-%d-%Y")
        events = []
        for ev in root.findall("event"):
            if (
                ev.findtext("country") == "USD"
                and ev.findtext("impact") in ("High", "Medium")
                and ev.findtext("date") == today_str
            ):
                events.append(f"• {ev.findtext('title')} [{ev.findtext('impact')} Impact — {ev.findtext('time')} UTC]")
        return events if events else ["• No major red-folder USD releases today; session liquidity & yields driving flow"]
    except Exception as e:
        print(f"⚠️ Economic calendar fetch warning: {e}")
        return ["• US Treasury yields & Dollar Index flow driving session volatility"]
