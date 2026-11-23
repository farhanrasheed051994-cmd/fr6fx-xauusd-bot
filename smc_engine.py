import time
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime, timezone

def fetch_tradingview_spot():
    url = "https://tradingview.com"
    cols = ("close", "change", "high", "low", "EMA20|5", "EMA50|5", "High.1D", "Low.1D", "RSI")
    payload = {
        "symbols": {"tickers": ("OANDA:XAUUSD", "TVC:DXY")},
        "columns": list(cols)
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Origin": "https://tradingview.com",
        "Referer": "https://tradingview.com/",
        "Content-Type": "application/json"
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        if resp.status_code != 200 or not resp.text.strip():
            print(f"⚠️ TradingView scanner status {resp.status_code}—using Yahoo spot fallback")
            return {}
        r = resp.json()
        out = {}
        for row in r.get("data", ()):
            out.update({row.get("s"): dict(zip(cols, row.get("d", ())))})
        return out
    except Exception as e:
        print(f"⚠️ TradingView scanner warning: {e}")
        return {}

def download_gold_candles():
    for ticker in ("GC=F", "XAUUSD=X"):
        for attempt in range(2):
            try:
                df = yf.download(ticker, period="5d", interval="15m", progress=False)
                if df is not None and not df.empty and len(df) >= 40:
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    return df
            except Exception as e:
                print(f"⚠️ yfinance {ticker} attempt {attempt + 1} failed: {e}")
            time.sleep(2)
    raise RuntimeError("Failed to fetch Gold 15m candle data from Yahoo Finance.")

def detect_market_structure(df_intraday, live_price):
    highs = df_intraday.get("High").values
    lows = df_intraday.get("Low").values
    closes = df_intraday.get("Close").values
    n = len(df_intraday)

    swing_highs = list()
    swing_lows = list()
    for i in range(2, n - 2):
        h_val = float(highs.__getitem__(i))
        l_val = float(lows.__getitem__(i))
        if (
            h_val >= float(highs.__getitem__(i - 1))
            and h_val >= float(highs.__getitem__(i - 2))
            and h_val >= float(highs.__getitem__(i + 1))
            and h_val >= float(highs.__getitem__(i + 2))
        ):
            swing_highs.append(round(h_val, 2))
        if (
            l_val <= float(lows.__getitem__(i - 1))
            and l_val <= float(lows.__getitem__(i - 2))
            and l_val <= float(lows.__getitem__(i + 1))
            and l_val <= float(lows.__getitem__(i + 2))
        ):
            swing_lows.append(round(l_val, 2))

    last_sh = swing_highs.__getitem__(len(swing_highs) - 1) if swing_highs else round(float(df_intraday.get("High").max()), 2)
    last_sl = swing_lows.__getitem__(len(swing_lows) - 1) if swing_lows else round(float(df_intraday.get("Low").min()), 2)
    recent_close = float(closes.__getitem__(n - 1))

    if recent_close > last_sh:
        structure_tag = f"Bullish BOS above ${last_sh}"
    elif recent_close < last_sl:
        structure_tag = f"Bearish BOS below ${last_sl}"
    elif len(swing_highs) >= 2 and swing_highs.__getitem__(len(swing_highs) - 1) < swing_highs.__getitem__(len(swing_highs) - 2):
        structure_tag = f"Bearish CHoCH / Lower High at ${last_sh}"
    elif len(swing_lows) >= 2 and swing_lows.__getitem__(len(swing_lows) - 1) > swing_lows.__getitem__(len(swing_lows) - 2):
        structure_tag = f"Bullish CHoCH / Higher Low at ${last_sl}"
    else:
        structure_tag = f"Intraday Range (${last_sl} – ${last_sh})"

    return structure_tag, last_sh, last_sl
def get_smc_market_data():
    tv = fetch_tradingview_spot()
    xau = tv.get("OANDA:XAUUSD", {})
    dxy = tv.get("TVC:DXY", {})

    gc = download_gold_candles()
    last_gc_close = float(gc.get("Close").iloc.__getitem__(len(gc) - 1))

    live_price = round(float(xau.get("close") or last_gc_close), 2)
    pct_change = round(float(xau.get("change") or 0.0), 2)
    ema20 = round(float(xau.get("EMA20|5") or live_price), 2)
    ema50 = round(float(xau.get("EMA50|5") or live_price), 2)
    rsi_val = round(float(xau.get("RSI") or 50.0), 1)

    spread = round(last_gc_close - live_price, 2)
    df = gc.copy()
    for col in ("Open", "High", "Low", "Close"):
        df.__setitem__(col, df.get(col) - spread)

    prev_day = df.iloc.__getitem__(slice(-192, -96)) if len(df) >= 192 else df.iloc.__getitem__(slice(None, -48))
    pdh = round(float(prev_day.get("High").max()), 2)
    pdl = round(float(prev_day.get("Low").min()), 2)

    macro_24h = df.tail(96)
    macro_high = round(max(float(macro_24h.get("High").max()), float(xau.get("High.1D") or 0)), 2)
    macro_low = round(min(float(macro_24h.get("Low").min()), float(xau.get("Low.1D") or 99999)), 2)

    intraday_df = df.tail(40)
    strong_high = round(float(intraday_df.get("High").max()), 2)
    strong_low = round(float(intraday_df.get("Low").min()), 2)
    if (strong_high - strong_low) < 10.0:
        wider_df = df.tail(64)
        strong_high = round(float(wider_df.get("High").max()), 2)
        strong_low = round(float(wider_df.get("Low").min()), 2)

    equilibrium = round((strong_high + strong_low) / 2.0, 2)

    df_utc = df.tz_convert("UTC") if df.index.tz is not None else df.tz_localize("UTC")
    last_24h = df_utc.tail(96)

    asia_df = last_24h.loc.__getitem__((last_24h.index.hour >= 0) & (last_24h.index.hour < 7))
    london_df = last_24h.loc.__getitem__((last_24h.index.hour >= 7) & (last_24h.index.hour < 13))
    ny_df = last_24h.loc.__getitem__((last_24h.index.hour >= 13) & (last_24h.index.hour < 21))

    asia_high = round(float(asia_df.get("High").max()), 2) if not asia_df.empty else strong_high
    asia_low = round(float(asia_df.get("Low").min()), 2) if not asia_df.empty else strong_low
    london_high = round(float(london_df.get("High").max()), 2) if not london_df.empty else strong_high
    london_low = round(float(london_df.get("Low").min()), 2) if not london_df.empty else strong_low
    ny_high = round(float(ny_df.get("High").max()), 2) if not ny_df.empty else strong_high
    ny_low = round(float(ny_df.get("Low").min()), 2) if not ny_df.empty else strong_low

    zone_thickness = round(max((strong_high - strong_low) * 0.16, 2.8), 2)
    supply_low = round(strong_high - zone_thickness, 2)
    demand_high = round(strong_low + zone_thickness, 2)
    supply_zone = f"${supply_low} – ${strong_high}"
    demand_zone = f"${strong_low} – ${demand_high}"

    retest_res = supply_low
    retest_sup = demand_high

    fvg_note = "No unmitigated 15m Fair Value Gap; watching Order Block retests"
    fvg_type = "NONE"
    fvg_top = 0.0
    fvg_bottom = 0.0
    for idx in range(len(intraday_df) - 3, 2, -1):
        c1_high = float(intraday_df.get("High").iloc.__getitem__(idx - 2))
        c3_low = float(intraday_df.get("Low").iloc.__getitem__(idx))
        c1_low = float(intraday_df.get("Low").iloc.__getitem__(idx - 2))
        c3_high = float(intraday_df.get("High").iloc.__getitem__(idx))
        if c3_low > c1_high + 1.2:
            fvg_type = "BULLISH"
            fvg_bottom = round(c1_high, 2)
            fvg_top = round(c3_low, 2)
            fvg_note = f"Bullish 15m Fair Value Gap at ${fvg_bottom} – ${fvg_top}"
            break
        if c1_low > c3_high + 1.2:
            fvg_type = "BEARISH"
            fvg_bottom = round(c3_high, 2)
            fvg_top = round(c1_low, 2)
            fvg_note = f"Bearish 15m Fair Value Gap at ${fvg_bottom} – ${fvg_top}"
            break

    structure_tag, swing_high_ref, swing_low_ref = detect_market_structure(intraday_df, live_price)

    recent_6h = df.tail(24)
    recent_6h_high = round(float(recent_6h.get("High").max()), 2)
    recent_6h_low = round(float(recent_6h.get("Low").min()), 2)

    if recent_6h_high > asia_high and live_price < asia_high:
        pa_signal = f"Buy side liquidity swept above Asian High (${asia_high}) with bearish rejection ({structure_tag})"
    elif recent_6h_low < asia_low and live_price > asia_low:
        pa_signal = f"Sell side liquidity swept below Asian Low (${asia_low}) with bullish reclaim ({structure_tag})"
    elif recent_6h_high > pdh and live_price < pdh:
        pa_signal = f"Liquidity raid above Previous Day High (${pdh}); sellers defending supply ({structure_tag})"
    elif recent_6h_low < pdl and live_price > pdl:
        pa_signal = f"Stop-hunt sweep below Previous Day Low (${pdl}); buyers defending demand ({structure_tag})"
    elif live_price > equilibrium:
        pa_signal = f"Premium structure holding above ${equilibrium} equilibrium ({structure_tag})"
    else:
        pa_signal = f"Discount structure below ${equilibrium} equilibrium ({structure_tag})"

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
        "macro_high": macro_high,
        "macro_low": macro_low,
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
        "fvg_type": fvg_type,
        "fvg_top": fvg_top,
        "fvg_bottom": fvg_bottom,
        "structure_tag": structure_tag,
        "swing_high_ref": swing_high_ref,
        "swing_low_ref": swing_low_ref,
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
    try:
        resp = requests.get(
            "https://faireconomy.media",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        data = resp.json()
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        events = list()
        for ev in data:
            if (
                ev.get("country") == "USD"
                and ev.get("impact") in ("High", "Medium")
                and str(ev.get("date", "")).startswith(today_iso)
            ):
                dt_str = str(ev.get("date", ""))
                ev_time = dt_str.__getitem__(slice(11, 16)) if len(dt_str) >= 16 else "TBD"
                events.append(f"• {ev.get('title')} ({ev.get('impact')} Impact — {ev_time} UTC)")
        return events if events else list(("• No major red-folder USD releases today; session liquidity & yields driving flow",))
    except Exception as e:
        print(f"⚠️ Economic calendar fetch warning: {e}")
        return list(("• US Treasury yields & Dollar Index flow driving session volatility",))
