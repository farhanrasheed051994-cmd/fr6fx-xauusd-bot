import os
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright
from google import genai
from google.genai import types
from PIL import Image
from smc_engine import get_smc_market_data, get_usd_high_impact_news

MEMORY_FILE = "predictions.json"

def detect_session():
    utc_hour = datetime.now(timezone.utc).hour
    if 4 <= utc_hour <= 9:
        return "LONDON OPEN"
    elif 10 <= utc_hour <= 15:
        return "NEW YORK OPEN"
    return "LIVE SESSION"

def check_previous_call_played_out(smc):
    """Checks if the previous session's Strong Low buy or Strong High sell played out."""
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
    # Did price sweep/tap Strong Low discount floor and rally back to Equilibrium?
    if l6 <= (strong_low + 2.5) and h6 >= eq:
        outcome = {
            "won": True,
            "setup": f"Discount Floor Buy at ${strong_low} -> Equilibrium ${eq}",
            "old_session": prev["session"],
            "old_chart": prev["saved_5m_chart"]
        }
    # Did price tap Strong High premium cap and drop back to Equilibrium?
    elif h6 >= (strong_high - 2.5) and l6 <= eq:
        outcome = {
            "won": True,
            "setup": f"Premium Cap Sell at ${strong_high} -> Equilibrium ${eq}",
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
    html_uri = Path("tv_chart.html").resolve().as_uri()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 540, "height": 620},
            device_scale_factor=2
        )
        page = await context.new_page()

        await page.goto(f"{html_uri}?interval=15", wait_until="networkidle")
        await page.wait_for_timeout(5000)
        await page.screenshot(path="assets/tv_15m.png")

        await page.goto(f"{html_uri}?interval=5", wait_until="networkidle")
        await page.wait_for_timeout(5000)
        await page.screenshot(path="assets/tv_5m.png")

        await browser.close()

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
    You are the lead XAUUSD Smart Money Concepts analyst for @FR6FX.
    Create a fast-paced, human-sounding 35-to-40 second vertical video script for the {session_name} on {today_label}.

    EXACT LIVE NUMBERS (Use these exact numbers):
    - Live Gold Price: ${smc['live_price']} ({smc['pct_change']}%)
    - Red Premium Zone (Strong High): ${smc['strong_high']}
    - 50% Equilibrium: ${smc['equilibrium']}
    - Blue Discount Zone (Strong Low): ${smc['strong_low']}
    - 5m EMA 20: ${smc['ema20']} | 5m EMA 50: ${smc['ema50']}
    - DXY Correlation: {smc['dxy_bias']}
    - Status: {smc['zone_status']}
    - USD News: {', '.join(news)}

    INSPECT BOTH ATTACHED LIVE TRADINGVIEW CHARTS (15m & 5m) and write a natural, human trader script:
    1. Start with a strong hook (0-4s) stating the exact live Gold price and session ({session_name}).
    2. Break down the Red Premium Strong High (${smc['strong_high']}), 50% Equilibrium (${smc['equilibrium']}), and Blue Discount Strong Low (${smc['strong_low']}).
    3. Explain the 5m EMA 20/50 alignment and give clear liquidity-sweep confirmation rules (educational only, never guarantee profit).
    4. End with a seamless loop + comment CTA ("Are you watching buys at the discount floor or sells at the premium cap? Comment below").
    5. CRITICAL VOICE RULE: In 'spoken_script', write numbers phonetically how a human trader speaks (e.g., "thirty-seven nineteen" instead of "$3719.00", "fifty percent equilibrium").
    {recap_prompt}

    Return ONLY valid JSON:
    {{
      "date_label": "{today_label}",
      "session": "{session_name}",
      "hook_banner": "3-4 WORD PUNCHY HOOK (e.g. GOLD TRAP AT ${smc['live_price']}?)",
      "spoken_script": "Full 38-second phonetic voiceover script (approx 85-95 words)",
      "youtube_title": "{session_name.title()} Gold Live TradingView Analysis ({today_label}) | XAUUSD #Shorts",
      "social_caption": "Structured caption with exact Strong High, Equilibrium, Strong Low, EMA 20/50 levels, Follow @FR6FX CTA, educational disclaimer, and 5 hashtags",
      "recap_enabled": false,
      "recap_spoken_script": ""
    }}
    """

    response = client.models.generate_content(
        model="gemini-3.8-flash",
        contents=[prompt, img_15m, img_5m],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.4
        )
    )

    result = json.loads(response.text)
    result["smc"] = smc

    # Save snapshot to predictions.json memory
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
    news = get_usd_high_impact_news()
    played_out = check_previous_call_played_out(smc)

    await capture_tradingview_charts()
    out = generate_ai_analysis(smc, news, session, played_out)
    print(f"✅ Phase 3 AI Brain complete for {session}. Bonus Recap Triggered: {out.get('recap_enabled')}")

if __name__ == "__main__":
    asyncio.run(main())
