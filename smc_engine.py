"""FR6FX SMC data engine (v6: TradingView scanner + Yahoo, no OANDA API).

Fixed / enhanced vs v2 (the "remaining" list):
- Data flow (same as the original design, NO OANDA API): live price, 5m EMA20/EMA50, RSI, daily high/low and DXY come
  from the TradingView scanner for OANDA:XAUUSD / TVC:DXY. Candles come from Yahoo: spot XAUUSD=X first (accepted only
  if it sits within $8 of the TradingView quote), then GC=F futures shifted by the basis (the original method).
  Set CANDLE_SOURCE=futures to use ONLY GC=F exactly like v1. Run `python smc_engine.py` for a live self-test.
  Note: the scanner's RSI column is the DAILY RSI (reported as rsi_timeframe).
- Real market structure: swing pivots, BOS / CHoCH, unmitigated order blocks, equal-highs/lows liquidity pools.
  New keys: structure_trend, structure_note, ob_supply_*, ob_demand_*, eq_highs, eq_lows, liquidity_pools.
  (supply_zone/demand_zone/strong_high/strong_low/equilibrium keep their meaning so other files keep working.)
- DST-aware sessions (London 07:00-13:00 Europe/London, NY 08:00-16:00 America/New_York, Asia = 00:00 UTC -> London open).
  In winter these equal the old fixed 07-13 / 13-21 UTC hours; in summer they shift automatically.
- DST-aware market hours (Fri 17:00 ET close, Sun 18:00 ET open) and holidays: Jan 1, Good Friday, Dec 25.
- Economic calendar: env override, JSON then XML fallback, 30-min cache (the feed is rate limited), stale-cache fallback.
- Data lag is measured and reported (data_lag_minutes); stale limit tightened to 90 minutes.
- Structure vote added to the bias score (score clamped to 0-100).
- get_smc_market_data() returns (smc, df).
"""
import json
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests
import yfinance as yf

try:
    from zoneinfo import ZoneInfo
    LONDON_TZ = ZoneInfo("Europe/London")
    NY_TZ = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001  (tzdata missing) -> winter offsets; add `tzdata` to requirements
    LONDON_TZ = timezone.utc
    NY_TZ = timezone(timedelta(hours=-5))

TV_SCAN_URL = "https://scanner.tradingview.com/cfd/scan"
CALENDAR_URLS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",
]
CALENDAR_CACHE = os.path.join(tempfile.gettempdir(), "fr6fx_calendar_cache.json")
CALENDAR_TTL = 1800
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FR6FX-bot/3.0)"}
MAX_CANDLE_AGE = timedelta(minutes=90)
MIN_BARS = 150
SPOT_MAX_SHIFT = 8.0      # spot-vs-TradingView residual we are willing to correct
FUT_MAX_SHIFT = 150.0     # futures basis sanity limit
SWING_N = 3


class DataError(RuntimeError):
    """Raised when market data is missing or unusable. Never publish on this."""


# ---------------------------------------------------------------- helpers
def _num(v, default=None):
    try:
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def _scrub(text):
    return re.sub(r"(apikey|api_key|token)=[^&\s]+", r"\1=***", str(text), flags=re.I)


def _request_json(method, url, retries=3, **kw):
    headers = {**HEADERS, **kw.pop("headers", {})}
    last = None
    for i in range(retries):
        try:
            r = requests.request(method, url, timeout=15, headers=headers, **kw)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise DataError(f"{url.split('?')[0]} failed after {retries} tries: {_scrub(last)}")


# ---------------------------------------------------------------- sessions / market hours (DST aware)
def session_windows(day):
    """UTC (start, end) per session for a UTC calendar date."""
    def at(tz, h):
        return datetime(day.year, day.month, day.day, h, tzinfo=tz).astimezone(timezone.utc)

    l0, l1 = at(LONDON_TZ, 7), at(LONDON_TZ, 13)
    n0, n1 = at(NY_TZ, 8), at(NY_TZ, 16)
    a0 = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return {"ASIA": (a0, l0), "LONDON": (l0, l1), "NY": (n0, n1)}


def session_label(now=None):
    """Label for the session a post is about (cron runs pre-London and pre-NY)."""
    now = now or datetime.now(timezone.utc)
    w = session_windows(now.date())
    if w["LONDON"][0] - timedelta(hours=3) <= now < w["NY"][0] - timedelta(hours=1):
        return "LONDON SESSION"
    if w["NY"][0] - timedelta(hours=1) <= now < w["NY"][1]:
        return "NEW YORK SESSION"
    return "XAUUSD MARKET"


def _easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def market_is_open(now=None):
    """Spot gold: closes Fri 17:00 New York, reopens Sun 18:00 New York. Closed Jan 1, Good Friday, Dec 25."""
    now = now or datetime.now(timezone.utc)
    ny = now.astimezone(NY_TZ)
    wd, h = ny.weekday(), ny.hour
    if wd == 5 or (wd == 4 and h >= 17) or (wd == 6 and h < 18):
        return False
    d = ny.date()
    if (d.month, d.day) in {(12, 25), (1, 1)}:
        return False
    if d == _easter(d.year) - timedelta(days=2):
        return False
    return True


def _nth_weekday(year, month, weekday, n):
    """n-th weekday of a month (n>=1), or the last one (n=-1). weekday: Mon=0."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def thin_liquidity_note(d):
    """Text for days when gold is open but liquidity is thin (US holidays, year-end). Empty string otherwise."""
    y = d.year
    thanksgiving = _nth_weekday(y, 11, 3, 4)
    days = {
        date(y, 1, 1): "New Year's Day", date(y, 1, 2): "Post-New Year",
        _nth_weekday(y, 1, 0, 3): "US MLK Day", _nth_weekday(y, 2, 0, 3): "US Presidents' Day",
        _nth_weekday(y, 5, 0, -1): "US Memorial Day", date(y, 6, 19): "US Juneteenth",
        date(y, 7, 4): "US Independence Day", _nth_weekday(y, 9, 0, 1): "US Labor Day",
        thanksgiving: "US Thanksgiving", thanksgiving + timedelta(days=1): "Day after US Thanksgiving",
        date(y, 12, 24): "Christmas Eve", date(y, 12, 26): "Boxing Day", date(y, 12, 31): "New Year's Eve",
    }
    for fixed, label in ((date(y, 6, 19), "US Juneteenth"), (date(y, 7, 4), "US Independence Day")):
        if fixed.weekday() == 5:      # Saturday -> observed Friday
            days[fixed - timedelta(days=1)] = f"{label} (observed)"
        elif fixed.weekday() == 6:    # Sunday -> observed Monday
            days[fixed + timedelta(days=1)] = f"{label} (observed)"
    name = days.get(d)
    return f"{name}: holiday-thinned liquidity, expect erratic moves and wider spreads" if name else ""


def _rng(lo, hi):
    return "not started" if lo is None else f"${lo} – ${hi}"


def _session_range(day_df, window):
    start, end = window
    part = day_df[(day_df.index >= start) & (day_df.index < end)]
    if part.empty:
        return None, None
    return round(float(part["High"].max()), 2), round(float(part["Low"].min()), 2)


# ---------------------------------------------------------------- live quote + candles
def fetch_tradingview_spot():
    """TradingView scanner quote for OANDA:XAUUSD and TVC:DXY (same call and columns as the original pipeline)."""
    cols = ["close", "change", "high", "low", "EMA20|5", "EMA50|5", "High.1D", "Low.1D", "RSI"]
    payload = {"symbols": {"tickers": ["OANDA:XAUUSD", "TVC:DXY"]}, "columns": cols}
    r = _request_json("POST", TV_SCAN_URL, json=payload)
    out = {}
    for row in r.get("data", []):
        out[row.get("s")] = dict(zip(cols, row.get("d", [])))
    return out


def _dxy_from(tv):
    """(dxy_now, dxy_change_pct, source) from the same scanner response; Yahoo DX-Y.NYB only if it is missing."""
    q = tv.get("TVC:DXY", {})
    now, chg = _num(q.get("close")), _num(q.get("change"))
    if now is not None and chg is not None:
        return now, chg, "tradingview"
    try:
        h = yf.download("DX-Y.NYB", period="10d", interval="1d", progress=False, auto_adjust=False)
        if isinstance(h.columns, pd.MultiIndex):
            h.columns = h.columns.get_level_values(0)
        closes = h["Close"].dropna()
        if len(closes) >= 2:
            return float(closes.iloc[-1]), float((closes.iloc[-1] / closes.iloc[-2] - 1) * 100), "yahoo:DX-Y.NYB"
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ DXY backup via Yahoo failed: {_scrub(e)}")
    return None, None, None


def _to_utc_index(df):
    idx = df.index
    df.index = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    return df


def _fetch_yahoo(ticker):
    raw = yf.download(ticker, period="5d", interval="15m", progress=False, auto_adjust=False)
    if raw is None or raw.empty:
        raise DataError(f"yfinance returned no candles for {ticker}")
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    return _to_utc_index(raw[["Open", "High", "Low", "Close"]].copy())


def _check_fresh(df, label="candles"):
    age = datetime.now(timezone.utc) - df.index[-1].to_pydatetime()
    if age > MAX_CANDLE_AGE:
        raise DataError(f"latest {label} bar is {age} old")


def _finalize(df, live_price, max_shift):
    """Clean candles; if live_price is given, shift them onto it (rejecting gaps larger than max_shift)."""
    df = df[["Open", "High", "Low", "Close"]].dropna().astype(float).sort_index()
    df = df[~df.index.duplicated(keep="last")]
    if len(df) < MIN_BARS:
        raise DataError(f"only {len(df)} candles")
    _check_fresh(df)
    shift = 0.0
    if live_price is not None:
        shift = round(float(df["Close"].iloc[-1]) - live_price, 2)
        if abs(shift) > max_shift:
            raise DataError(f"candle/live-price gap {shift} exceeds {max_shift}")
        for col in ("Open", "High", "Low", "Close"):
            df[col] = df[col] - shift
    return df, shift


def load_aligned_candles(live_price):
    """Yahoo 15m candles aligned to the TradingView quote. Returns (df_utc, shift_applied, source_name).
    auto (default): spot XAUUSD=X first (rejected if >$8 from the quote), then GC=F shifted by the futures basis.
    CANDLE_SOURCE=futures: only GC=F, exactly like the original pipeline."""
    sources = []
    if os.environ.get("CANDLE_SOURCE", "auto").strip().lower() != "futures":
        sources.append(("yahoo:XAUUSD=X (spot)", lambda: _fetch_yahoo("XAUUSD=X"), SPOT_MAX_SHIFT))
    sources.append(("yahoo:GC=F (futures, basis-shifted)", lambda: _fetch_yahoo("GC=F"), FUT_MAX_SHIFT))
    errors = []
    for name, fn, max_shift in sources:
        try:
            df, shift = _finalize(fn(), live_price, max_shift)
            print(f"✅ Candle source: {name} (shift {shift})")
            return df, shift, name
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: {_scrub(e)}")
    raise DataError("no usable candle source -> " + " | ".join(errors))


# ---------------------------------------------------------------- gold inputs (TradingView scanner + Yahoo candles)
def _gold_inputs():
    tv = fetch_tradingview_spot()
    q = tv.get("OANDA:XAUUSD", {})
    live_price = _num(q.get("close"))
    if live_price is None:
        raise DataError("TradingView scanner returned no XAUUSD price")
    live_price = round(live_price, 2)
    df, shift, source = load_aligned_candles(live_price)
    e20, e50, rsi = _num(q.get("EMA20|5")), _num(q.get("EMA50|5")), _num(q.get("RSI"))
    return {
        "live_price": live_price,
        "pct_change": round(_num(q.get("change"), 0.0), 2),
        "ema20": round(e20, 2) if e20 is not None else None,
        "ema50": round(e50, 2) if e50 is not None else None,
        "rsi": round(rsi, 1) if rsi is not None else None,
        "high_1d": _num(q.get("High.1D")), "low_1d": _num(q.get("Low.1D")),
        "df": df, "shift": shift, "source": source,
        "price_source": "TradingView scanner (OANDA:XAUUSD)",
        "indicator_source": "TradingView scanner (5m EMAs; RSI = scanner default, DAILY)",
        "rsi_timeframe": "1D",
        "dxy": _dxy_from(tv),
    }


# ---------------------------------------------------------------- structure / order blocks / liquidity
def _swings(df, n=SWING_N):
    hi, lo = df["High"].to_numpy(), df["Low"].to_numpy()
    sh, sl = [], []
    for i in range(n, len(df) - n):
        if hi[i] == hi[i - n:i + n + 1].max() and hi[i] > hi[i - n:i].max():
            sh.append((i, float(hi[i])))
        if lo[i] == lo[i - n:i + n + 1].min() and lo[i] < lo[i - n:i].min():
            sl.append((i, float(lo[i])))
    return sh, sl


def _structure(df, sh, sl, n=SWING_N):
    """BOS = close beyond the last swing in trend direction; CHoCH = close beyond the opposite swing."""
    cl = df["Close"].to_numpy()
    events, trend = [], 0
    cur_sh = cur_sl = None
    used_sh = used_sl = True
    ish = isl = 0
    for i in range(len(df)):
        while ish < len(sh) and sh[ish][0] + n <= i:
            cur_sh, used_sh = sh[ish], False
            ish += 1
        while isl < len(sl) and sl[isl][0] + n <= i:
            cur_sl, used_sl = sl[isl], False
            isl += 1
        if cur_sh and not used_sh and cl[i] > cur_sh[1]:
            origin = cur_sl[0] if cur_sl else max(0, cur_sh[0] - n)
            events.append({"kind": "CHoCH" if trend == -1 else "BOS", "dir": "bullish", "idx": i,
                           "level": cur_sh[1], "origin": origin})
            trend, used_sh = 1, True
        elif cur_sl and not used_sl and cl[i] < cur_sl[1]:
            origin = cur_sh[0] if cur_sh else max(0, cur_sl[0] - n)
            events.append({"kind": "CHoCH" if trend == 1 else "BOS", "dir": "bearish", "idx": i,
                           "level": cur_sl[1], "origin": origin})
            trend, used_sl = -1, True
    return events, trend


def _order_blocks(df, events, min_width=0.0, min_leg=0.0):
    """Order block = last opposing candle between the leg origin and the structure break. Mitigated if closed through.
    Zones thinner than min_width (volatility based) are widened away from price so they are tradable.
    Breaks without real displacement (move from the block to the break close < min_leg) are ignored."""
    op, cl = df["Open"].to_numpy(), df["Close"].to_numpy()
    hi, lo = df["High"].to_numpy(), df["Low"].to_numpy()
    obs = []
    for ev in events:
        i, o = ev["idx"], min(ev["origin"], ev["idx"] - 1)
        bull = ev["dir"] == "bullish"
        pick = next((k for k in range(i - 1, o - 1, -1) if (cl[k] < op[k] if bull else cl[k] > op[k])), o)
        zl, zh = float(lo[pick]), float(hi[pick])
        leg = (cl[i] - zl) if bull else (zh - cl[i])
        if leg < min_leg:
            continue
        if zh - zl < min_width:
            if bull:
                zl = zh - min_width
            else:
                zh = zl + min_width
        after = cl[i + 1:]
        mitigated = bool((after < zl).any()) if bull else bool((after > zh).any())
        obs.append({"dir": ev["dir"], "lo": zl, "hi": zh, "idx": pick, "mitigated": mitigated})
    return obs


def _nearest_obs(obs, price):
    dem = [o for o in obs if o["dir"] == "bullish" and not o["mitigated"] and o["lo"] < price]
    sup = [o for o in obs if o["dir"] == "bearish" and not o["mitigated"] and o["hi"] > price]
    demand = max(dem, key=lambda o: o["hi"]) if dem else None
    supply = min(sup, key=lambda o: o["lo"]) if sup else None
    return supply, demand


def _equal_level(df, swings, atr, price, kind):
    """Nearest unswept equal-highs (above price) or equal-lows (below price)."""
    tol = max(0.5, 0.12 * atr)
    pts = swings[-8:]
    arr = df["High"].to_numpy() if kind == "high" else df["Low"].to_numpy()
    best = None
    for a in range(len(pts)):
        for b in range(a + 1, len(pts)):
            if abs(pts[a][1] - pts[b][1]) > tol:
                continue
            later = pts[b][0]
            if kind == "high":
                lvl = max(pts[a][1], pts[b][1])
                if lvl > price and not (arr[later + 1:] > lvl + tol).any():
                    best = lvl if best is None else min(best, lvl)
            else:
                lvl = min(pts[a][1], pts[b][1])
                if lvl < price and not (arr[later + 1:] < lvl - tol).any():
                    best = lvl if best is None else max(best, lvl)
    return round(best, 2) if best is not None else None


def _find_fvg(df):
    hi, lo = df["High"].to_numpy(), df["Low"].to_numpy()
    op, cl = df["Open"].to_numpy(), df["Close"].to_numpy()
    atr = float((df["High"] - df["Low"]).tail(14).mean())
    thr = max(1.0, 0.25 * atr)
    n = len(df)
    for i in range(n - 1, max(n - 40, 2), -1):
        if abs(cl[i - 1] - op[i - 1]) < 0.6 * atr:
            continue
        c1h, c1l, c3h, c3l = hi[i - 2], lo[i - 2], hi[i], lo[i]
        if c3l > c1h + thr and not (lo[i + 1:] <= c1h).any():
            return f"Bullish 15m FVG (Imbalance) at ${round(c1h, 2)} – ${round(c3l, 2)}", "bullish"
        if c1l > c3h + thr and not (hi[i + 1:] >= c1l).any():
            return f"Bearish 15m FVG (Imbalance) at ${round(c3h, 2)} – ${round(c1l, 2)}", "bearish"
    return "No fresh unfilled 15m Fair Value Gap; watching order block retests", None


# ---------------------------------------------------------------- main snapshot
def get_smc_market_data():
    g = _gold_inputs()
    live_price, pct_change = g["live_price"], g["pct_change"]
    ema20, ema50, rsi_val = g["ema20"], g["ema50"], g["rsi"]
    df, shift, source = g["df"], g["shift"], g["source"]
    dxy_now, dxy_chg, dxy_source = g["dxy"]

    last_ts = df.index[-1]
    last_close = float(df["Close"].iloc[-1])
    now = datetime.now(timezone.utc)
    lag_min = int(max(0, (now - last_ts.to_pydatetime()).total_seconds() / 60 - 15))

    # previous trading day (last UTC date before today with a real number of bars)
    dates = df.index.normalize()
    counts = df.groupby(dates).size()
    today_date = last_ts.normalize()
    prev = [d for d, c in counts.items() if d < today_date and c >= 40]
    if not prev:
        raise DataError("no complete previous trading day in data")
    prev_day = df[dates == prev[-1]]
    pdh, pdl = round(float(prev_day["High"].max()), 2), round(float(prev_day["Low"].min()), 2)

    # rolling 24h dealing range
    win = df[df.index > last_ts - pd.Timedelta(hours=24)]
    strong_high, strong_low = float(win["High"].max()), float(win["Low"].min())
    if g["high_1d"] is not None:
        strong_high = max(strong_high, g["high_1d"])
    if g["low_1d"] is not None:
        strong_low = min(strong_low, g["low_1d"])
    strong_high, strong_low = round(strong_high, 2), round(strong_low, 2)
    equilibrium = round((strong_high + strong_low) / 2.0, 2)

    # DST-aware sessions (today's UTC date; None when not started)
    windows = session_windows(today_date.date())
    today_df = df[dates == today_date]
    asia_high, asia_low = _session_range(today_df, windows["ASIA"])
    london_high, london_low = _session_range(today_df, windows["LONDON"])
    ny_high, ny_low = _session_range(today_df, windows["NY"])

    # range-based zones (kept for compatibility with video/evaluator)
    thickness = round(max((strong_high - strong_low) * 0.14, 3.5), 2)
    supply_low, demand_high = round(strong_high - thickness, 2), round(strong_low + thickness, 2)
    retest_res = round((strong_high + equilibrium) / 2.0, 2)
    retest_sup = round((strong_low + equilibrium) / 2.0, 2)

    fvg_note, fvg_type = _find_fvg(df)

    # structure, order blocks, liquidity pools
    sh, sl = _swings(df)
    events, trend = _structure(df, sh, sl)
    atr = float((df["High"] - df["Low"]).tail(14).mean())
    obs = _order_blocks(df, events, min_width=max(1.0, 0.3 * atr), min_leg=1.5 * atr)
    ob_sup, ob_dem = _nearest_obs(obs, live_price)
    eq_highs = _equal_level(df, sh, atr, live_price, "high")
    eq_lows = _equal_level(df, sl, atr, live_price, "low")
    if events:
        ev = events[-1]
        word = "Bullish" if ev["dir"] == "bullish" else "Bearish"
        side = "above" if ev["dir"] == "bullish" else "below"
        structure_note = f"{word} {ev['kind']} on 15m (close {side} ${round(ev['level'], 2)})"
    else:
        structure_note = "No confirmed 15m structure break in the lookback window"
    pools = []
    if eq_highs is not None:
        pools.append(f"Equal highs (buy-side liquidity) at ${eq_highs}")
    if eq_lows is not None:
        pools.append(f"Equal lows (sell-side liquidity) at ${eq_lows}")
    liquidity_pools = "; ".join(pools) if pools else "No clean equal highs/lows pools nearby"

    # sweeps: wick beyond level AND close back inside, price back inside now
    recent = df.tail(24)
    post_asia = recent[recent.index >= windows["ASIA"][1]]

    def swept_above(level, bars):
        return level is not None and last_close < level and bool(((bars["High"] > level) & (bars["Close"] < level)).any())

    def swept_below(level, bars):
        return level is not None and last_close > level and bool(((bars["Low"] < level) & (bars["Close"] > level)).any())

    if swept_above(asia_high, post_asia):
        pa_signal = f"Buy-side liquidity swept above Asian High (${asia_high}) with bearish rejection back inside range"
    elif swept_below(asia_low, post_asia):
        pa_signal = f"Sell-side liquidity swept below Asian Low (${asia_low}) with bullish rejection & reclaim"
    elif swept_above(pdh, recent):
        pa_signal = f"Fakeout liquidity raid above Previous Day High (${pdh}); sellers defending supply"
    elif swept_below(pdl, recent):
        pa_signal = f"Stop-hunt sweep below Previous Day Low (${pdl}); buyers defending demand"
    elif live_price > equilibrium:
        pa_signal = (f"Bullish market structure holding above ${equilibrium} equilibrium; eyeing ${pdh} PDH liquidity"
                     if live_price < pdh else
                     f"Bullish market structure trading above PDH (${pdh}); watching for continuation or a sweep-and-reject")
    else:
        pa_signal = (f"Bearish market structure below ${equilibrium} equilibrium; targeting ${pdl} PDL liquidity"
                     if live_price > pdl else
                     f"Bearish market structure trading below PDL (${pdl}); watching for continuation or a sweep-and-reclaim")

    ema_bias = ("Bullish (EMA 20 above 50)" if ema20 > ema50 else "Bearish (EMA 20 below 50)") \
        if ema20 is not None and ema50 is not None else "unavailable"

    if dxy_now is None or dxy_chg is None:
        dxy_now, dxy_bias = None, "unavailable"
    else:
        dxy_now = round(dxy_now, 2)
        dxy_bias = (f"Bullish at {dxy_now} (+{round(dxy_chg, 2)}%, pressuring Gold lower)" if dxy_chg > 0
                    else f"Bearish at {dxy_now} ({round(dxy_chg, 2)}%, supporting Gold upside)")

    score = 50
    score += 15 if live_price > equilibrium else -15
    if ema20 is not None and ema50 is not None:
        score += 15 if ema20 > ema50 else -15
    if dxy_chg:
        score += 15 if dxy_chg < 0 else -15
    if rsi_val is not None:
        score += 10 if rsi_val > 55 else (-10 if rsi_val < 45 else 0)
    score += 10 * trend
    score = max(0, min(100, score))
    bias_label = "BULLISH BIAS" if score >= 65 else ("BEARISH BIAS" if score <= 35 else "NEUTRAL / RANGE")

    def r2(v):
        return round(v, 2) if v is not None else None

    smc = {
        "as_of": now.isoformat(),
        "liquidity_note": thin_liquidity_note(now.astimezone(NY_TZ).date()),
        "data_source": source,
        "data_lag_minutes": lag_min,
        "source_shift": shift,
        "price_source": g["price_source"],
        "indicator_source": g["indicator_source"],
        "rsi_timeframe": g["rsi_timeframe"],
        "dxy_source": dxy_source or "unavailable",
        "live_price": live_price,
        "pct_change": pct_change,
        "pdh": pdh, "pdl": pdl,
        "asia_high": asia_high, "asia_low": asia_low, "asia_range": _rng(asia_low, asia_high),
        "london_high": london_high, "london_low": london_low, "london_range": _rng(london_low, london_high),
        "ny_high": ny_high, "ny_low": ny_low, "ny_range": _rng(ny_low, ny_high),
        "strong_high": strong_high, "equilibrium": equilibrium, "strong_low": strong_low,
        "supply_low": supply_low, "demand_high": demand_high,
        "supply_zone": f"${supply_low} – ${strong_high}",
        "demand_zone": f"${strong_low} – ${demand_high}",
        "retest_res": retest_res, "retest_sup": retest_sup,
        "structure_trend": {1: "bullish", -1: "bearish", 0: "undefined"}[trend],
        "structure_note": structure_note,
        "ob_supply_low": r2(ob_sup["lo"]) if ob_sup else None,
        "ob_supply_high": r2(ob_sup["hi"]) if ob_sup else None,
        "ob_demand_low": r2(ob_dem["lo"]) if ob_dem else None,
        "ob_demand_high": r2(ob_dem["hi"]) if ob_dem else None,
        "ob_supply_zone": f"${r2(ob_sup['lo'])} – ${r2(ob_sup['hi'])}" if ob_sup else "none unmitigated above price",
        "ob_demand_zone": f"${r2(ob_dem['lo'])} – ${r2(ob_dem['hi'])}" if ob_dem else "none unmitigated below price",
        "eq_highs": eq_highs, "eq_lows": eq_lows, "liquidity_pools": liquidity_pools,
        "fvg_note": fvg_note, "fvg_type": fvg_type,
        "pa_signal": pa_signal,
        "ema20": ema20, "ema50": ema50,
        "rsi": rsi_val if rsi_val is not None else "n/a",
        "ema_bias": ema_bias,
        "dxy_now": dxy_now if dxy_now is not None else "n/a",
        "dxy_bias": dxy_bias,
        "bias_label": bias_label, "bias_score": score,
        "recent_6h_high": round(float(recent["High"].max()), 2),
        "recent_6h_low": round(float(recent["Low"].min()), 2),
    }
    return smc, df


# ---------------------------------------------------------------- USD news
def _parse_calendar_json(raw):
    out = []
    for ev in raw:
        dt = datetime.fromisoformat(ev["date"])
        dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        out.append({"title": ev.get("title"), "country": ev.get("country"), "impact": ev.get("impact"),
                    "dt": dt.isoformat(), "tz_verified": True})
    return out


def _parse_calendar_xml(content):
    """XML feed: date MM-DD-YYYY, time like 1:30pm. Its timezone is unverified, so times are never shown for these events."""
    root = ET.fromstring(content)
    out = []
    for ev in root.findall("event"):
        t = (ev.findtext("time") or "").strip()
        try:
            dt = datetime.strptime(f"{ev.findtext('date').strip()} {t.upper()}", "%m-%d-%Y %I:%M%p").replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError):
            continue  # All Day / Tentative
        out.append({"title": (ev.findtext("title") or "").strip(), "country": ev.findtext("country"),
                    "impact": ev.findtext("impact"), "dt": dt.isoformat(), "tz_verified": False})
    return out


def _load_calendar():
    if os.path.exists(CALENDAR_CACHE) and time.time() - os.path.getmtime(CALENDAR_CACHE) < CALENDAR_TTL:
        with open(CALENDAR_CACHE) as f:
            return json.load(f)
    urls = ([os.environ["CALENDAR_URL"].strip()] if os.environ.get("CALENDAR_URL") else []) + CALENDAR_URLS
    errors = []
    for url in urls:
        try:
            r = requests.get(url, timeout=15, headers=HEADERS)
            r.raise_for_status()
            events = _parse_calendar_xml(r.content) if url.lower().endswith(".xml") else _parse_calendar_json(r.json())
            if not events:
                raise ValueError("parsed 0 events")
            with open(CALENDAR_CACHE, "w") as f:
                json.dump(events, f)
            print(f"✅ Calendar loaded from {url} ({len(events)} events)")
            return events
        except Exception as e:  # noqa: BLE001
            errors.append(f"{url}: {e}")
    if os.path.exists(CALENDAR_CACHE) and time.time() - os.path.getmtime(CALENDAR_CACHE) < 7 * 86400:
        print("⚠️ Calendar fetch failed; using stale cache:", " | ".join(errors))
        with open(CALENDAR_CACHE) as f:
            return json.load(f)
    raise DataError(" | ".join(errors))


def get_usd_fundamental_context():
    """Today's High/Medium impact USD events (UTC). Generic line on any failure; never raises."""
    try:
        today = datetime.now(timezone.utc).date()
        found = []
        for ev in _load_calendar():
            if ev.get("country") != "USD" or ev.get("impact") not in ("High", "Medium"):
                continue
            dt = datetime.fromisoformat(ev["dt"])
            if dt.date() == today:
                when = f"{dt:%H:%M} UTC" if ev.get("tz_verified", True) else "time TBC"
                found.append((dt, f"• {ev['title']} [{ev['impact']} Impact — {when}]"))
        found.sort(key=lambda x: x[0])
        lines = [t for _, t in found][:6]
        return lines or ["• No major red-folder USD releases today; session liquidity & yields driving flow"]
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Economic calendar unavailable: {e}")
        return ["• US Treasury yields & Dollar Index flow driving session volatility"]


if __name__ == "__main__":
    # Live self-test:  python smc_engine.py
    print("market_is_open:", market_is_open(), "| session:", session_label())
    snap, frame = get_smc_market_data()
    keys = ("data_source", "price_source", "indicator_source", "rsi_timeframe", "dxy_source", "source_shift",
            "data_lag_minutes", "live_price", "pct_change", "ema20", "ema50", "rsi", "dxy_now", "pdh", "pdl", "asia_range", "london_range",
            "ny_range", "strong_high", "equilibrium", "strong_low", "structure_trend", "structure_note", "ob_supply_zone",
            "ob_demand_zone", "liquidity_pools", "fvg_note", "pa_signal", "dxy_bias", "bias_label", "bias_score", "liquidity_note")
    for k in keys:
        print(f"{k:18s}= {snap[k]}")
    print(f"candles: {len(frame)} | first {frame.index[0]} | last {frame.index[-1]}")
    print("news:", *get_usd_fundamental_context(), sep="\n  ")
