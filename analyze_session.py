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

    if not history or history[-1].get("evaluated"):
        return None

    prev = history[-1]

    try:
        prev_dt = datetime.strptime(prev["timestamp"], "%Y%m%d_%H%M").replace(tzinfo=timezone.utc)
        hours_elapsed = (datetime.now(timezone.utc) - prev_dt).total_seconds() / 3600.0
        if hours_elapsed < 2.0:
            return None
    except Exception:
        pass

    h6 = smc["recent_6h_high"]
    l6 = smc["recent_6h_low"]

    strong_low = float(prev["strong_low"])
    strong_high = float(prev["strong_high"])
    eq = float(prev["equilibrium"])

    outcome = None
    if l6 <= (strong_low + 2.5) and h6 >= eq:
        outcome = {
            "won": True,
            "setup": f"Demand Zone bounce at ${strong_low} -> Equilibrium ${eq}",
            "old_session": prev["session"],
            "old_chart": prev["saved_5m_chart"]
        }
    elif h6 >= (strong_high - 2.5) and l6 <= eq:
        outcome = {
            "won": True,
            "setup": f"Supply Zone rejection at ${strong_high} -> Equilibrium ${eq}",
            "old_session": prev["session"],
            "old_chart": prev["saved_5m_chart"]
        }

    prev["evaluated"] = True
    prev["outcome"] = outcome
    with open(MEMORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

    return outcome

def fetch_tf_candles(interval, live_price):
    """Fetches 5m or 15m Gold candles calibrated to exact OANDA:XAUUSD spot price."""
    period = "2d" if interval == "5m" else "5d"
    for ticker in ["GC=F", "XAUUSD=X"]:
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False)
            if df is not None and not df.empty and len(df) >= 35:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.tail(48).copy()
                spread = float(df["Close"].iloc[-1]) - float(live_price)
                for c in ["Open", "High", "Low", "Close"]:
                    df[c] = df[c] - spread
                df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
                df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
                return df
        except Exception as e:
            print(f"⚠️ {ticker} ({interval}) fetch warning: {e}")
    raise RuntimeError(f"Could not fetch {interval} candles.")

def render_pro_chart_image(df, tf_label, smc, out_png_path, visible_count=None):
    """Renders an ultra-crisp institutional SMC candlestick chart with exact Y-axis zone boxes."""
    if visible_count is None:
        visible_count = len(df)

    fig, ax = plt.subplots(figsize=(9.6, 8.6), dpi=125)
    bg_color = "#0b101b"
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    opens = df["Open"].values[:visible_count]
    highs = df["High"].values[:visible_count]
    lows = df["Low"].values[:visible_count]
    closes = df["Close"].values[:visible_count]
    ema20 = df["EMA20"].values[:visible_count]
    ema50 = df["EMA50"].values[:visible_count]
    n_total = len(df)
    x = np.arange(visible_count)

    sup_high = float(smc["strong_high"])
    sup_low = float(smc["retest_res"])
    dem_low = float(smc["strong_low"])
    dem_high = float(smc["retest_sup"])
    eq_price = float(smc["equilibrium"])
    live_p = float(closes[-1])

    sup_rect = patches.Rectangle(
        (-1, sup_low), n_total + 8, max(sup_high - sup_low, 1.5),
        linewidth=1.0, edgecolor="#ef4444", facecolor="#ef4444", alpha=0.16, zorder=1
    )
    ax.add_patch(sup_rect)
    ax.text(
        0.2, sup_high - 0.4, f"SUPPLY ZONE  ${sup_low:.1f} – ${sup_high:.1f}",
        color="#fca5a5", fontsize=8.5, fontweight="bold", va="top", zorder=6
    )

    dem_rect = patches.Rectangle(
        (-1, dem_low), n_total + 8, max(dem_high - dem_low, 1.5),
        linewidth=1.0, edgecolor="#06b6d4", facecolor="#06b6d4", alpha=0.16, zorder=1
    )
    ax.add_patch(dem_rect)
    ax.text(
        0.2, dem_low + 0.4, f"DEMAND ZONE  ${dem_low:.1f} – ${dem_high:.1f}",
        color="#67e8f9", fontsize=8.5, fontweight="bold", va="bottom", zorder=6
    )

    ax.axhline(eq_price, color="#f59e0b", linestyle=":", linewidth=1.3, alpha=0.9, zorder=2)
    ax.text(
        0.2, eq_price + 0.35, f"50% EQ  ${eq_price:.2f}",
        color="#fcd34d", fontsize=8.0, fontweight="bold", va="bottom", zorder=6
    )

    for i in range(visible_count):
        is_up = closes[i] >= opens[i]
        body_col = "#00c896" if is_up else "#ff4757"
        wick_col = "#2ed573" if is_up else "#ff6b81"
        ax.plot([x[i], x[i]], [lows[i], highs[i]], color=wick_col, linewidth=1.5, zorder=3)
        b_bot = min(opens[i], closes[i])
        b_h = max(abs(closes[i] - opens[i]), 0.28)
        ax.bar(
            x[i], b_h, bottom=b_bot, width=0.72,
            color=body_col, edgecolor=body_col, linewidth=0.9, zorder=4
        )

    ax.plot(x, ema20, color="#3b82f6", linewidth=2.0, label="EMA 20", zorder=5)
    ax.plot(x, ema50, color="#f97316", linewidth=2.0, label="EMA 50", zorder=5)

    ax.axhline(live_p, color="#00f2fe", linestyle="--", linewidth=1.2, alpha=0.9, zorder=6)
    ax.text(
        n_total + 0.4, live_p, f" ${live_p:.2f} ",
        color="#0b101b", fontsize=9.5, fontweight="bold", va="center",
        bbox=dict(boxstyle="round,pad=0.28", facecolor="#00f2fe", edgecolor="none"),
        zorder=7
    )

    ax.text(
        0.015, 0.975, f"XAUUSD • {tf_label} • SMART MONEY STRUCTURE",
        transform=ax.transAxes, color="#e2e8f0", fontsize=10.5, fontweight="bold", va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#131c2e", edgecolor="#26334d"),
        zorder=7
    )
    ax.text(
        0.5, 0.5, "FR6 FX",
        transform=ax.transAxes, color="#ffffff", alpha=0.045,
        fontsize=64, fontweight="bold", ha="center", va="center", zorder=1
    )

    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    ax.tick_params(axis="y", colors="#cbd5e1", labelsize=10)
    ax.tick_params(axis="x", colors="#64748b", labelsize=8.5)
    ax.grid(True, color="#192338", linestyle="-", linewidth=0.7, alpha=0.85)

    tick_step = max(n_total // 5, 1)
    tick_idxs = list(range(0, n_total, tick_step))
    tick_labels = [df.index[i].strftime("%H:%M") for i in tick_idxs]
    ax.set_xticks(tick_idxs)
    ax.set_xticklabels(tick_labels)

    for spine in ["top", "left"]:
        ax.spines[spine].set_visible(False)
    for spine in ["bottom", "right"]:
        ax.spines[spine].set_color("#26334d")

    all_lows = min(df["Low"].min(), dem_low)
    all_highs = max(df["High"].max(), sup_high)
    pad = max((all_highs - all_lows) * 0.08, 2.5)
    ax.set_ylim(all_lows - pad, all_highs + pad)
    ax.set_xlim(-1, n_total + 5.8)

    leg = ax.legend(loc="upper right", frameon=True, facecolor="#131c2e", edgecolor="#26334d", fontsize=9)
    for text in leg.get_texts():
        text.set_color("#f1f5f9")

    plt.subplots_adjust(left=0.02, right=0.88, top=0.97, bottom=0.06)
    plt.savefig(out_png_path, facecolor=bg_color, dpi=125)
    plt.close(fig)

def build_live_candle_clip(df, tf_label, smc, out_webm_path):
    """Renders an 18-second animated live-candle printing + smooth zoom video clip."""
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

    cmd = [
        "ffmpeg", "-y", "-framerate", "1", "-i", os.path.join(frame_dir, "f_%03d.png"),
        "-vf", "scale=1020:914,zoompan=z='min(zoom+0.0004,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=450:s=960x860:fps=25",
        "-t", "18", "-c:v", "libvpx-vp9", "-b:v", "1800k", "-an", out_webm_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

async def capture_tradingview_charts(smc):
    os.makedirs("assets", exist_ok=True)
    df_15 = fetch_tf_candles("15m", smc["live_price"])
    df_5 = fetch_tf_candles("5m", smc["live_price"])

    render_pro_chart_image(df_15, "15M", smc, "assets/tv_15m.png")
    render_pro_chart_image(df_5, "5M", smc, "assets/tv_5m.png")

    build_live_candle_clip(df_15, "15M", smc, "assets/tv_15m.webm")
    build_live_candle_clip(df_5, "5M", smc, "assets/tv_5m.webm")
    print("✅ Institutional 15M & 5M candlestick charts with exact Y-axis SMC zones rendered.")
def generate_ai_analysis(smc, news, session_name, played_out):
    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
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
        recap_prompt = f"""
        BONUS RECAP TRIGGERED: Our previous {played_out['old_session']} call ({played_out['setup']}) JUST PLAYED OUT!
        Set "recap_enabled": true and write a punchy 15-second phonetic 'recap_spoken_script' showing viewers how our FR6 FX level hit target.
        """

    prompt = f"""
    You are the head Smart Money Concepts (SMC) mentor for @FR6FX.
    Generate BOTH:
    1. A calm, authoritative 42-second vertical video script ('spoken_script') for YouTube/Instagram/Facebook Reels.
    2. A deep, mentor-style written analysis ('telegram_report') to post right underneath our annotated TradingView chart image in our Telegram channel ({tg_link}).

    EXACT LIVE TECHNICAL & SESSION DATA:
    - Session: {session_name} ({today_label})
    - Live Gold Price: ${smc['live_price']} ({smc['pct_change']}%)
    - Previous Day High (PDH): ${smc['pdh']} | Previous Day Low (PDL): ${smc['pdl']}
    - Asian Session Range: ${smc['asia_low']} – ${smc['asia_high']}
    - London Session Range: ${smc['london_low']} – ${smc['london_high']}
    - New York Session Range: ${smc['ny_low']} – ${smc['ny_high']}
    - Institutional Supply Zone (Resistance): {smc['supply_zone']} (Strong High: ${smc['strong_high']})
    - 50% Equilibrium Pivot: ${smc['equilibrium']}
    - Institutional Demand Zone (Support): {smc['demand_zone']} (Strong Low: ${smc['strong_low']})
    - Retest Zones: Resistance Retest ${smc['retest_res']} | Support Retest ${smc['retest_sup']}
    - Fair Value Gap: {smc['fvg_note']}
    - Liquidity & Price Action Read: {smc['pa_signal']}
    - 5m EMA 20: ${smc['ema20']} | 5m EMA 50: ${smc['ema50']} | RSI(14): {smc['rsi']}
    - DXY Impact: {smc['dxy_bias']}
    - Overall Bias: {smc['bias_label']} ({smc['bias_score']}/100)
    - Fundamental USD News Today:
    {news_block}

    RULES FOR 'spoken_script' (Reels Voiceover, ~95 words):
    - Write numbers cleanly without decimals (e.g. "thirty-six nineteen" instead of "$3619.60", and "one-oh-four" for DXY).
    - ALWAYS spell out "fair value gap" instead of "FVG" and write "buy side liquidity" with a space so speech recognition transcribes it accurately.
    - Cover the live session price action, liquidity sweep/rejection ({smc['pa_signal']}), Supply & Demand zones, and DXY impact.
    - Include this exact natural CTA near the end: "Join our free Telegram channel in the bio or description for full chart markups and live news alerts, and comment your bias below."

    RULES FOR 'telegram_report' (Mentor-style standalone Telegram post, 1,200–1,800 characters using HTML tags <b> and <i> only, NO asterisks):
    - Act like a patient, disciplined mentor teaching your community how to read the chart.
    - Include sections with clean emojis:
      1. 📊 SESSION CONTEXT & SESSION HIGHS/LOWS (Asia, London, NY, PDH/PDL)
      2. 💧 LIQUIDITY, SWEEPS & FAIR VALUE GAP ({smc['pa_signal']} & {smc['fvg_note']})
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
      "telegram_report": "Complete mentor-style Telegram chart breakdown (1,200–1,800 characters) using HTML bold/italic tags",
      "recap_enabled": false,
      "recap_spoken_script": ""
    }}
    """

    models_to_try = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    response = None

    for model_name in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=[prompt, img_15m, img_5m],
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
        print("🔄 Gemini busy—using built-in Mentor fallback analysis...")
        dxy_spoken = f"{smc['dxy_now']:.1f}".replace(".0", "")
        dxy_dir = "pushing higher" if "Bullish" in smc["dxy_bias"] else "pulling back"
        clean_pa = re.sub(r"\$(\d+)\.\d+", r"\1", smc["pa_signal"])
        clean_pa = clean_pa.replace("Buy-side", "Buy side").replace("buy-side", "buy side")
        clean_pa = clean_pa.replace("Sell-side", "Sell side").replace("sell-side", "sell side")
        clean_pa = clean_pa.replace("FVG", "fair value gap")

        result = {
            "date_label": today_label,
            "session": session_name,
            "spoken_script": (
                f"Gold is trading near {int(smc['live_price'])} heading into the {session_name} with a {smc['bias_label'].lower()}. "
                f"Looking at session liquidity, {clean_pa}. "
                f"Institutional supply sits between {int(smc['retest_res'])} and {int(smc['strong_high'])}, while demand support rests near {int(smc['strong_low'])}. "
                f"With the dollar index {dxy_dir} around {dxy_spoken}, wait for a clean sweep and retest before confirming entries. "
                f"Join our free Telegram channel in the bio or description for full chart markups and live news alerts, and comment your bias below."
            ),
            "youtube_title": f"XAUUSD {session_name.title()} Smart Money Analysis ({today_label}) | Gold Supply & Demand #Shorts",
            "social_caption": (
                f"📊 XAUUSD {session_name} SMC OUTLOOK ({today_label})\n\n"
                f"🔴 Supply Zone: {smc['supply_zone']}\n"
                f"⚖️ 50% Equilibrium: ${smc['equilibrium']}\n"
                f"🔵 Demand Zone: {smc['demand_zone']}\n"
                f"💧 Liquidity Read: {smc['pa_signal']}\n"
                f"💵 DXY Impact: {smc['dxy_bias']}\n\n"
                f"📲 Join Free Telegram for Full Chart Markups & News Alerts: https://{tg_link}\n"
                f"💾 Save this post & follow @FR6FX!\n"
                f"⚠️ Educational purposes only. Not financial advice."
            ),
            "telegram_report": (
                f"🟡 <b>FR6 FX MENTOR BRIEF — XAUUSD ({session_name})</b>\n"
                f"💰 Live Spot: <b>${smc['live_price']}</b> ({smc['bias_label']})\n\n"
                f"📍 <b>Session & Daily Liquidity:</b>\n"
                f"• PDH / PDL: ${smc['pdh']} / ${smc['pdl']}\n"
                f"• Asia Range: ${smc['asia_low']} – ${smc['asia_high']}\n"
                f"• London Range: ${smc['london_low']} – ${smc['london_high']}\n\n"
                f"💧 <b>Price Action & Imbalance:</b>\n"
                f"• {smc['pa_signal']}\n"
                f"• {smc['fvg_note']}\n\n"
                f"🎯 <b>Zones to Watch:</b>\n"
                f"• 🔴 Supply Cap: {smc['supply_zone']} (Retest: ${smc['retest_res']})\n"
                f"• ⚖️ 50% Equilibrium: ${smc['equilibrium']}\n"
                f"• 🔵 Demand Floor: {smc['demand_zone']} (Retest: ${smc['retest_sup']})\n\n"
                f"📰 <b>DXY & USD Fundamentals:</b>\n"
                f"• DXY: {smc['dxy_bias']}\n"
                f"{news_block}\n\n"
                f"🧠 <b>Mentor Rule:</b> Never chase mid-range candles. Wait for a liquidity sweep into Supply/Demand + 5m structure shift.\n"
                f"⚠️ <i>Educational analysis only. Manage risk.</i>"
            ),
            "recap_enabled": False,
            "recap_spoken_script": ""
        }

    result["smc"] = smc
    result["seo"] = build_seo_package(smc, news, session_name, result)

    history = []
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            history = json.load(f)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    saved_5m = f"assets/history_{ts}_5m.png"
    img_5m.save(saved_5m)

    is_duplicate = (
        history
        and not history[-1].get("evaluated")
        and float(history[-1]["strong_high"]) == float(smc["strong_high"])
        and float(history[-1]["strong_low"]) == float(smc["strong_low"])
    )

    if not is_duplicate:
        history.append({
            "timestamp": ts,
            "session": session_name,
            "strong_high": smc["strong_high"],
            "equilibrium": smc["equilibrium"],
            "strong_low": smc["strong_low"],
            "saved_5m_chart": saved_5m,
            "evaluated": False
        })
    else:
        print("ℹ️ Levels unchanged from last open call—skipping duplicate prediction log.")

    with open(MEMORY_FILE, "w") as f:
        json.dump(history[-15:], f, indent=2)

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
