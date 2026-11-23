import os
import re
import json
import requests
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
from PIL import Image, ImageDraw, ImageFont
from smc_engine import get_smc_market_data, get_usd_fundamental_context
from seo_engine import build_seo_package

MEMORY_FILE = "predictions.json"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def detect_session():
    utc_hour = datetime.now(timezone.utc).hour
    if 4 <= utc_hour <= 11:
        return "LONDON SESSION"
    elif 12 <= utc_hour <= 19:
        return "NEW YORK SESSION"
    return "ASIAN SESSION"

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
        if (datetime.now(timezone.utc) - prev_dt).total_seconds() / 3600.0 < 2.0:
            return None
    except Exception:
        pass

    h6 = float(smc.get("recent_6h_high"))
    l6 = float(smc.get("recent_6h_low"))
    strong_low = float(prev.get("strong_low"))
    strong_high = float(prev.get("strong_high"))
    eq = float(prev.get("equilibrium"))

    outcome = None
    if l6 <= (strong_low + 2.5) and h6 >= eq:
        outcome = {
            "won": True,
            "setup": f"Support bounce at ${strong_low} -> Equilibrium ${eq}",
            "old_session": prev.get("session"),
            "old_chart": prev.get("saved_5m_chart")
        }
    elif h6 >= (strong_high - 2.5) and l6 <= eq:
        outcome = {
            "won": True,
            "setup": f"Resistance rejection at ${strong_high} -> Equilibrium ${eq}",
            "old_session": prev.get("session"),
            "old_chart": prev.get("saved_5m_chart")
        }

    prev.update({"evaluated": True, "outcome": outcome})
    with open(MEMORY_FILE, "w") as f:
        json.dump(history, f, indent=2)
    return outcome

def fetch_clean_candles(interval, live_price, bars=46):
    period = "2d" if interval == "5m" else "5d"
    for ticker in ("GC=F", "XAUUSD=X"):
        try:
            df = yf.download(ticker, period=period, interval=interval, progress=False)
            if df is not None and not df.empty and len(df) >= 35:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df = df.tail(bars).copy()
                last_close = float(df.get("Close").iloc.__getitem__(len(df) - 1))
                spread = last_close - float(live_price)
                for col in ("Open", "High", "Low", "Close"):
                    df.__setitem__(col, df.get(col) - spread)
                return df
        except Exception as e:
            print(f"⚠️ {ticker} ({interval}) warning: {e}")
    raise RuntimeError(f"Could not fetch live {interval} candles.")

def detect_swing_badges(df):
    highs = df.get("High").values
    lows = df.get("Low").values
    n = len(df)
    badges = list()
    prev_h = None
    prev_l = None
    for i in range(3, n - 3):
        win_h = max(highs.__getitem__(k) for k in range(i - 3, i + 4))
        win_l = min(lows.__getitem__(k) for k in range(i - 3, i + 4))
        cur_h = float(highs.__getitem__(i))
        cur_l = float(lows.__getitem__(i))
        if cur_h == win_h:
            lbl = "HH" if (prev_h is not None and cur_h > prev_h) else ("LH" if prev_h is not None else "H")
            badges.append((i, cur_h, lbl, True))
            prev_h = cur_h
        elif cur_l == win_l:
            lbl = "HL" if (prev_l is not None and cur_l > prev_l) else ("LL" if prev_l is not None else "L")
            badges.append((i, cur_l, lbl, False))
            prev_l = cur_l
    keep_from = max(0, len(badges) - 5)
    return list(badges).__getitem__(slice(keep_from, None))
def render_tv_stage_chart(df, tf_label, smc, stage, out_png_path):
    fig, ax = plt.subplots(figsize=(8.64, 7.6), dpi=125)
    bg_color = "#131722"
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    opens = df.get("Open").values
    highs = df.get("High").values
    lows = df.get("Low").values
    closes = df.get("Close").values
    n_total = len(df)
    x = np.arange(n_total)

    res_lvl = float(smc.get("strong_high"))
    sup_lvl = float(smc.get("strong_low"))
    is_bull = "BULLISH" in str(smc.get("bias_label", ""))

    if is_bull:
        wz_low = float(smc.get("strong_low"))
        wz_high = float(smc.get("retest_sup"))
        inv_lvl = round(wz_low - 3.5, 2)
    else:
        wz_low = float(smc.get("retest_res"))
        wz_high = float(smc.get("strong_high"))
        inv_lvl = round(wz_high + 3.5, 2)

    live_p = float(closes.__getitem__(n_total - 1))
    c_low = min(float(df.get("Low").min()), sup_lvl, inv_lvl)
    c_high = max(float(df.get("High").max()), res_lvl, inv_lvl)
    c_span = max(c_high - c_low, 10.0)
    y_min = c_low - c_span * 0.09
    y_max = c_high + c_span * 0.10

    for i in range(n_total):
        c_val = float(closes.__getitem__(i))
        o_val = float(opens.__getitem__(i))
        h_val = float(highs.__getitem__(i))
        l_val = float(lows.__getitem__(i))
        x_val = int(x.__getitem__(i))
        is_up = c_val >= o_val
        col = "#089981" if is_up else "#F23645"
        ax.plot((x_val, x_val), (l_val, h_val), color=col, linewidth=1.7, zorder=3)
        b_bot = min(o_val, c_val)
        b_h = max(abs(c_val - o_val), c_span * 0.011)
        ax.bar(x_val, b_h, bottom=b_bot, width=0.68, color=col, edgecolor=col, linewidth=0.8, zorder=4)

    badges = detect_swing_badges(df)
    for idx_b, price_b, lbl_b, is_high_b in badges:
        y_off = c_span * 0.025 if is_high_b else -c_span * 0.032
        b_col = "#38bdf8" if lbl_b in ("HH", "HL") else "#f59e0b"
        ax.text(
            idx_b, price_b + y_off, f" {lbl_b} ",
            color=b_col, fontsize=8.5, fontweight="bold", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.22", facecolor="#1e293b", edgecolor=b_col, linewidth=1.1),
            zorder=6
        )

    if stage >= 2:
        ax.axhline(res_lvl, color="#F23645", linestyle="--", linewidth=1.8, zorder=5)
        ax.text(
            1.2, res_lvl + c_span * 0.012,
            f"RESISTANCE  {int(round(res_lvl))}",
            color="#F23645", fontsize=10.0, fontweight="bold", va="bottom", zorder=7
        )

    if stage >= 3:
        ax.axhline(sup_lvl, color="#00E5FF", linestyle="--", linewidth=1.8, zorder=5)
        ax.text(
            1.2, sup_lvl - c_span * 0.012,
            f"SUPPORT  {int(round(sup_lvl))}",
            color="#00E5FF", fontsize=10.0, fontweight="bold", va="top", zorder=7
        )

    if stage >= 4:
        wz_h = max(wz_high - wz_low, c_span * 0.045)
        ax.add_patch(patches.Rectangle(
            (max(n_total - 24, 0), wz_low), 34, wz_h,
            linewidth=1.3, edgecolor="#F59E0B", facecolor="#F59E0B", alpha=0.22, zorder=2
        ))
        ax.text(
            n_total + 6.4, wz_low + wz_h * 0.5,
            "WATCH ZONE",
            color="#FBBF24", fontsize=9.0, fontweight="bold", ha="right", va="center", zorder=7
        )

    if stage >= 5:
        ax.axhline(inv_lvl, color="#FB7185", linestyle=":", linewidth=1.5, zorder=5)
        ax.text(
            n_total * 0.44, inv_lvl - c_span * 0.012 if is_bull else inv_lvl + c_span * 0.012,
            f"Invalid {'below' if is_bull else 'above'} {int(round(inv_lvl))}",
            color="#FB7185", fontsize=9.2, fontweight="bold",
            va="top" if is_bull else "bottom", zorder=7
        )

        x_start = n_total - 1
        x_mid = n_total + 1.8
        x_end = n_total + 5.2
        wz_mid = (wz_low + wz_high) * 0.5
        target_p = res_lvl - c_span * 0.03 if is_bull else sup_lvl + c_span * 0.03

        ax.plot(
            (x_start, x_mid), (live_p, wz_mid),
            color="#FBBF24", linestyle="--", linewidth=2.1, zorder=8
        )
        ax.annotate(
            "", xy=(x_end, target_p), xytext=(x_mid, wz_mid),
            arrowprops=dict(arrowstyle="->", color="#FBBF24", lw=2.4, ls="--"),
            zorder=8
        )

    ax.plot((n_total - 1, n_total + 6.8), (live_p, live_p), color="#64748b", linestyle=":", linewidth=1.1, zorder=4)
    ax.text(
        n_total + 7.0, live_p, f" {live_p:.2f} ",
        color="#ffffff", fontsize=9.0, fontweight="bold", va="center",
        bbox=dict(boxstyle="round,pad=0.24", facecolor="#F23645" if live_p < opens.__getitem__(n_total - 1) else "#089981", edgecolor="none"),
        zorder=9
    )

    ax.yaxis.tick_right()
    ax.tick_params(axis="y", colors="#94a3b8", labelsize=9.8, length=0)
    ax.tick_params(axis="x", colors="#64748b", labelsize=8.2, length=0)
    ax.grid(True, color="#1e2433", linestyle="-", linewidth=0.75, alpha=0.9)

    tick_step = max(n_total // 5, 1)
    tick_idxs = list(range(0, n_total, tick_step))
    tick_labels = tuple(df.index.__getitem__(i).strftime("%H:%M") for i in tick_idxs)
    ax.set_xticks(tick_idxs)
    ax.set_xticklabels(tick_labels)

    for spine in ("top", "left", "bottom", "right"):
        ax.spines.get(spine).set_visible(False)

    ax.set_ylim(y_min, y_max)
    ax.set_xlim(-1.5, n_total + 9.8)

    plt.subplots_adjust(left=0.055, right=0.835, top=0.985, bottom=0.048)
    plt.savefig(out_png_path, facecolor=bg_color, dpi=125)
    plt.close(fig)

    img = Image.open(out_png_path).convert("RGB").resize((1080, 950), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        f_top = ImageFont.truetype(FONT_BOLD, 21)
    except Exception:
        f_top = ImageFont.load_default()

    draw.text((58, 16), f"XAUUSD  •  {tf_label}  •  FR6 FX", fill=(148, 163, 184, 255), font=f_top)
    draw.ellipse((58, 50, 72, 64), fill=(242, 54, 69, 255))
    draw.text((80, 45), "LIVE", fill=(242, 54, 69, 255), font=f_top)
    img.save(out_png_path)
def build_progressive_chart_stages(smc):
    os.makedirs("assets", exist_ok=True)
    live_p = smc.get("live_price")
    df_15 = fetch_clean_candles("15m", live_p, bars=46)
    df_5 = fetch_clean_candles("5m", live_p, bars=46)

    render_tv_stage_chart(df_15, "M15", smc, stage=1, out_png_path="assets/stage_1.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=2, out_png_path="assets/stage_2.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=3, out_png_path="assets/stage_3.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=4, out_png_path="assets/stage_4.png")
    render_tv_stage_chart(df_5, "M5", smc, stage=5, out_png_path="assets/stage_5.png")
    Image.open("assets/stage_5.png").save("assets/tv_5m.png")
    print("✅ 5 progressive TradingView-style Retina chart stages rendered in <2s.")

def clean_spoken_text(raw_text):
    txt = re.sub(r"\$(\d+)\.\d+", r"\1", str(raw_text))
    txt = txt.replace("$", "")
    txt = txt.replace("XAUUSD", "Gold").replace("xauusd", "Gold")
    txt = txt.replace("Buy-side", "Buy side").replace("buy-side", "buy side")
    txt = txt.replace("Sell-side", "Sell side").replace("sell-side", "sell side")
    txt = txt.replace("FVG", "fair value gap")
    txt = txt.replace("BOS", "break of structure").replace("CHoCH", "change of character")
    return txt

def generate_ai_analysis(smc, news, session_name, played_out):
    client = genai.Client(
        api_key=os.environ.get("GEMINI_API_KEY"),
        http_options={"timeout": 45}
    )
    img_stage4 = Image.open("assets/stage_4.png").resize((540, 475), Image.Resampling.LANCZOS)
    img_stage5 = Image.open("assets/stage_5.png").resize((540, 475), Image.Resampling.LANCZOS)

    today_label = datetime.now(timezone.utc).strftime("%d %b %Y")
    tg_link = (
        os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official")
        .replace("https://", "")
        .replace("http://", "")
        .strip()
    )
    news_block = "\n".join(news)

    is_bull = "BULLISH" in str(smc.get("bias_label", ""))
    default_hook = "WILL GOLD PUMP FROM DEMAND?" if is_bull else "WILL GOLD REJECT RESISTANCE?"

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
    dxy_b = smc.get("dxy_bias")
    bias_l = smc.get("bias_label")

    prompt = f"""
    You are the head Smart Money Concepts (SMC) mentor for @FR6FX.
    Generate JSON with:
    1. 'hook_title': Short 4-5 word uppercase question for the top of the Reel (e.g. "{default_hook}").
    2. 'spoken_script': A crisp 35-second vertical video voiceover (~85 words) that walks through:
       - M15 structure ({struct_t}),
       - Resistance at {int(round(float(s_high)))},
       - Support at {int(round(float(s_low)))},
       - Watch Zone ({int(round(float(ret_sup)))} to {int(round(float(s_low)))} if bullish, or {int(round(float(ret_res)))} to {int(round(float(s_high)))} if bearish),
       - Dropping to the 5 minute chart for confirmation—never chase,
       - Ending with: "Follow FR6 FX and join our free Telegram in the bio or description for full chart markups and live news alerts."
       Write ALL numbers as clean whole integers without decimals or dollar signs, and say "Gold" instead of XAUUSD.
    3. 'telegram_report': Mentor-style Telegram post (1,200-1,600 chars) using HTML <b> and <i> tags only.

    LIVE DATA:
    - Session: {session_name} ({today_label}) | Live Spot: ${live_p} ({pct_c}%)
    - Resistance: ${s_high} | Support: ${s_low} | 50% Equilibrium: ${eq}
    - Supply Zone: {sup_z} | Demand Zone: {dem_z}
    - Structure: {struct_t} | Liquidity: {pa_sig} | FVG: {fvg}
    - 24H Range: ${m_low}-${m_high} | PDH/PDL: ${pdh}/${pdl} | Asia: ${a_low}-${a_high} | London: ${l_low}-${l_high}
    - DXY: {dxy_b} | Overall Bias: {bias_l}
    - USD News: {news_block}

    Return ONLY valid JSON:
    {{
      "hook_title": "{default_hook}",
      "date_label": "{today_label}",
      "session": "{session_name}",
      "spoken_script": "Full 35-second clean numeric voiceover script",
      "youtube_title": "XAUUSD {session_name.title()} ({today_label}) | Gold Resistance, Support & Watch Zone #Shorts",
      "social_caption": "Clean Reels caption with Resistance, Support, Watch Zone, Free Telegram (https://{tg_link}), Follow @FR6FX CTA, and educational disclaimer",
      "telegram_report": "Mentor-style Telegram breakdown with HTML bold/italic tags",
      "recap_enabled": false,
      "recap_spoken_script": ""
    }}
    """
    result = None

    if os.environ.get("GEMINI_API_KEY"):
        for model_name in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=(prompt, img_stage4, img_stage5),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.35
                    )
                )
                if response and response.text:
                    result = json.loads(response.text)
                    print(f"✅ AI Mentor analysis generated using {model_name}")
                    break
            except Exception as e:
                print(f"⚠️ {model_name} busy: {e}")

    if not result and os.environ.get("GROQ_API_KEY"):
        groq_url = "".join(("https://", "api.", "groq.", "com/openai/v1/chat/completions"))
        for g_model in ("openai/gpt-oss-120b", "qwen/qwen3-32b", "llama-3.1-8b-instant"):
            try:
                g_resp = requests.post(
                    groq_url,
                    headers={
                        "Authorization": "Bearer " + os.environ.get("GROQ_API_KEY", "").strip(),
                        "Content-Type": "application/json",
                        "User-Agent": "FR6FX-Bot/1.0"
                    },
                    json={
                        "model": g_model,
                        "messages": list(({"role": "user", "content": prompt},)),
                        "response_format": {"type": "json_object"},
                        "temperature": 0.35
                    },
                    timeout=20
                )
                if g_resp.status_code == 200:
                    raw_json = g_resp.json().get("choices", ()).__getitem__(0).get("message", {}).get("content", "")
                    if raw_json:
                        result = json.loads(raw_json)
                        print(f"✅ AI Mentor analysis generated using Groq ({g_model})")
                        break
                else:
                    print(f"⚠️ Groq {g_model} status {g_resp.status_code}")
            except Exception as e:
                print(f"⚠️ Groq {g_model} warning: {e}")

    if result:
        result.update({"spoken_script": clean_spoken_text(result.get("spoken_script", ""))})
    else:
        print("🔄 Using built-in Mentor fallback analysis...")
        wz_txt = f"{int(round(float(s_low)))} to {int(round(float(ret_sup)))}" if is_bull else f"{int(round(float(ret_res)))} to {int(round(float(s_high)))}"
        result = {
            "hook_title": default_hook,
            "date_label": today_label,
            "session": session_name,
            "spoken_script": (
                f"On the 15 minute chart, Gold is trading near {int(round(float(live_p)))} heading into our {session_name.lower()} with a {str(bias_l).lower()}. "
                f"Key resistance sits at {int(round(float(s_high)))}, while major support holds at {int(round(float(s_low)))}. "
                f"Our primary watch zone is between {wz_txt}. "
                f"Dropping down to the 5 minute chart, wait for clean confirmation before entering and never chase candles. "
                f"Follow FR6 FX and join our free Telegram in the bio or description for full chart markups and live news alerts."
            ),
            "youtube_title": f"XAUUSD {session_name.title()} ({today_label}) | Gold Resistance, Support & Watch Zone #Shorts",
            "social_caption": (
                f"📊 FR6 FX | XAUUSD {session_name} ({today_label})\n\n"
                f"🔴 Resistance: ${s_high}\n"
                f"🟡 Watch Zone: {sup_z if not is_bull else dem_z}\n"
                f"🔵 Support: ${s_low}\n"
                f"💵 DXY Impact: {dxy_b}\n\n"
                f"📲 Join Free Telegram for Full Chart Markups & News Alerts: https://{tg_link}\n"
                f"💾 Save & follow @FR6FX!\n"
                f"⚠️ Not financial advice."
            ),
            "telegram_report": (
                f"🟡 <b>FR6 FX | XAUUSD {session_name}</b>\n"
                f"💰 Live Spot: <b>${live_p}</b> ({bias_l})\n\n"
                f"🎯 <b>Key Institutional Levels:</b>\n"
                f"• 🔴 Resistance: <b>${s_high}</b>\n"
                f"• 🟡 Watch Zone: <b>{sup_z if not is_bull else dem_z}</b>\n"
                f"• ⚖️ 50% Equilibrium: <b>${eq}</b>\n"
                f"• 🔵 Support: <b>${s_low}</b>\n\n"
                f"📍 <b>Session Liquidity:</b>\n"
                f"• 24H Range: ${m_low} - ${m_high} | PDH/PDL: ${pdh}/${pdl}\n"
                f"• Asia: ${a_low}-${a_high} | London: ${l_low}-${l_high}\n\n"
                f"💧 <b>Structure & Flow:</b>\n"
                f"• {struct_t}\n"
                f"• {pa_sig}\n"
                f"• DXY: {dxy_b}\n\n"
                f"📰 <b>USD Calendar:</b>\n{news_block}\n\n"
                f"🧠 <b>Mentor Rule:</b> Wait for confirmation inside the Watch Zone—no chase.\n"
                f"⚠️ <i>Not financial advice.</i>"
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
    Image.open("assets/stage_5.png").save(saved_5m)

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

    keep_from = max(0, len(history) - 15)
    recent_history = list(history).__getitem__(slice(keep_from, None))
    with open(MEMORY_FILE, "w") as f:
        json.dump(recent_history, f, indent=2)

    with open("assets/analysis_output.json", "w") as f:
        json.dump(result, f, indent=2)
    return result

def main():
    session = detect_session()
    smc = get_smc_market_data()
    news = get_usd_fundamental_context()
    played_out = check_previous_call_played_out(smc)

    build_progressive_chart_stages(smc)
    out = generate_ai_analysis(smc, news, session, played_out)
    print(f"✅ Phase 3 complete for {session}. Hook: {out.get('hook_title')}")

if __name__ == "__main__":
    main()
