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
            "setup": f"Discount Support bounce at ${strong_low} -> Equilibrium ${eq}",
            "old_session": prev["session"],
            "old_chart": prev["saved_5m_chart"]
        }
    elif h6 >= (strong_high - 2.5) and l6 <= eq:
        outcome = {
            "won": True,
            "setup": f"Premium Resistance rejection at ${strong_high} -> Equilibrium ${eq}",
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
    port = server.server_address[1]
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
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    img_15m = Image.open("assets/tv_15m.png")
    img_5m = Image.open("assets/tv_5m.png")

    today_label = datetime.now(timezone.utc).strftime("%d %b %Y")

    recap_prompt = ""
    if played_out and played_out.get("won"):
        recap_prompt = f"""
        BONUS RECAP TRIGGERED: Our previous {played_out['old_session']} call ({played_out['setup']}) JUST PLAYED OUT!
        Set "recap_enabled": true and write a punchy 15-second phonetic 'recap_spoken_script' showing viewers how our FR6 FX level hit target to the dollar.
        """

    prompt = f"""
    You are the lead XAUUSD Technical & Fundamental analyst for @FR6FX.
    Create a calm, authoritative, human-sounding 40-to-45 second vertical video script for the {session_name} on {today_label}.

    EXACT LIVE TECHNICAL & FUNDAMENTAL DATA (Use these exact numbers):
    - Live Gold Price: ${smc['live_price']} ({smc['pct_change']}%)
    - Major Resistance / Red Premium Cap: ${smc['strong_high']} (Intraday Resistance: ${smc['intraday_res']})
    - 50% Equilibrium Pivot: ${smc['equilibrium']}
    - Major Support / Blue Discount Floor: ${smc['strong_low']} (Intraday Support: ${smc['intraday_sup']})
    - Recent Price Action / Sweep: {smc['sweep_event']}
    - 5m EMA 20: ${smc['ema20']} | 5m EMA 50: ${smc['ema50']} ({smc['ema_bias']})
    - DXY Macro Impact: {smc['dxy_bias']}
    - Overall Bias: {smc['bias_label']} ({smc['bias_score']}/100)
    - Fundamental Drivers Today: {', '.join(news)}

    INSPECT BOTH ATTACHED LIVE TRADINGVIEW CHARTS (15m & 5m) and write a clear, structured trader breakdown:
    1. HOOK (0-5s): State the live Gold price (${smc['live_price']}), current {smc['bias_label']}, and the key sweep/rejection happening right now.
    2. SUPPORT & RESISTANCE ZONES (5-18s): Explain the Red Resistance Zone (${smc['strong_high']}), 50% Equilibrium (${smc['equilibrium']}), and Blue Support Zone (${smc['strong_low']}), plus how EMA 20/50 is acting as dynamic support or resistance.
    3. DXY & FUNDAMENTAL IMPACT (18-30s): Explain how the US Dollar Index ({smc['dxy_now']}) and today's fundamental news ({news}) are pushing or supporting Gold.
    4. SCENARIO PREDICTION & CTA (30-42s): Give clear "If/Then" watchable zones (e.g. holding above ${smc['intraday_sup']} targets ${smc['equilibrium']}/${smc['intraday_res']}; breaking below opens ${smc['strong_low']}) — strictly educational, never guarantee profits. End with: "Are you watching support buys or resistance sells this session? Drop your bias below."
    5. CRITICAL VOICE RULE: In 'spoken_script', write numbers cleanly without awkward decimals (e.g., "thirty-five fifty-six" instead of "$3556.50") so the voice sounds completely human and unhurried.
    {recap_prompt}

    Return ONLY valid JSON:
    {{
      "date_label": "{today_label}",
      "session": "{session_name}",
      "headline": "XAUUSD {session_name} OUTLOOK",
      "spoken_script": "Full 42-second clear phonetic voiceover script (approx 95-105 words)",
      "youtube_title": "XAUUSD Live Technical & Fundamental Analysis ({today_label}) | {session_name.title()} #Shorts",
      "social_caption": "Clean structured breakdown with Resistance, Support, Equilibrium, DXY Impact, Fundamental Catalyst, Watchable Scenarios, Follow @FR6FX CTA, and educational disclaimer (NO hashtags here)",
      "recap_enabled": false,
      "recap_spoken_script": ""
    }}
    """

    models_to_try = ["gemini-3.8-flash", "gemini-3.5-flash-lite"]
    response = None

    for model_name in models_to_try:
        for attempt in range(3):
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
                time.sleep(6)
        if response and response.text:
            print(f"✅ AI analysis generated using {model_name}")
            break

    if response and response.text:
        result = json.loads(response.text)
    else:
        print("🔄 Gemini busy—using built-in Technical & Fundamental fallback script...")
        result = {
            "date_label": today_label,
            "session": session_name,
            "headline": f"XAUUSD {session_name} OUTLOOK",
            "spoken_script": (
                f"Gold is trading near {int(smc['live_price'])} heading into the {session_name} with a {smc['bias_label'].lower()}. "
                f"Right now we are seeing {smc['sweep_event']}. "
                f"Key resistance sits at the red premium zone around {int(smc['strong_high'])}, fifty percent equilibrium is at {int(smc['equilibrium'])}, and major support rests at the blue discount floor near {int(smc['strong_low'])}. "
                f"On the macro side, DXY is {smc['dxy_bias']}, while {news} drives fundamental flow. "
                f"Watch for a liquidity sweep and rejection at support or resistance before confirming entries. Are you watching buys or sells this session? Comment below."
            ),
            "youtube_title": f"XAUUSD Live Technical & Fundamental Analysis ({today_label}) | {session_name.title()} #Shorts",
            "social_caption": (
                f"📊 XAUUSD {session_name} OUTLOOK ({today_label})\n\n"
                f"🔴 Major Resistance: ${smc['strong_high']} (Intraday: ${smc['intraday_res']})\n"
                f"⚖️ 50% Equilibrium: ${smc['equilibrium']}\n"
                f"🔵 Major Support: ${smc['strong_low']} (Intraday: ${smc['intraday_sup']})\n"
                f"📈 5m EMA 20 / 50: ${smc['ema20']} / ${smc['ema50']}\n"
                f"💵 DXY Impact: {smc['dxy_bias']}\n"
                f"📰 Fundamentals: {news}\n\n"
                f"💾 Save this post & follow @FR6FX for daily live Gold levels!\n"
                f"⚠️ Educational purposes only. Not financial advice."
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
    print(f"✅ Phase 3 AI Brain complete for {session}. Bonus Recap Triggered: {out.get('recap_enabled')}")

if __name__ == "__main__":
    asyncio.run(main())
