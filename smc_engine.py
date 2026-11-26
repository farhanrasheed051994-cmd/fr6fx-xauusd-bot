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
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return float(tr.rolling(period).mean().iloc[-1])


def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = rsi.iloc[-1]
    return round(float(val), 1) if pd.notna(val) else 50.0


def find_swing_points(df, left=3, right=3):
    highs = df["high"].values
    lows = df["low"].values
    times = df.index
    n = len(df)
    swing_highs = []
    swing_lows = []

    for i in range(left, n - right):
        window_h = highs[i - left : i + right + 1]
        window_l = lows[i - left : i + right + 1]
        if highs[i] == np.max(window_h):
            swing_highs.append({"idx": i, "time": times[i], "price": round(float(highs[i]), 2)})
        if lows[i] == np.min(window_l):
            swing_lows.append({"idx": i, "time": times[i], "price": round(float(lows[i]), 2)})

    return swing_highs, swing_lows


def analyze_structure(df, swing_highs, swing_lows):
    close_now = float(df["close"].iloc[-1])
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        sh = swing_highs[-1]["price"] if swing_highs else round(float(df["high"].max()), 2)
        sl = swing_lows[-1]["price"] if swing_lows else round(float(df["low"].min()), 2)
        return "Consolidation Range", "NEUTRAL", sh, sl

    last_sh = swing_highs[-1]["price"]
    prev_sh = swing_highs[-2]["price"]
    last_sl = swing_lows[-1]["price"]
    prev_sl = swing_lows[-2]["price"]

    if close_now > last_sh and last_sl > prev_sl:
        return f"Bullish BOS above ${last_sh} (HH/HL)", "BULLISH", last_sh, last_sl
    if close_now < last_sl and last_sh < prev_sh:
        return f"Bearish BOS below ${last_sl} (LH/LL)", "BEARISH", last_sh, last_sl
    if close_now > last_sh and last_sh < prev_sh:
        return f"Bullish CHoCH above ${last_sh}", "BULLISH", last_sh, last_sl
    if close_now < last_sl and last_sl > prev_sl:
        return f"Bearish CHoCH below ${last_sl}", "BEARISH", last_sh, last_sl
    if last_sh > prev_sh and last_sl > prev_sl:
        return f"Bullish Structure (HL at ${last_sl})", "BULLISH", last_sh, last_sl
    if last_sh < prev_sh and last_sl < prev_sl:
        return f"Bearish Structure (LH at ${last_sh})", "BEARISH", last_sh, last_sl

    return f"Internal Range (${last_sl} – ${last_sh})", "NEUTRAL", last_sh, last_sl
def find_unmitigated_order_blocks(df, atr, live_price):
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n = len(df)

    bullish_obs = []
    bearish_obs = []

    for i in range(2, n - 3):
        body_next1 = abs(closes[i + 1] - opens[i + 1])
        body_next2 = abs(closes[i + 2] - opens[i + 2])
        displacement = max(body_next1, body_next2)

        # Bullish OB: Bearish candle before strong bullish displacement
        if closes[i] < opens[i] and closes[i + 1] > opens[i + 1] and displacement >= atr * 1.15:
            ob_low = round(float(lows[i]), 2)
            ob_high = round(float(max(opens[i], highs[i])), 2)
            subsequent_closes = closes[i + 2 :]
            if len(subsequent_closes) > 0 and np.min(subsequent_closes) > ob_low and ob_low < live_price:
                bullish_obs.append({"low": ob_low, "high": ob_high})

        # Bearish OB: Bullish candle before strong bearish displacement
        if closes[i] > opens[i] and closes[i + 1] < opens[i + 1] and displacement >= atr * 1.15:
            ob_high = round(float(highs[i]), 2)
            ob_low = round(float(min(opens[i], lows[i])), 2)
            subsequent_closes = closes[i + 2 :]
            if len(subsequent_closes) > 0 and np.max(subsequent_closes) < ob_high and ob_high > live_price:
                bearish_obs.append({"low": ob_low, "high": ob_high})

    best_demand = bullish_obs[-1] if bullish_obs else None
    best_supply = bearish_obs[-1] if bearish_obs else None
    return best_demand, best_supply


def find_unmitigated_fvgs(df, live_price, min_gap=1.0):
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)

    bull_fvgs = []
    bear_fvgs = []

    for i in range(2, n - 1):
        if lows[i] > highs[i - 2] + min_gap:
            gap_bot = round(float(highs[i - 2]), 2)
            gap_top = round(float(lows[i]), 2)
            if np.min(lows[i + 1 :]) > gap_bot and gap_bot < live_price:
                bull_fvgs.append({"bottom": gap_bot, "top": gap_top})

        if lows[i - 2] > highs[i] + min_gap:
            gap_bot = round(float(highs[i]), 2)
            gap_top = round(float(lows[i - 2]), 2)
            if np.max(highs[i + 1 :]) < gap_top and gap_top > live_price:
                bear_fvgs.append({"bottom": gap_bot, "top": gap_top})

    return (bull_fvgs[-1] if bull_fvgs else None), (bear_fvgs[-1] if bear_fvgs else None)
def get_smc_market_data():
    if not os.path.exists(MT5_DATA_PATH):
        raise FileNotFoundError(f"Missing {MT5_DATA_PATH}. Run mt5_push.py first.")

    with open(MT5_DATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    df_m15 = load_mt5_df(raw["xau_m15"])
    df_m5 = load_mt5_df(raw["xau_m5"])
    df_dxy = load_mt5_df(raw["dxy_m15"])
    df_h1 = load_mt5_df(raw["xau_h1"]) if raw.get("xau_h1") else None

    live_price = round(float(raw.get("gold_bid") or df_m5["close"].iloc[-1]), 2)
    dxy_now = round(float(raw.get("dxy_bid") or df_dxy["close"].iloc[-1]), 3)

    # H1 Higher-Timeframe Structure (if xau_h1 is present)
    if df_h1 is not None and len(df_h1) >= 20:
        h1_sh, h1_sl = find_swing_points(df_h1.tail(60), left=3, right=3)
        h1_struct_tag, h1_dir, _, _ = analyze_structure(df_h1.tail(60), h1_sh, h1_sl)
    else:
        h1_struct_tag, h1_dir = "H1 aligned with M15", "NEUTRAL"

    # Daily & Session Ranges (UTC)
    unique_dates = sorted(df_m15.index.normalize().unique())
    if len(unique_dates) >= 2:
        prev_day_df = df_m15[df_m15.index.normalize() == unique_dates[-2]]
        today_df = df_m15[df_m15.index.normalize() == unique_dates[-1]]
    else:
        prev_day_df = df_m15.iloc[:-96]
        today_df = df_m15.tail(96)

    pdh = round(float(prev_day_df["high"].max()), 2)
    pdl = round(float(prev_day_df["low"].min()), 2)
    prev_day_close = float(prev_day_df["close"].iloc[-1])
    pct_change = round(((live_price - prev_day_close) / prev_day_close) * 100.0, 2)

    last_24h = df_m15.tail(96)
    macro_high = round(float(last_24h["high"].max()), 2)
    macro_low = round(float(last_24h["low"].min()), 2)

    asia_df = today_df[(today_df.index.hour >= 0) & (today_df.index.hour < 7)]
    london_df = today_df[(today_df.index.hour >= 7) & (today_df.index.hour < 13)]
    ny_df = today_df[(today_df.index.hour >= 13) & (today_df.index.hour < 21)]

    asia_high = round(float(asia_df["high"].max()), 2) if not asia_df.empty else macro_high
    asia_low = round(float(asia_df["low"].min()), 2) if not asia_df.empty else macro_low
    london_high = round(float(london_df["high"].max()), 2) if not london_df.empty else macro_high
    london_low = round(float(london_df["low"].min()), 2) if not london_df.empty else macro_low
    ny_high = round(float(ny_df["high"].max()), 2) if not ny_df.empty else macro_high
    ny_low = round(float(ny_df["low"].min()), 2) if not ny_df.empty else macro_low

    # Intraday Dealing Range & M15 Structure
    dealing_df = df_m15.tail(64)
    atr_m15 = compute_atr(df_m15, 14)
    swing_highs, swing_lows = find_swing_points(dealing_df, left=3, right=3)
    structure_tag, struct_dir, _, _ = analyze_structure(dealing_df, swing_highs, swing_lows)

    strong_high = round(float(dealing_df["high"].max()), 2)
    strong_low = round(float(dealing_df["low"].min()), 2)
    equilibrium = round((strong_high + strong_low) / 2.0, 2)
    in_discount = live_price < equilibrium

    # Unmitigated Order Blocks & Fair Value Gaps
    demand_ob, supply_ob = find_unmitigated_order_blocks(df_m15.tail(96), atr_m15, live_price)
    bull_fvg, bear_fvg = find_unmitigated_fvgs(df_m15.tail(64), live_price, min_gap=max(1.0, atr_m15 * 0.25))

    dem_low = demand_ob["low"] if demand_ob else strong_low
    dem_high = demand_ob["high"] if demand_ob else round(strong_low + max(atr_m15 * 0.8, 3.0), 2)
    sup_high = supply_ob["high"] if supply_ob else strong_high
    sup_low = supply_ob["low"] if supply_ob else round(strong_high - max(atr_m15 * 0.8, 3.0), 2)

    supply_zone = f"${sup_low} – ${sup_high}"
    demand_zone = f"${dem_low} – ${dem_high}"

    fvg_parts = []
    if bull_fvg:
        fvg_parts.append(f"Bullish FVG ${bull_fvg['bottom']}–${bull_fvg['top']}")
    if bear_fvg:
        fvg_parts.append(f"Bearish FVG ${bear_fvg['bottom']}–${bear_fvg['top']}")
    fvg_note = " | ".join(fvg_parts) if fvg_parts else "No unmitigated M15 FVG; watching OB reaction"

    # Liquidity Sweep Read
    recent_6h = df_m15.tail(24)
    r6_high = round(float(recent_6h["high"].max()), 2)
    r6_low = round(float(recent_6h["low"].min()), 2)

    if r6_high > pdh and live_price < pdh:
        pa_signal = f"Buy-side liquidity swept above PDH (${pdh}) with bearish rejection"
    elif r6_low < pdl and live_price > pdl:
        pa_signal = f"Sell-side liquidity swept below PDL (${pdl}) with bullish reclaim"
    elif r6_high > asia_high and live_price < asia_high:
        pa_signal = f"Asian High (${asia_high}) liquidity raided; sellers defending premium"
    elif r6_low < asia_low and live_price > asia_low:
        pa_signal = f"Asian Low (${asia_low}) stop-hunt complete; buyers reclaiming discount"
    elif in_discount:
        pa_signal = f"Trading in Discount below ${equilibrium} equilibrium ({structure_tag})"
    else:
        pa_signal = f"Trading in Premium above ${equilibrium} equilibrium ({structure_tag})"

    # Momentum & DXYm Correlation
    ema20 = round(float(df_m15["close"].ewm(span=20, adjust=False).mean().iloc[-1]), 2)
    ema50 = round(float(df_m15["close"].ewm(span=50, adjust=False).mean().iloc[-1]), 2)
    rsi_val = compute_rsi(df_m15["close"], 14)
    ema_bias = "Bullish (EMA20 > EMA50)" if ema20 > ema50 else "Bearish (EMA20 < EMA50)"

    dxy_start = float(df_dxy["close"].iloc[0])
    dxy_chg = round(((dxy_now - dxy_start) / dxy_start) * 100.0, 2)
    if dxy_chg > 0.05:
        dxy_bias = f"Bullish at {dxy_now} (+{dxy_chg}%, headwind for Gold)"
    elif dxy_chg < -0.05:
        dxy_bias = f"Bearish at {dxy_now} ({dxy_chg}%, tailwind for Gold)"
    else:
        dxy_bias = f"Flat at {dxy_now} ({dxy_chg}%, neutral USD flow)"

    # Weighted Multi-Timeframe Confluence Score
    score = 50
    score += 15 if h1_dir == "BULLISH" else (-15 if h1_dir == "BEARISH" else 0)
    score += 15 if struct_dir == "BULLISH" else (-15 if struct_dir == "BEARISH" else 0)
    score += 10 if ema20 > ema50 else -10
    score += 10 if dxy_chg < -0.05 else (-10 if dxy_chg > 0.05 else 0)

    if score >= 60:
        bias_label = "BULLISH BIAS"
    elif score <= 40:
        bias_label = "BEARISH BIAS"
    else:
        bias_label = "RANGE / REACTION"

    is_bull = score >= 50
    watch_low = dem_low if is_bull else sup_low
    watch_high = dem_high if is_bull else sup_high
    invalidation = round(dem_low - max(atr_m15 * 0.6, 2.5), 2) if is_bull else round(sup_high + max(atr_m15 * 0.6, 2.5), 2)
    tp1 = equilibrium
    tp2 = sup_low if is_bull else dem_high

    return {
        "exported_utc": raw.get("exported_utc", ""),
        "live_price": live_price,
        "pct_change": pct_change,
        "atr_m15": round(atr_m15, 2),
        "h1_structure": h1_struct_tag,
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
        "strong_high": sup_high,
        "strong_low": dem_low,
        "equilibrium": equilibrium,
        "supply_zone": supply_zone,
        "demand_zone": demand_zone,
        "supply_low": sup_low,
        "supply_high": sup_high,
        "demand_low": dem_low,
        "demand_high": dem_high,
        "watch_low": watch_low,
        "watch_high": watch_high,
        "invalidation": invalidation,
        "tp1": tp1,
        "tp2": tp2,
        "retest_res": sup_low,
        "retest_sup": dem_high,
        "bull_fvg": bull_fvg,
        "bear_fvg": bear_fvg,
        "fvg_note": fvg_note,
        "structure_tag": structure_tag,
        "struct_dir": struct_dir,
        "pa_signal": pa_signal,
        "ema20": ema20,
        "ema50": ema50,
        "rsi": rsi_val,
        "ema_bias": ema_bias,
        "dxy_now": dxy_now,
        "dxy_bias": dxy_bias,
        "bias_label": bias_label,
        "bias_score": score,
    }
