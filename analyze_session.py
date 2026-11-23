import os
import re
import json
import time
import asyncio
import subprocess
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from datetime import datetime, timezone
from google import genai
from google.genai import types
from PIL import Image
from smc_engine import get_smc_market_data, get_usd_fundamental_context
from seo_engine import build_seo_package

MEMORY_FILE = "predictions.json"

def detect_session():
    utc_hour = datetime.now(timezone.utc).hour
    if 4 <= utc_hour <= 9:
        return "LONDON SESSION"
    elif 10 <= utc_hour <= 15:
        return "NEW YORK SESSION"
    return "XAUUSD MARKET"

def check_previous_call_played_out(smc):
    if not os.path.exists(MEMORY_FILE):
        return None

    with open(MEMORY_FILE, "r") as f:
        history = json.load(f)

    if not history:
        return None

    prev = history.__getitem__(len(history) - 1)
    if prev.get("evaluated"):
        return None

    try:
        prev_dt = datetime.strptime(prev.get("timestamp"), "%Y%m%d_%H%M").replace(tzinfo=timezone.utc)
        hours_elapsed = (datetime.now(timezone.utc) - prev_dt).total_seconds() / 3600.0
        if hours_elapsed < 2.0:
            return None
    except Exception:
        pass

    h6 = smc.get("recent_6h_high")
    l6 = smc.get("recent_6h_low")
    strong_low = float(prev.get("strong_low"))
    strong_high = float(prev.get("strong_high"))
    eq = float(prev.get("equilibrium"))

    outcome = None
    if l6 <= (strong_low + 2.5) and h6 >= eq:
        outcome = {
            "won": True,
            "setup": f"Demand Zone bounce at ${strong_low} -> Equilibrium ${eq}",
            "old_session": prev.get("session"),
            "old_chart": prev.get("saved_5m_chart")
        }
    elif h6 >= (strong_high - 2.5) and l6 <= eq:
        outcome = {
            "won": True,
            "setup": f"Supply Zone rejection at ${strong_high} -> Equilibrium ${eq}",
            "old_session": prev.get("session"),
            "old_chart": prev.get("saved_5m_chart")
        }

    prev.update({"evaluated": True, "outcome": outcome})
    with open(MEMORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    return outcome

def fetch_tf_candles(interval, live_price):
    period = "2d" if interval == "5m" else "5d"
    for ticker in ("GC=F", "XAUUSD=X"):
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False)
            if df is not None and not df.empty and len(df) >= 35:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.tail(46).copy()
                last_close = float(df.get("Close").iloc.__getitem__(len(df) - 1))
                spread = last_close - float(live_price)
                for col in ("Open", "High", "Low", "Close"):
                    df.__setitem__(col, df.get(col) - spread)
                df.__setitem__("EMA20", df.get("Close").ewm(span=20, adjust=False).mean())
                df.__setitem__("EMA50", df.get("Close").ewm(span=50, adjust=False).mean())
                return df
        except Exception as e:
            print(f"⚠️ {ticker} ({interval}) fetch warning: {e}")
    raise RuntimeError(f"Could not fetch {interval} candles.")
def render_pro_chart_image(df, tf_label, smc, out_png_path, visible_count=None):
    if visible_count is None:
        visible_count = len(df)

    fig, ax = plt.subplots(figsize=(9.6, 8.6), dpi=125)
    bg_color = "#0b101b"
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    sl = slice(0, visible_count)
    opens = df.get("Open").values.__getitem__(sl)
    highs = df.get("High").values.__getitem__(sl)
    lows = df.get("Low").values.__getitem__(sl)
    closes = df.get("Close").values.__getitem__(sl)
    ema20 = df.get("EMA20").values.__getitem__(sl)
    ema50 = df.get("EMA50").values.__getitem__(sl)
    n_total = len(df)
    x = np.arange(visible_count)

    c_low = float(df.get("Low").min())
    c_high = float(df.get("High").max())
    c_span = max(c_high - c_low, 8.0)
    y_min = c_low - c_span * 0.14
    y_max = c_high + c_span * 0.16

    sup_high = float(smc.get("strong_high"))
    sup_low = float(smc.get("retest_res"))
    dem_low = float(smc.get("strong_low"))
    dem_high = float(smc.get("retest_sup"))
    eq_price = float(smc.get("equilibrium"))
    live_p = float(closes.__getitem__(visible_count - 1))

    vis_sup_top = min(sup_high, y_max - c_span * 0.015)
    vis_sup_bot = max(min(sup_low, vis_sup_top - c_span * 0.07), y_max - c_span * 0.13)
    ax.add_patch(patches.Rectangle(
        (-1, vis_sup_bot), n_total + 8, vis_sup_top - vis_sup_bot,
        linewidth=1.2, edgecolor="#ef4444", facecolor="#ef4444", alpha=0.22, zorder=1
    ))
    ax.text(
        0.3, vis_sup_top - c_span * 0.012,
        f"SUPPLY ZONE  ${sup_low:.1f} - ${sup_high:.1f}",
        color="#fca5a5", fontsize=9.5, fontweight="bold", va="top", zorder=6
    )

    vis_dem_bot = max(dem_low, y_min + c_span * 0.015)
    vis_dem_top = min(max(dem_high, vis_dem_bot + c_span * 0.07), y_min + c_span * 0.13)
    ax.add_patch(patches.Rectangle(
        (-1, vis_dem_bot), n_total + 8, vis_dem_top - vis_dem_bot,
        linewidth=1.2, edgecolor="#06b6d4", facecolor="#06b6d4", alpha=0.22, zorder=1
    ))
    ax.text(
        0.3, vis_dem_bot + c_span * 0.012,
        f"DEMAND ZONE  ${dem_low:.1f} - ${dem_high:.1f}",
        color="#67e8f9", fontsize=9.5, fontweight="bold", va="bottom", zorder=6
    )

    if y_min < eq_price < y_max:
        ax.axhline(eq_price, color="#f59e0b", linestyle=":", linewidth=1.6, alpha=0.95, zorder=2)
        ax.text(
            0.3, eq_price + c_span * 0.012, f"50% EQ  ${eq_price:.2f}",
            color="#fcd34d", fontsize=8.8, fontweight="bold", va="bottom", zorder=6
        )

    for i in range(visible_count):
        c_val = closes.__getitem__(i)
        o_val = opens.__getitem__(i)
        h_val = highs.__getitem__(i)
        l_val = lows.__getitem__(i)
        x_val = x.__getitem__(i)
        is_up = c_val >= o_val
        body_col = "#00d09c" if is_up else "#ff4757"
        wick_col = "#2ed573" if is_up else "#ff6b81"
        ax.plot((x_val, x_val), (l_val, h_val), color=wick_col, linewidth=1.8, zorder=3)
        b_bot = min(o_val, c_val)
        b_h = max(abs(c_val - o_val), c_span * 0.014)
        ax.bar(
            x_val, b_h, bottom=b_bot, width=0.74,
            color=body_col, edgecolor=body_col, linewidth=1.0, zorder=4
        )
    ax.plot(x, ema20, color="#3b82f6", linewidth=2.2, label="EMA 20", zorder=5)
    ax.plot(x, ema50, color="#f97316", linewidth=2.2, label="EMA 50", zorder=5)

    ax.axhline(live_p, color="#00f2fe", linestyle="--", linewidth=1.4, alpha=0.95, zorder=6)
    ax.text(
        n_total + 0.3, live_p, f" ${live_p:.2f} ",
        color="#0b101b", fontsize=10, fontweight="bold", va="center",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#00f2fe", edgecolor="none"),
        zorder=7
    )

    ax.text(
        0.015, 0.975, f"XAUUSD | {tf_label} | INSTITUTIONAL SMC",
        transform=ax.transAxes, color="#f1f5f9", fontsize=10.5, fontweight="bold", va="top",
        bbox=dict(boxstyle="round,pad=0.32", facecolor="#131c2e", edgecolor="#2a3954"),
        zorder=7
    )
    ax.text(
        0.5, 0.5, "FR6 FX",
        transform=ax.transAxes, color="#ffffff", alpha=0.05,
        fontsize=68, fontweight="bold", ha="center", va="center", zorder=1
    )

    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.tick_params(axis="y", colors="#e2e8f0", labelsize=10.5)
    ax.tick_params(axis="x", colors="#64748b", labelsize=9)
    ax.grid(True, color="#192338", linestyle="-", linewidth=0.7, alpha=0.85)

    tick_step = max(n_total // 5, 1)
    tick_idxs = list(range(0, n_total, tick_step))
    tick_labels = tuple(df.index.__getitem__(i).strftime("%H:%M") for i in tick_idxs)
    ax.set_xticks(tick_idxs)
    ax.set_xticklabels(tick_labels)

    for spine in ("top", "left"):
        ax.spines.get(spine).set_visible(False)
    for spine in ("bottom", "right"):
        ax.spines.get(spine).set_color("#2a3954")

    ax.set_ylim(y_min, y_max)
    ax.set_xlim(-1, n_total + 6.0)

    leg = ax.legend(loc="upper right", frameon=True, facecolor="#131c2e", edgecolor="#2a3954", fontsize=9.5)
    for text in leg.get_texts():
        text.set_color("#f8fafc")

    plt.subplots_adjust(left=0.015, right=0.885, top=0.98, bottom=0.055)
    plt.savefig(out_png_path, facecolor=bg_color, dpi=125)
    plt.close(fig)

def build_live_candle_clip(df, tf_label, smc, out_webm_path):
    frame_dir = f"assets/frames_{tf_label}"
    os.makedirs(frame_dir, exist_ok=True)
    n_total = len(df)
    start_c = max(n_total - 11, 20)
    frame_idx = 0

    for c in range(start_c, n_total + 1):
        png_f = os.path.join(frame_dir, f"f_{frame_idx:03d}.png")
        render_pro_chart_image(df, tf_label, smc, png_f, visible_count=c)
        frame_idx += 1

    last_png = os.path.join(frame_dir, f"f_{frame_idx - 1:03d}.png")
    for _ in range(6):
        png_f = os.path.join(frame_dir, f"f_{frame_idx:03d}.png")
        Image.open(last_png).save(png_f)
        frame_idx += 1

    cmd = (
        "ffmpeg", "-y", "-framerate", "1", "-i", os.path.join(frame_dir, "f_%03d.png"),
        "-vf", "scale=960:860,fps=30",
        "-t", "18", "-c:v", "libvpx-vp9", "-b:v", "2000k", "-an", out_webm_path
    )
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

async def capture_tradingview_charts(smc):
    os.makedirs("assets", exist_ok=True)
    df_15 = fetch_tf_candles("15m", smc.get("live_price"))
    df_5 = fetch_tf_candles("5m", smc.get("live_price"))

    render_pro_chart_image(df_15, "15M", smc, "assets/tv_15m.png")
    render_pro_chart_image(df_5, "5M", smc, "assets/tv_5m.png")

    build_live_candle_clip(df_15, "15M", smc, "assets/tv_15m.webm")
    build_live_candle_clip(df_5, "5M", smc, "assets/tv_5m.webm")
    print("✅ Full-height 15M & 5M candlestick charts with exact Y-axis SMC zones rendered.")
def generate_ai_analysis(smc, news, session_name, played_out):
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
        http_options={"timeout": 30000}
    )
    img_15m = Image.open("assets/tv_15m.png")
    img_5m = Image.open("assets/tv_5m.png")

    today_label = datetime.now(timezone.utc).strftime("%d %b %Y")
    tg_link = (
        os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official")
        .replace("https://", "")
        .replace("http://", "")
        .strip()
    )
    news_block = "\n".join(news)

    recap_prompt = ""
    if played_out and played_out.get("won"):
        old_sess = played_out.get("old_session")
        old_setup = played_out.get("setup")
        recap_prompt = f"""
        BONUS RECAP TRIGGERED: Our previous {old_sess} call ({old_setup}) JUST PLAYED OUT!
        Set "recap_enabled": true and write a punchy 15-second phonetic 'recap_spoken_script' showing viewers how our FR6 FX level hit target.
        """

    live_p = smc.get("live_price")
    pct_c = smc.get("pct_change")
    pdh = smc.get("pdh")
    pdl = smc.get("pdl")
    a_low = smc.get("asia_low")
    a_high = smc.get("asia_high")
    l_low = smc.get("london_low")
    l_high = smc.get("london_high")
    n_low = smc.get("ny_low")
    n_high = smc.get("ny_high")
    sup_z = smc.get("supply_zone")
    s_high = smc.get("strong_high")
    eq = smc.get("equilibrium")
    dem_z = smc.get("demand_zone")
    s_low = smc.get("strong_low")
    ret_res = smc.get("retest_res")
    ret_sup = smc.get("retest_sup")
    fvg = smc.get("fvg_note")
    pa_sig = smc.get("pa_signal")
    ema20 = smc.get("ema20")
    ema50 = smc.get("ema50")
    rsi = smc.get("rsi")
    dxy_b = smc.get("dxy_bias")
    bias_l = smc.get("bias_label")
    bias_s = smc.get("bias_score")
    prompt = f"""
    You are the head Smart Money Concepts (SMC) mentor for @FR6FX.
    Generate BOTH:
    1. A calm, authoritative 42-second vertical video script ('spoken_script') for YouTube/Instagram/Facebook Reels.
    2. A deep, mentor-style written analysis ('telegram_report') to post right underneath our annotated TradingView chart image in our Telegram channel ({tg_link}).

    EXACT LIVE TECHNICAL & SESSION DATA:
    - Session: {session_name} ({today_label})
    - Live Gold Price: ${live_p} ({pct_c}%)
    - Previous Day High (PDH): ${pdh} | Previous Day Low (PDL): ${pdl}
    - Asian Session Range: ${a_low} - ${a_high}
    - London Session Range: ${l_low} - ${l_high}
    - New York Session Range: ${n_low} - ${n_high}
    - Institutional Supply Zone (Resistance): {sup_z} (Strong High: ${s_high})
    - 50% Equilibrium Pivot: ${eq}
    - Institutional Demand Zone (Support): {dem_z} (Strong Low: ${s_low})
    - Retest Zones: Resistance Retest ${ret_res} | Support Retest ${ret_sup}
    - Fair Value Gap: {fvg}
    - Liquidity & Price Action Read: {pa_sig}
    - 5m EMA 20: ${ema20} | 5m EMA 50: ${ema50} | RSI(14): {rsi}
    - DXY Impact: {dxy_b}
    - Overall Bias: {bias_l} ({bias_s}/100)
    - Fundamental USD News Today:
    {news_block}

    RULES FOR 'spoken_script' (Reels Voiceover, ~95 words):
    - Write numbers cleanly without decimals (e.g. "thirty-six nineteen" instead of "$3619.60", and "one-oh-four" for DXY).
    - ALWAYS spell out "fair value gap" instead of "FVG" and write "buy side liquidity" with a space so speech recognition transcribes it accurately.
    - Cover the live session price action, liquidity sweep/rejection ({pa_sig}), Supply & Demand zones, and DXY impact.
    - Include this exact natural CTA near the end: "Join our free Telegram channel in the bio or description for full chart markups and live news alerts, and comment your bias below."

    RULES FOR 'telegram_report' (Mentor-style standalone Telegram post, 1,200-1,800 characters using HTML tags <b> and <i> only, NO asterisks):
    - Act like a patient, disciplined mentor teaching your community how to read the chart.
    - Include sections with clean emojis:
      1. 📊 SESSION CONTEXT & SESSION HIGHS/LOWS (Asia, London, NY, PDH/PDL)
      2. 💧 LIQUIDITY, SWEEPS & FAIR VALUE GAP ({pa_sig} & {fvg})
      3. 🎯 SUPPLY, DEMAND & RETEST ZONES TO WATCH
      4. 💵 DXY MACRO & UPCOMING USD NEWS
      5. 🧠 MENTOR GAMEPLAN & NEXT SCENARIOS (Bullish vs Bearish invalidation rules, educational only)
    {recap_prompt}

    Return ONLY valid JSON:
    {{
      "date_label": "{today_label}",
      "session": "{session_name}",
      "spoken_script": "Full 42-second phonetic voiceover script including free Telegram CTA",
      "youtube_title": "XAUUSD {session_name.title()} Smart Money Analysis ({today_label}) | Gold Supply & Demand #Shorts",
      "social_caption": "Clean Reels caption with Supply/Demand levels, DXY bias, FREE TELEGRAM LINK (https://{tg_link}), Follow @FR6FX CTA, and educational disclaimer",
      "telegram_report": "Complete mentor-style Telegram chart breakdown (1,200-1,800 characters) using HTML bold/italic tags",
      "recap_enabled": false,
      "recap_spoken_script": ""
    }}
    """

    models_to_try = ("gemini-2.5-flash", "gemini-2.5-flash-lite")
    response = None

    for model_name in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=(prompt, img_15m, img_5m),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.4
                    )
                )
                if response and response.text:
                    break
            except Exception as e:
                print(f"⚠️ {model_name} attempt {attempt+1} busy: {e}")
                time.sleep(5)
        if response and response.text:
            print(f"✅ AI Mentor analysis generated using {model_name}")
            break
    if response and response.text:
        result = json.loads(response.text)
    else:
        print("🔄 Gemini busy-using built-in Mentor fallback analysis...")
        dxy_val = float(smc.get("dxy_now"))
        dxy_spoken = f"{dxy_val:.1f}".replace(".0", "")
        dxy_dir = "pushing higher" if "Bullish" in str(dxy_b) else "pulling back"
        clean_pa = re.sub(r"\$(\d+)\.\d+", r"\1", str(pa_sig))
        clean_pa = clean_pa.replace("Buy-side", "Buy side").replace("buy-side", "buy side")
        clean_pa = clean_pa.replace("Sell-side", "Sell side").replace("sell-side", "sell side")
        clean_pa = clean_pa.replace("FVG", "fair value gap")

        result = {
            "date_label": today_label,
            "session": session_name,
            "spoken_script": (
                f"Gold is trading near {int(float(live_p))} heading into the {session_name} with a {str(bias_l).lower()}. "
                f"Looking at session liquidity, {clean_pa}. "
                f"Institutional supply sits between {int(float(ret_res))} and {int(float(s_high))}, while demand support rests near {int(float(s_low))}. "
                f"With the dollar index {dxy_dir} around {dxy_spoken}, wait for a clean sweep and retest before confirming entries. "
                f"Join our free Telegram channel in the bio or description for full chart markups and live news alerts, and comment your bias below."
            ),
            "youtube_title": f"XAUUSD {session_name.title()} Smart Money Analysis ({today_label}) | Gold Supply & Demand #Shorts",
            "social_caption": (
                f"📊 XAUUSD {session_name} SMC OUTLOOK ({today_label})\n\n"
                f"🔴 Supply Zone: {sup_z}\n"
                f"⚖️ 50% Equilibrium: ${eq}\n"
                f"🔵 Demand Zone: {dem_z}\n"
                f"💧 Liquidity Read: {pa_sig}\n"
                f"💵 DXY Impact: {dxy_b}\n\n"
                f"📲 Join Free Telegram for Full Chart Markups & News Alerts: https://{tg_link}\n"
                f"💾 Save this post & follow @FR6FX!\n"
                f"⚠️ Educational purposes only. Not financial advice."
            ),
            "telegram_report": (
                f"🟡 <b>FR6 FX MENTOR BRIEF — XAUUSD ({session_name})</b>\n"
                f"💰 Live Spot: <b>${live_p}</b> ({bias_l})\n\n"
                f"📍 <b>Session & Daily Liquidity:</b>\n"
                f"• PDH / PDL: ${pdh} / ${pdl}\n"
                f"• Asia Range: ${a_low} - ${a_high}\n"
                f"• London Range: ${l_low} - ${l_high}\n\n"
                f"💧 <b>Price Action & Imbalance:</b>\n"
                f"• {pa_sig}\n"
                f"• {fvg}\n\n"
                f"🎯 <b>Zones to Watch:</b>\n"
                f"• 🔴 Supply Cap: {sup_z} (Retest: ${ret_res})\n"
                f"• ⚖️ 50% Equilibrium: ${eq}\n"
                f"• 🔵 Demand Floor: {dem_z} (Retest: ${ret_sup})\n\n"
                f"📰 <b>DXY & USD Fundamentals:</b>\n"
                f"• DXY: {dxy_b}\n"
                f"{news_block}\n\n"
                f"🧠 <b>Mentor Rule:</b> Never chase mid-range candles. Wait for a liquidity sweep into Supply/Demand + 5m structure shift.\n"
                f"⚠️ <i>Educational analysis only. Manage risk.</i>"
            ),
            "recap_enabled": False,
            "recap_spoken_script": ""
        }

    result.update({"smc": smc, "seo": build_seo_package(smc, news, session_name, result)})

    history = []
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            history = json.load(f)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    saved_5m = f"assets/history_{ts}_5m.png"
    img_5m.save(saved_5m)

    last_item = history.__getitem__(len(history) - 1) if history else {}
    is_duplicate = (
        bool(history)
        and not last_item.get("evaluated")
        and float(last_item.get("strong_high", 0)) == float(s_high)
        and float(last_item.get("strong_low", 0)) == float(s_low)
    )

    if not is_duplicate:
        history.append({
            "timestamp": ts,
            "session": session_name,
            "strong_high": s_high,
            "equilibrium": eq,
            "strong_low": s_low,
            "saved_5m_chart": saved_5m,
            "evaluated": False
        })
    else:
        print("ℹ️ Levels unchanged from last open call-skipping duplicate prediction log.")

    keep_from = max(0, len(history) - 15)
    recent_history = list(history).__getitem__(slice(keep_from, None))
    with open(MEMORY_FILE, "w") as f:
        json.dump(recent_history, f, indent=2)

    with open("assets/analysis_output.json", "w") as f:
        json.dump(result, f, indent=2)

    return result

async def main():
    session = detect_session()
    smc = get_smc_market_data()
    news = get_usd_fundamental_context()
    played_out = check_previous_call_played_out(smc)

    await capture_tradingview_charts(smc)
    out = generate_ai_analysis(smc, news, session, played_out)
    print(f"✅ Phase 3 AI Mentor + SEO complete for {session}. Bonus Recap Triggered: {out.get('recap_enabled')}")

if __name__ == "__main__":
    asyncio.run(main())
