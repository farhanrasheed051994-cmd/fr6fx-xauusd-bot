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
from playwright.async_api import async_playwright
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
from smc_engine import get_smc_market_data, get_usd_fundamental_context
from seo_engine import build_seo_package

MEMORY_FILE = "predictions.json"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

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

def overlay_smc_hud_on_chart(png_path, tf_label, smc):
    img = Image.open(png_path).convert("RGB").resize((1080, 1000), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        f_tag = ImageFont.truetype(FONT_BOLD, 21)
        f_sm = ImageFont.truetype(FONT_BOLD, 18)
    except Exception:
        f_tag = ImageFont.load_default()
        f_sm = ImageFont.load_default()

    draw.rounded_rectangle((16, 14, 480, 56), radius=10, fill=(11, 16, 27, 225), outline=(56, 189, 248, 220), width=2)
    draw.text((28, 23), f"XAUUSD | {tf_label} | FR6 FX DESK", fill=(248, 250, 252, 255), font=f_tag)

    struct_txt = str(smc.get("structure_tag", ""))
    if struct_txt:
        draw.rounded_rectangle((16, 64, 520, 102), radius=8, fill=(15, 23, 42, 215), outline=(245, 158, 11, 200), width=1)
        draw.text((26, 73), f"STRUCTURE: {struct_txt}", fill=(253, 224, 71, 255), font=f_sm)

    img.save(png_path)
async def capture_real_tradingview_charts(smc):
    chart_url = os.environ.get("TRADINGVIEW_CHART_URL", "").strip()
    if not chart_url:
        chart_url = "https://tradingview.com"
    session_id = os.environ.get("TRADINGVIEW_SESSION_ID", "").strip()
    session_sign = os.environ.get("TRADINGVIEW_SESSION_SIGN", "").strip()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=("--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled")
        )
        context = await browser.new_context(
            viewport={"width": 540, "height": 500},
            device_scale_factor=2,
            color_scheme="dark",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        if session_id:
            cookies = list((
                {
                    "name": "sessionid",
                    "value": session_id,
                    "domain": ".tradingview.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax"
                },
            ))
            if session_sign:
                cookies.append({
                    "name": "sessionid_sign",
                    "value": session_sign,
                    "domain": ".tradingview.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "Lax"
                })
            await context.add_cookies(cookies)
            print("🔐 Authenticated TradingView session cookie injected.")

        page = await context.new_page()
        await page.goto(chart_url, wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(6500)

        for esc_try in range(3):
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)

        await page.evaluate("""() => {
            const selectors = (
                'div[data-name="legend-delete-action"]',
                'div[class*="toast"]',
                'div[class*="banner"]',
                'div[class*="popup"]',
                'button[aria-label="Close"]'
            );
            for (const sel of selectors) {
                document.querySelectorAll(sel).forEach(el => {
                    if (el && el.offsetHeight < 220) el.style.display = 'none';
                });
            }
        }""")

        for tf_code, tf_label, out_png in (("15", "15M", "assets/tv_15m.png"), ("5", "5M", "assets/tv_5m.png")):
            await page.mouse.click(270, 250)
            await page.wait_for_timeout(300)
            await page.keyboard.type(tf_code, delay=80)
            await page.wait_for_timeout(250)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(2500)
            await page.keyboard.press("Alt+r")
            await page.wait_for_timeout(1200)
            await page.screenshot(path=out_png, full_page=False)
            overlay_smc_hud_on_chart(out_png, tf_label, smc)
            print(f"📸 Real TradingView {tf_label} Retina chart captured -> {out_png}")

        await browser.close()
        return True

def fetch_tf_candles(interval, live_price):
    period = "2d" if interval == "5m" else "5d"
    for ticker in ("GC=F", "XAUUSD=X"):
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False)
            if df is not None and not df.empty and len(df) >= 35:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.tail(42).copy()
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
def render_fallback_chart_image(df, tf_label, smc, out_png_path):
    fig, ax = plt.subplots(figsize=(8.64, 8.0), dpi=125)
    bg_color = "#0b101b"
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    opens = df.get("Open").values
    highs = df.get("High").values
    lows = df.get("Low").values
    closes = df.get("Close").values
    ema20 = df.get("EMA20").values
    ema50 = df.get("EMA50").values
    n_total = len(df)
    x = np.arange(n_total)

    sup_high = float(smc.get("strong_high"))
    sup_low = float(smc.get("retest_res"))
    dem_low = float(smc.get("strong_low"))
    dem_high = float(smc.get("retest_sup"))
    eq_price = float(smc.get("equilibrium"))
    live_p = float(closes.__getitem__(n_total - 1))

    c_low = min(float(df.get("Low").min()), dem_low)
    c_high = max(float(df.get("High").max()), sup_high)
    c_span = max(c_high - c_low, 8.0)
    y_min = c_low - c_span * 0.08
    y_max = c_high + c_span * 0.11

    ax.add_patch(patches.Rectangle(
        (-1, sup_low), n_total + 8, max(sup_high - sup_low, c_span * 0.04),
        linewidth=1.2, edgecolor="#ef4444", facecolor="#ef4444", alpha=0.22, zorder=1
    ))
    ax.text(
        0.3, sup_high - c_span * 0.008,
        f"SUPPLY  ${sup_low:.1f} - ${sup_high:.1f}",
        color="#fca5a5", fontsize=9.5, fontweight="bold", va="top", zorder=6
    )

    ax.add_patch(patches.Rectangle(
        (-1, dem_low), n_total + 8, max(dem_high - dem_low, c_span * 0.04),
        linewidth=1.2, edgecolor="#06b6d4", facecolor="#06b6d4", alpha=0.22, zorder=1
    ))
    ax.text(
        0.3, dem_low + c_span * 0.008,
        f"DEMAND  ${dem_low:.1f} - ${dem_high:.1f}",
        color="#67e8f9", fontsize=9.5, fontweight="bold", va="bottom", zorder=6
    )

    fvg_type = str(smc.get("fvg_type", "NONE"))
    fvg_top = float(smc.get("fvg_top", 0.0))
    fvg_bot = float(smc.get("fvg_bottom", 0.0))
    if fvg_type in ("BULLISH", "BEARISH") and fvg_top > fvg_bot:
        fvg_col = "#22c55e" if fvg_type == "BULLISH" else "#f97316"
        ax.add_patch(patches.Rectangle(
            (max(n_total - 18, 0), fvg_bot), 24, fvg_top - fvg_bot,
            linewidth=1.0, edgecolor=fvg_col, facecolor=fvg_col, alpha=0.18, zorder=1
        ))

    ax.axhline(eq_price, color="#f59e0b", linestyle=":", linewidth=1.6, alpha=0.95, zorder=2)
    ax.text(
        0.3, eq_price + c_span * 0.01, f"50% EQ  ${eq_price:.2f}",
        color="#fcd34d", fontsize=8.8, fontweight="bold", va="bottom", zorder=6
    )

    for i in range(n_total):
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
        b_h = max(abs(c_val - o_val), c_span * 0.012)
        ax.bar(
            x_val, b_h, bottom=b_bot, width=0.72,
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

    ax.yaxis.tick_right()
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
    ax.set_xlim(-1, n_total + 6.5)

    leg = ax.legend(loc="lower right", frameon=True, facecolor="#131c2e", edgecolor="#2a3954", fontsize=9.5)
    for text in leg.get_texts():
        text.set_color("#f8fafc")

    plt.subplots_adjust(left=0.015, right=0.88, top=0.985, bottom=0.05)
    plt.savefig(out_png_path, facecolor=bg_color, dpi=125)
    plt.close(fig)
    overlay_smc_hud_on_chart(out_png_path, tf_label, smc)

def build_motion_clip_from_png(png_path, out_webm_path):
    cmd = (
        "ffmpeg", "-y", "-loop", "1", "-t", "22", "-i", png_path,
        "-vf", "scale=1134:1050,zoompan=z='min(zoom+0.0008,1.05)':d=660:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1000:fps=30",
        "-c:v", "libvpx-vp9", "-b:v", "2400k", "-an", out_webm_path
    )
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

async def capture_tradingview_charts(smc):
    os.makedirs("assets", exist_ok=True)
    captured_live = False
    try:
        captured_live = await capture_real_tradingview_charts(smc)
    except Exception as e:
        print(f"⚠️ Real TradingView capture fallback triggered: {e}")

    if not captured_live:
        df_15 = fetch_tf_candles("15m", smc.get("live_price"))
        df_5 = fetch_tf_candles("5m", smc.get("live_price"))
        render_fallback_chart_image(df_15, "15M", smc, "assets/tv_15m.png")
        render_fallback_chart_image(df_5, "5M", smc, "assets/tv_5m.png")

    build_motion_clip_from_png("assets/tv_15m.png", "assets/tv_15m.webm")
    build_motion_clip_from_png("assets/tv_5m.png", "assets/tv_5m.webm")
    print("✅ 1080x1000 Retina 15M & 5M charts + smooth motion clips ready.")
def clean_spoken_text(raw_text):
    txt = re.sub(r"\$(\d+)\.\d+", r"\1", str(raw_text))
    txt = txt.replace("$", "")
    txt = txt.replace("Buy-side", "Buy side").replace("buy-side", "buy side")
    txt = txt.replace("Sell-side", "Sell side").replace("sell-side", "sell side")
    txt = txt.replace("FVG", "fair value gap")
    txt = txt.replace("BOS", "break of structure").replace("CHoCH", "change of character")
    return txt

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
    m_high = smc.get("macro_high")
    m_low = smc.get("macro_low")
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
    struct_t = smc.get("structure_tag")
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
    1. A calm, authoritative 40-second vertical video script ('spoken_script') for YouTube/Instagram/Facebook Reels.
    2. A deep, mentor-style written analysis ('telegram_report') to post right underneath our annotated TradingView chart image in our Telegram channel ({tg_link}).

    EXACT LIVE TECHNICAL & SESSION DATA:
    - Session: {session_name} ({today_label})
    - Live Gold Price: ${live_p} ({pct_c}%)
    - 24H Macro Range: ${m_low} - ${m_high} | PDH: ${pdh} | PDL: ${pdl}
    - Asian Session Range: ${a_low} - ${a_high}
    - London Session Range: ${l_low} - ${l_high}
    - New York Session Range: ${n_low} - ${n_high}
    - Active Intraday Supply Zone: {sup_z} (Strong High: ${s_high})
    - 50% Intraday Equilibrium: ${eq}
    - Active Intraday Demand Zone: {dem_z} (Strong Low: ${s_low})
    - Market Structure: {struct_t}
    - Fair Value Gap: {fvg}
    - Liquidity & Price Action Read: {pa_sig}
    - 5m EMA 20: ${ema20} | 5m EMA 50: ${ema50} | RSI(14): {rsi}
    - DXY Impact: {dxy_b}
    - Overall Bias: {bias_l} ({bias_s}/100)
    - Fundamental USD News Today:
    {news_block}

    RULES FOR 'spoken_script' (Reels Voiceover, ~90 words):
    - Start with the 15 minute chart structure and session liquidity ({pa_sig}), then transition cleanly to the 5 minute chart entry confirmation around Supply ({int(float(ret_res))} to {int(float(s_high))}) and Demand ({int(float(s_low))}).
    - Write ALL numbers as clean whole integers without decimals or dollar signs (e.g. "3612" instead of "$3612.30") so captions never split decimals.
    - Spell out "fair value gap", "break of structure", and "buy side liquidity" with spaces.
    - End with this exact CTA: "Join our free Telegram channel in the bio or description for full chart markups and live news alerts, and comment your bias below."

    RULES FOR 'telegram_report' (Mentor-style standalone Telegram post, 1,200-1,800 characters using HTML tags <b> and <i> only, NO asterisks):
    - Include sections with clean emojis:
      1. 📊 SESSION CONTEXT & LIQUIDITY LEVELS (Asia, London, NY, PDH/PDL, 24H Macro Range)
      2. 💧 MARKET STRUCTURE, SWEEPS & FAIR VALUE GAP ({struct_t}, {pa_sig}, {fvg})
      3. 🎯 INTRADAY SUPPLY, DEMAND & RETEST ZONES
      4. 💵 DXY MACRO & TODAY'S USD ECONOMIC CALENDAR
      5. 🧠 MENTOR EXECUTION GAMEPLAN (Bullish vs Bearish confirmation & invalidation rules)
    {recap_prompt}

    Return ONLY valid JSON:
    {{
      "date_label": "{today_label}",
      "session": "{session_name}",
      "spoken_script": "Full 40-second clean numeric voiceover script including free Telegram CTA",
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
                        temperature=0.35
                    )
                )
                if response and response.text:
                    break
            except Exception as e:
                print(f"⚠️ {model_name} attempt {attempt + 1} busy: {e}")
                time.sleep(5)
        if response and response.text:
            print(f"✅ AI Mentor analysis generated using {model_name}")
            break

    if response and response.text:
        result = json.loads(response.text)
        result.update({"spoken_script": clean_spoken_text(result.get("spoken_script", ""))})
    else:
        print("🔄 Gemini busy—using built-in Mentor fallback analysis...")
        dxy_val = int(round(float(smc.get("dxy_now"))))
        dxy_dir = "pushing higher" if "Bullish" in str(dxy_b) else "pulling back"
        clean_pa = clean_spoken_text(pa_sig)

        result = {
            "date_label": today_label,
            "session": session_name,
            "spoken_script": (
                f"On the 15 minute chart, Gold is trading near {int(round(float(live_p)))} heading into the {session_name} with a {str(bias_l).lower()}. "
                f"{clean_pa}. "
                f"Dropping down to the 5 minute chart, institutional supply sits between {int(round(float(ret_res)))} and {int(round(float(s_high)))}, while demand support rests near {int(round(float(s_low)))}. "
                f"With the dollar index {dxy_dir} around {dxy_val}, wait for a clean sweep and five minute structure shift before confirming entries. "
                f"Join our free Telegram channel in the bio or description for full chart markups and live news alerts, and comment your bias below."
            ),
            "youtube_title": f"XAUUSD {session_name.title()} Smart Money Analysis ({today_label}) | Gold Supply & Demand #Shorts",
            "social_caption": (
                f"📊 XAUUSD {session_name} SMC OUTLOOK ({today_label})\n\n"
                f"🔴 Supply Zone: {sup_z}\n"
                f"⚖️ 50% Equilibrium: ${eq}\n"
                f"🔵 Demand Zone: {dem_z}\n"
                f"📐 Structure: {struct_t}\n"
                f"💧 Liquidity Read: {pa_sig}\n"
                f"💵 DXY Impact: {dxy_b}\n\n"
                f"📲 Join Free Telegram for Full Chart Markups & News Alerts: https://{tg_link}\n"
                f"💾 Save this post & follow @FR6FX!\n"
                f"⚠️ Educational purposes only. Not financial advice."
            ),
            "telegram_report": (
                f"🟡 <b>FR6 FX MENTOR BRIEF — XAUUSD ({session_name})</b>\n"
                f"💰 Live Spot: <b>${live_p}</b> ({bias_l})\n\n"
                f"📍 <b>Session & Macro Liquidity:</b>\n"
                f"• 24H Macro Range: ${m_low} - ${m_high}\n"
                f"• PDH / PDL: ${pdh} / ${pdl}\n"
                f"• Asia Range: ${a_low} - ${a_high}\n"
                f"• London Range: ${l_low} - ${l_high}\n\n"
                f"💧 <b>Structure, Sweeps & Imbalance:</b>\n"
                f"• {struct_t}\n"
                f"• {pa_sig}\n"
                f"• {fvg}\n\n"
                f"🎯 <b>Intraday Zones to Watch:</b>\n"
                f"• 🔴 Supply Cap: {sup_z} (Retest: ${ret_res})\n"
                f"• ⚖️ 50% Equilibrium: ${eq}\n"
                f"• 🔵 Demand Floor: {dem_z} (Retest: ${ret_sup})\n\n"
                f"📰 <b>DXY & Today's USD Calendar:</b>\n"
                f"• DXY: {dxy_b}\n"
                f"{news_block}\n\n"
                f"🧠 <b>Mentor Rule:</b> Never chase mid-range candles. Wait for a liquidity sweep into Supply/Demand + 5m structure shift.\n"
                f"⚠️ <i>Educational analysis only. Manage risk.</i>"
            ),
            "recap_enabled": False,
            "recap_spoken_script": ""
        }

    result.update({"smc": smc, "seo": build_seo_package(smc, news, session_name, result)})

    history = list()
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
        print("ℹ️ Levels unchanged from last open call—skipping duplicate prediction log.")

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
