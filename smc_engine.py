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


def find_unmitigated_fvg(df_window, live_price, min_gap=1.2):
    highs, lows = df_window["high"].values, df_window["low"].values
    n = len(df_window)
    for i in range(n - 2, 2, -1):
        if lows[i] > highs[i - 2] + min_gap:
            bot, top = round(float(highs[i - 2]), 2), round(float(lows[i]), 2)
            if np.min(lows[i + 1 :]) > bot and bot < live_price:
                return {"type": "BULLISH", "low": bot, "high": top}
        if lows[i - 2] > highs[i] + min_gap:
            bot, top = round(float(highs[i]), 2), round(float(lows[i - 2]), 2)
            if np.max(highs[i + 1 :]) < top and top > live_price:
                return {"type": "BEARISH", "low": bot, "high": top}
    return None
def find_institutional_zones(df_window, atr, live_price):
    opens, highs, lows, closes = (
        df_window["open"].values,
        df_window["high"].values,
        df_window["low"].values,
        df_window["close"].values,
    )
    # Wider, realistic Order Block thickness (at least $4.50 on Gold)
    zone_w = round(max(atr * 0.85, 4.5), 2)

    sup_list = []
    for i in range(2, len(df_window) - 2):
        if closes[i] > opens[i] and closes[i + 1] < opens[i + 1]:
            ob_h = round(float(highs[i]), 2)
            ob_l = round(min(float(opens[i]), round(ob_h - zone_w, 2)), 2)
            if ob_l > live_price + 1.0:
                sup_list.append((ob_l, ob_h))

    if sup_list:
        sup_low, sup_high = sup_list[-1]
    else:
        sup_high = max(round(float(np.max(highs)), 2), round(live_price + zone_w * 1.6, 2))
        sup_low = round(max(live_price + 1.5, sup_high - zone_w), 2)

    dem_list = []
    for i in range(2, len(df_window) - 2):
        if closes[i] < opens[i] and closes[i + 1] > opens[i + 1]:
            ob_l = round(float(lows[i]), 2)
            ob_h = round(max(float(opens[i]), round(ob_l + zone_w, 2)), 2)
            if ob_h < live_price - 1.0:
                dem_list.append((ob_l, ob_h))

    if dem_list:
        dem_low, dem_high = dem_list[-1]
    else:
        dem_low = min(round(float(np.min(lows)), 2), round(live_price - zone_w * 1.6, 2))
        dem_high = round(min(live_price - 1.5, dem_low + zone_w), 2)

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
        h1_high = round(float(df_h1.tail(48)["high"].max()), 2)
        h1_low = round(float(df_h1.tail(48)["low"].min()), 2)
    else:
        h1_struct_tag, h1_dir = "Aligned with M15", "NEUTRAL"
        h1_high = round(float(df_m15.tail(96)["high"].max()), 2)
        h1_low = round(float(df_m15.tail(96)["low"].min()), 2)

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

    # 44-bar wide mobile chart window
    chart_df = df_m15.tail(44)
    atr_m15 = compute_atr(df_m15, 14)
    sh, sl = find_swing_points(chart_df, 3, 3)
    structure_tag, struct_dir, _, _ = analyze_structure(chart_df, sh, sl)

    dem_low, dem_high, sup_low, sup_high = find_institutional_zones(chart_df, atr_m15, live_price)
    equilibrium = round((sup_high + dem_low) / 2.0, 2)
    fvg = find_unmitigated_fvg(chart_df, live_price, min_gap=max(1.2, atr_m15 * 0.25))

    # Session Liquidity Narrative
    r8 = df_m15.tail(32)
    if float(r8["high"].max()) > asia_high and live_price < asia_high:
        sweep_label = f"ASIA HIGH (${int(round(asia_high))}) SWEPT"
        pa_signal = f"London/NY swept Asian High (${asia_high}) and rejected back inside range"
    elif float(r8["low"].min()) < asia_low and live_price > asia_low:
        sweep_label = f"ASIA LOW (${int(round(asia_low))}) SWEPT"
        pa_signal = f"London/NY swept Asian Low (${asia_low}) and reclaimed structure"
    elif live_price >= equilibrium:
        sweep_label = "PREMIUM LIQUIDITY"
        pa_signal = f"Price holding in Premium above ${equilibrium} 50% equilibrium"
    else:
        sweep_label = "DISCOUNT LIQUIDITY"
        pa_signal = f"Price holding in Discount below ${equilibrium} 50% equilibrium"

    ema20 = round(float(df_m15["close"].ewm(span=20, adjust=False).mean().iloc[-1]), 2)
    ema50 = round(float(df_m15["close"].ewm(span=50, adjust=False).mean().iloc[-1]), 2)
    dxy_start = float(df_dxy["close"].iloc.__getitem__(0))
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
    invalidation = round(dem_low - max(atr_m15 * 0.6, 2.5), 2) if is_bull else round(sup_high + max(atr_m15 * 0.6, 2.5), 2)

    # Next Expansion Zones if Primary Resistance or Support Breaks
    next_bull_low = round(sup_high + max(atr_m15 * 1.1, 6.0), 2)
    next_bull_high = round(next_bull_low + max(atr_m15 * 0.8, 5.0), 2)

    next_bear_high = round(dem_low - max(atr_m15 * 1.1, 6.0), 2)
    next_bear_low = round(next_bear_high - max(atr_m15 * 0.8, 5.0), 2)


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
        "sweep_label": sweep_label,
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
        "fvg": fvg,
        "bull_tp1": next_bull_low,
        "bull_tp2": next_bull_high,
        "next_supply_zone": f"${next_bull_low} – ${next_bull_high}",
        "bear_tp1": next_bear_high,
        "bear_tp2": next_bear_low,
        "next_demand_zone": f"${next_bear_low} – ${next_bear_high}",
        "pa_signal": pa_signal,
        "dxy_now": dxy_now,
        "dxy_bias": dxy_bias,
        "bias_label": bias_label,
        "bias_score": score,
    }
