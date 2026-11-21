import os
import json
import time
import asyncio
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from google import genai
from google.genai import types
from PIL import Image
from smc_engine import get_smc_market_data, get_usd_fundamental_context

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

async def capture_tradingview_charts():
    os.makedirs("assets", exist_ok=True)

    server = ThreadingHTTPServer(("127.0.0.1", 0), SimpleHTTPRequestHandler)
    _, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}/tv_chart.html"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = await browser.new_context(
                viewport={"width": 540, "height": 620},
                device_scale_factor=2,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            await page.goto(f"{base_url}?interval=15", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(8000)
            await page.screenshot(path="assets/tv_15m.png")

            await page.goto(f"{base_url}?interval=5", wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(8000)
            await page.screenshot(path="assets/tv_5m.png")

            await browser.close()
    finally:
        server.shutdown()
def generate_ai_analysis(smc, news, session_name, played_out):
    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options={"timeout": 25000}
    )
    img_15m = Image.open("assets/tv_15m.png")
    img_5m = Image.open("assets/tv_5m.png")

    today_label = datetime.now(timezone.utc).strftime("%d %b %Y")
    tg_link = os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official").strip()
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
    2. A deep, mentor-style written analysis ('telegram_report') to post alongside our annotated TradingView chart image in our Telegram channel ({tg_link}).

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
    - Fair Value Gap (FVG): {smc['fvg_note']}
    - Liquidity & Price Action Read: {smc['pa_signal']}
    - 5m EMA 20: ${smc['ema20']} | 5m EMA 50: ${smc['ema50']} | RSI(14): {smc['rsi']}
    - DXY Impact: {smc['dxy_bias']}
    - Overall Bias: {smc['bias_label']} ({smc['bias_score']}/100)
    - Fundamental USD News Today:
    {news_block}

    RULES FOR 'spoken_script' (Reels Voiceover, ~95 words):
    - Write numbers cleanly without awkward decimals (e.g. "thirty-five thirty-eight" instead of "$3538.18").
    - Cover the live session price action, liquidity sweep/rejection ({smc['pa_signal']}), Supply & Demand zones, and DXY impact.
    - Include this exact natural CTA near the end: "Join our free Telegram channel in the bio or description for full chart markups and live news alerts, and comment your bias below."

    RULES FOR 'telegram_report' (Mentor-style Telegram post under 950 characters so it fits cleanly in a Telegram photo caption):
    - Act like a patient, disciplined mentor teaching your community how to read the chart.
    - Include sections with clean emojis:
      1. 📊 SESSION CONTEXT & SESSION HIGHS/LOWS (Asia, London, NY, PDH/PDL)
      2. 💧 LIQUIDITY, SWEEPS & FVG IMBALANCE ({smc['pa_signal']} & {smc['fvg_note']})
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
      "social_caption": "Clean Reels caption with Supply/Demand levels, DXY bias, FREE TELEGRAM LINK ({tg_link}), Follow @FR6FX CTA, and educational disclaimer",
      "telegram_report": "Complete mentor-style Telegram chart breakdown under 950 characters",
      "recap_enabled": false,
      "recap_spoken_script": ""
    }}
    """

    models_to_try = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
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
        result = {
            "date_label": today_label,
            "session": session_name,
            "spoken_script": (
                f"Gold is trading near {int(smc['live_price'])} heading into the {session_name} with a {smc['bias_label'].lower()}. "
                f"Looking at session liquidity, {smc['pa_signal']}. "
                f"Institutional supply sits between {int(smc['retest_res'])} and {int(smc['strong_high'])}, while demand support rests near {int(smc['strong_low'])}. "
                f"With DXY {smc['dxy_bias']}, wait for a clean sweep and retest before confirming entries. "
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
                f"🟡 *FR6 FX MENTOR BRIEF — XAUUSD ({session_name})*\n"
                f"💰 Live Spot: *${smc['live_price']}* ({smc['bias_label']})\n\n"
                f"📍 *Session & Daily Liquidity:*\n"
                f"• PDH / PDL: ${smc['pdh']} / ${smc['pdl']}\n"
                f"• Asia Range: ${smc['asia_low']} – ${smc['asia_high']}\n"
                f"• London Range: ${smc['london_low']} – ${smc['london_high']}\n\n"
                f"💧 *Price Action & Imbalance:*\n"
                f"• {smc['pa_signal']}\n"
                f"• {smc['fvg_note']}\n\n"
                f"🎯 *Zones to Watch:*\n"
                f"• 🔴 Supply Cap: {smc['supply_zone']} (Retest: ${smc['retest_res']})\n"
                f"• ⚖️ 50% Equilibrium: ${smc['equilibrium']}\n"
                f"• 🔵 Demand Floor: {smc['demand_zone']} (Retest: ${smc['retest_sup']})\n\n"
                f"📰 *DXY & USD Fundamentals:*\n"
                f"• DXY: {smc['dxy_bias']}\n"
                f"{news_block}\n\n"
                f"🧠 *Mentor Rule:* Never chase mid-range candles. Wait for a liquidity sweep into Supply/Demand + 5m structure shift.\n"
                f"⚠️ _Educational analysis only. Manage risk._"
            ),
            "recap_enabled": False,
            "recap_spoken_script": ""
        }

    result["smc"] = smc

    history = []
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            history = json.load(f)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    saved_5m = f"assets/history_{ts}_5m.png"
    img_5m.save(saved_5m)

    history.append({
        "timestamp": ts,
        "session": session_name,
        "strong_high": smc["strong_high"],
        "equilibrium": smc["equilibrium"],
        "strong_low": smc["strong_low"],
        "saved_5m_chart": saved_5m,
        "evaluated": False
    })

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

    await capture_tradingview_charts()
    out = generate_ai_analysis(smc, news, session, played_out)
    print(f"✅ Phase 3 AI Mentor complete for {session}. Bonus Recap Triggered: {out.get('recap_enabled')}")

if __name__ == "__main__":
    asyncio.run(main())
