import os
import json
import numpy as np
import pandas as pd

MT5_DATA_PATH = os.path.join("data", "mt5_data.json")


def load_mt5_df(records):
    df = pd.DataFrame(records)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.set_index("time", inplace=True)
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    df["volume"] = df["volume"].astype(int)
    return df


def compute_atr(df, period=14):
    high, low, prev_close = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def find_swing_points(df, left=3, right=3):
    highs, lows, times = df["high"].values, df["low"].values, df.index
    swing_highs, swing_lows = [], []
    for i in range(left, len(df) - right):
        if highs[i] == np.max(highs[i - left : i + right + 1]):
            swing_highs.append({"idx": i, "time": times[i], "price": round(float(highs[i]), 2)})
        if lows[i] == np.min(lows[i - left : i + right + 1]):
            swing_lows.append({"idx": i, "time": times[i], "price": round(float(lows[i]), 2)})
    return swing_highs, swing_lows


def analyze_structure(df, swing_highs, swing_lows):
    close_now = float(df["close"].iloc[-1])
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        sh = swing_highs[-1]["price"] if swing_highs else round(float(df["high"].max()), 2)
        sl = swing_lows[-1]["price"] if swing_lows else round(float(df["low"].min()), 2)
        return f"Range (${sl} – ${sh})", "NEUTRAL", sh, sl

    last_sh, prev_sh = swing_highs[-1]["price"], swing_highs[-2]["price"]
    last_sl, prev_sl = swing_lows[-1]["price"], swing_lows[-2]["price"]

    if close_now > last_sh and last_sl > prev_sl:
        return f"Bullish BOS above ${last_sh}", "BULLISH", last_sh, last_sl
    if close_now < last_sl and last_sh < prev_sh:
        return f"Bearish BOS below ${last_sl}", "BEARISH", last_sh, last_sl
    if close_now > last_sh:
        return f"Bullish CHoCH above ${last_sh}", "BULLISH", last_sh, last_sl
    if close_now < last_sl:
        return f"Bearish CHoCH below ${last_sl}", "BEARISH", last_sh, last_sl
    if last_sh > prev_sh and last_sl > prev_sl:
        return f"Bullish Trend (HL ${last_sl})", "BULLISH", last_sh, last_sl
    if last_sh < prev_sh and last_sl < prev_sl:
        return f"Bearish Trend (LH ${last_sh})", "BEARISH", last_sh, last_sl
    return f"Consolidation (${last_sl} – ${last_sh})", "NEUTRAL", last_sh, last_sl
def find_clean_zones(df_window, atr, live_price):
    opens, highs, lows, closes = (
        df_window["open"].values,
        df_window["high"].values,
        df_window["low"].values,
        df_window["close"].values,
    )
    pad = round(max(atr * 0.45, 2.5), 2)

    sup_list = []
    for i in range(2, len(df_window) - 2):
        if closes[i] > opens[i] and closes[i + 1] < opens[i + 1]:
            ob_h = round(float(highs[i]), 2)
            ob_l = round(float(max(opens[i], ob_h - pad)), 2)
            if ob_l > live_price + 1.5:
                sup_list.append((ob_l, ob_h))

    if sup_list:
        sup_low, sup_high = sup_list[-1]
    else:
        sup_high = max(round(float(np.max(highs)), 2), round(live_price + pad * 2, 2))
        sup_low = round(max(live_price + 1.5, sup_high - pad), 2)

    dem_list = []
    for i in range(2, len(df_window) - 2):
        if closes[i] < opens[i] and closes[i + 1] > opens[i + 1]:
            ob_l = round(float(lows[i]), 2)
            ob_h = round(float(min(opens[i], ob_l + pad)), 2)
            if ob_h < live_price - 1.5:
                dem_list.append((ob_l, ob_h))

    if dem_list:
        dem_low, dem_high = dem_list[-1]
    else:
        dem_low = min(round(float(np.min(lows)), 2), round(live_price - pad * 2, 2))
        dem_high = round(min(live_price - 1.5, dem_low + pad), 2)

    return dem_low, dem_high, sup_low, sup_high


def get_smc_market_data():
    with open(MT5_DATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    df_m15 = load_mt5_df(raw["xau_m15"])
    df_m5 = load_mt5_df(raw["xau_m5"])
    df_dxy = load_mt5_df(raw["dxy_m15"])
    df_h1 = load_mt5_df(raw["xau_h1"]) if raw.get("xau_h1") else None

    live_price = round(float(raw.get("gold_bid") or df_m5["close"].iloc[-1]), 2)
    dxy_now = round(float(raw.get("dxy_bid") or df_dxy["close"].iloc[-1]), 2)

    if df_h1 is not None and len(df_h1) >= 20:
        h1_sh, h1_sl = find_swing_points(df_h1.tail(60), 3, 3)
        h1_struct_tag, h1_dir, _, _ = analyze_structure(df_h1.tail(60), h1_sh, h1_sl)
    else:
        h1_struct_tag, h1_dir = "Aligned with M15", "NEUTRAL"

    unique_dates = sorted(df_m15.index.normalize().unique())
    prev_day = df_m15[df_m15.index.normalize() == unique_dates[-2]] if len(unique_dates) >= 2 else df_m15.iloc[:-96]
    today_df = df_m15[df_m15.index.normalize() == unique_dates[-1]] if len(unique_dates) >= 2 else df_m15.tail(96)

    pdh = round(float(prev_day["high"].max()), 2)
    pdl = round(float(prev_day["low"].min()), 2)
    prev_close = float(prev_day["close"].iloc[-1])
    pct_change = round(((live_price - prev_close) / prev_close) * 100.0, 2)

    asia_df = today_df[(today_df.index.hour >= 0) & (today_df.index.hour < 7)]
    asia_high = round(float(asia_df["high"].max()), 2) if not asia_df.empty else pdh
    asia_low = round(float(asia_df["low"].min()), 2) if not asia_df.empty else pdl

    # 38-bar window = chunky, zoomed-in mobile candles + exact sync with chart_renderer.py
    chart_df = df_m15.tail(38)
    atr_m15 = compute_atr(df_m15, 14)
    sh, sl = find_swing_points(chart_df, 3, 3)
    structure_tag, struct_dir, _, _ = analyze_structure(chart_df, sh, sl)

    dem_low, dem_high, sup_low, sup_high = find_clean_zones(chart_df, atr_m15, live_price)
    equilibrium = round((sup_high + dem_low) / 2.0, 2)

    r6 = df_m15.tail(24)
    if float(r6["high"].max()) > asia_high and live_price < asia_high:
        pa_signal = f"Asian High (${asia_high}) swept; bearish rejection active"
    elif float(r6["low"].min()) < asia_low and live_price > asia_low:
        pa_signal = f"Asian Low (${asia_low}) swept; bullish reclaim active"
    elif live_price >= equilibrium:
        pa_signal = f"Trading in Premium above ${equilibrium} equilibrium"
    else:
        pa_signal = f"Trading in Discount below ${equilibrium} equilibrium"

    ema20 = round(float(df_m15["close"].ewm(span=20, adjust=False).mean().iloc[-1]), 2)
    ema50 = round(float(df_m15["close"].ewm(span=50, adjust=False).mean().iloc[-1]), 2)
    dxy_start = float(df_dxy["close"].iloc)
    dxy_chg = round(((dxy_now - dxy_start) / dxy_start) * 100.0, 2)
    dxy_bias = f"{dxy_now} ({'+' if dxy_chg >= 0 else ''}{dxy_chg}%)"

    score = 50
    score += 15 if h1_dir == "BULLISH" else (-15 if h1_dir == "BEARISH" else 0)
    score += 15 if struct_dir == "BULLISH" else (-15 if struct_dir == "BEARISH" else 0)
    score += 10 if ema20 > ema50 else -10
    score += 10 if dxy_chg < -0.05 else (-10 if dxy_chg > 0.05 else 0)

    bias_label = "BULLISH BIAS" if score >= 60 else ("BEARISH BIAS" if score <= 40 else "RANGE SETUP")
    is_bull = score >= 50

    watch_low = dem_low if is_bull else sup_low
    watch_high = dem_high if is_bull else sup_high
    invalidation = round(dem_low - max(atr_m15 * 0.5, 2.0), 2) if is_bull else round(sup_high + max(atr_m15 * 0.5, 2.0), 2)

    return {
        "live_price": live_price,
        "pct_change": pct_change,
        "atr_m15": round(atr_m15, 2),
        "h1_structure": h1_struct_tag,
        "structure_tag": structure_tag,
        "struct_dir": struct_dir,
        "pdh": pdh,
        "pdl": pdl,
        "asia_high": asia_high,
        "asia_low": asia_low,
        "strong_high": sup_high,
        "strong_low": dem_low,
        "equilibrium": equilibrium,
        "supply_zone": f"${sup_low} – ${sup_high}",
        "demand_zone": f"${dem_low} – ${dem_high}",
        "supply_low": sup_low,
        "supply_high": sup_high,
        "demand_low": dem_low,
        "demand_high": dem_high,
        "watch_low": watch_low,
        "watch_high": watch_high,
        "invalidation": invalidation,
        "bull_tp1": sup_low,
        "bull_tp2": round(max(sup_high, pdh), 2),
        "bear_tp1": dem_high,
        "bear_tp2": round(min(dem_low, pdl), 2),
        "pa_signal": pa_signal,
        "dxy_now": dxy_now,
        "dxy_bias": dxy_bias,
        "bias_label": bias_label,
        "bias_score": score,
    }
