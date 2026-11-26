import os
import re
import json
import requests
from datetime import datetime, timezone
from google import genai
from google.genai import types
from PIL import Image
from smc_engine import get_smc_market_data
from chart_renderer import build_progressive_chart_stages
from seo_engine import build_seo_package


def detect_session():
    utc_hour = datetime.now(timezone.utc).hour
    if 4 <= utc_hour <= 11:
        return "LONDON SESSION"
    elif 12 <= utc_hour <= 19:
        return "NEW YORK SESSION"
    return "ASIAN SESSION"


def clean_spoken_text(raw_text):
    txt = re.sub(r"\$(\d+)\.\d+", r"\1", str(raw_text))
    txt = re.sub(r"(\d+)\.\d+", r"\1", txt)
    txt = txt.replace("$", "")
    txt = txt.replace("XAUUSDm", "Gold").replace("XAUUSD", "Gold").replace("xauusd", "Gold")
    txt = txt.replace("DXYm", "DXY")
    txt = txt.replace("Buy-side", "Buy side").replace("buy-side", "buy side")
    txt = txt.replace("Sell-side", "Sell side").replace("sell-side", "sell side")
    txt = txt.replace("FVG", "fair value gap")
    txt = txt.replace("OB", "order block")
    txt = txt.replace("BOS", "break of structure").replace("CHoCH", "change of character")
    return txt.strip()


def generate_ai_analysis(smc, session_name):
    today_label = datetime.now(timezone.utc).strftime("%d %b %Y")
    tg_link = (
        os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official")
        .replace("https://", "")
        .replace("http://", "")
        .strip()
    )

    is_bull = "BULLISH" in str(smc.get("bias_label", ""))
    live_p = smc["live_price"]
    s_high = smc["strong_high"]
    s_low = smc["strong_low"]
    eq = smc["equilibrium"]
    sup_z = smc["supply_zone"]
    dem_z = smc["demand_zone"]
    w_low = smc["watch_low"]
    w_high = smc["watch_high"]
    inv = smc["invalidation"]
    tp1 = smc["tp1"]
    tp2 = smc["tp2"]

    prompt = f"""
You are the head Smart Money Concepts (SMC) analyst for @FR6FX.
Analyze the live MT5 XAUUSDm chart images and institutional metrics below, then return ONLY valid JSON.

LIVE MT5 DATA ({session_name} | {today_label}):
- Live Gold Price: ${live_p} ({smc['pct_change']}%) | Overall Bias: {smc['bias_label']} (Score {smc['bias_score']}/100)
- H1 Structure: {smc['h1_structure']}
- M15 Structure: {smc['structure_tag']}
- Liquidity Read: {smc['pa_signal']}
- Institutional Supply OB: {sup_z} | Institutional Demand OB: {dem_z}
- 50% Equilibrium: ${eq} | Fair Value Gaps: {smc['fvg_note']}
- Primary Watch Zone: ${w_low} – ${w_high} | Invalidation: ${inv} | TP1: ${tp1} | TP2: ${tp2}
- Session Ranges: PDH ${smc['pdh']} / PDL ${smc['pdl']} | Asia ${smc['asia_low']}-${smc['asia_high']} | London ${smc['london_low']}-${smc['london_high']}
- Momentum: {smc['ema_bias']} | RSI(14): {smc['rsi']}
- DXYm Correlation: {smc['dxy_bias']}

REQUIREMENTS:
1. "hook_title": A bold 4-to-6 word curiosity hook in ALL CAPS for the top of the vertical Reel (e.g., "GOLD LIQUIDITY TRAP AT {int(round(s_high))}?" or "WATCH THIS GOLD ORDER BLOCK"). No generic titles.
2. "spoken_script": A punchy, high-retention 28-second voiceover (~70–75 words). Must follow this exact sequence so chart animations sync cleanly:
   - Sentence 1 (Hook + Bias): State current Gold price ({int(round(live_p))}) and the immediate liquidity/structure setup.
   - Sentence 2 (Resistance): Mention key resistance at {int(round(s_high))}.
   - Sentence 3 (Support): Mention major support at {int(round(s_low))}.
   - Sentence 4 (Watch Zone): Say the exact phrase "Watch zone" and state {int(round(w_low))} to {int(round(w_high))}.
   - Sentence 5 (M5 Execution): Say "Dropping to the 5 minute chart" and explain waiting for a confirmation candle—never chasing.
   - Sentence 6 (CTA): End with "Follow FR6 FX and join our free Telegram in the bio for daily Gold setups."
   CRITICAL: Write ALL numbers as clean whole integers (no decimals, no dollar signs) and always say "Gold" instead of XAUUSD.
3. "telegram_report": An institutional, ultra-clean Telegram breakdown (1,100–1,450 chars) using ONLY Telegram HTML tags (<b>, <i>, <code>). Include:
   - Header with session, spot price, and bias
   - Multi-timeframe structure & liquidity read (H1 + M15 + DXYm)
   - Exact Institutional Zones (Supply OB, 50% Equilibrium, Demand OB, FVG)
   - Clear <b>IF / THEN EXECUTION PLAN</b> (Bullish Scenario trigger + targets vs. Bearish Scenario trigger + targets, plus exact Invalidation level)
   - Short risk reminder & "Not financial advice."

Return ONLY valid JSON:
{{
  "hook_title": "BOLD 4-6 WORD HOOK",
  "date_label": "{today_label}",
  "session": "{session_name}",
  "spoken_script": "Clean 75-word voiceover script",
  "telegram_report": "HTML formatted institutional Telegram report"
}}
"""
    result = None

    if os.environ.get("GEMINI_API_KEY"):
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
            http_options={"timeout": 45}
        )
        img_stage4 = Image.open("assets/stage_4.png").resize((540, 495), Image.Resampling.LANCZOS)
        img_stage5 = Image.open("assets/stage_5.png").resize((540, 495), Image.Resampling.LANCZOS)

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
        groq_url = "https://groq.com"
        for g_model in ("openai/gpt-oss-120b", "openai/gpt-oss-20b"):
            try:
                g_resp = requests.post(
                    groq_url,
                    headers={
                        "Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '').strip()}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": g_model,
                        "messages": [
                            {"role": "system", "content": "Return ONLY raw valid JSON without markdown code fences."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.35
                    },
                    timeout=25
                )
                if g_resp.status_code == 200:
                    raw_txt = g_resp.json()["choices"][0]["message"]["content"].strip()
                    raw_txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_txt)
                    if raw_txt:
                        result = json.loads(raw_txt)
                        print(f"✅ AI Mentor analysis generated using Groq ({g_model})")
                        break
            except Exception as e:
                print(f"⚠️ Groq {g_model} warning: {e}")

    if result:
        result["spoken_script"] = clean_spoken_text(result.get("spoken_script", ""))
        result["hook_title"] = str(result.get("hook_title", f"GOLD {session_name} SETUP")).upper()[:42]
    else:
        print("🔄 Using built-in institutional fallback analysis...")
        hook_default = (
            f"GOLD DEMAND TRAP AT {int(round(s_low))}?"
            if is_bull else f"GOLD SUPPLY REJECTION AT {int(round(s_high))}?"
        )
        result = {
            "hook_title": hook_default,
            "date_label": today_label,
            "session": session_name,
            "spoken_script": (
                f"Gold is trading near {int(round(live_p))} entering the {session_name.lower()} with a {smc['bias_label'].lower()}. "
                f"Key resistance holds at {int(round(s_high))}. "
                f"Major support sits at {int(round(s_low))}. "
                f"Our primary watch zone is between {int(round(w_low))} and {int(round(w_high))}. "
                f"Dropping to the 5 minute chart, wait for a clean confirmation candle before entering and never chase. "
                f"Follow FR6 FX and join our free Telegram in the bio for daily Gold setups."
            ),
            "telegram_report": (
                f"🟡 <b>FR6 FX | XAUUSD {session_name}</b> ({today_label})\n"
                f"💰 Spot: <b>${live_p}</b> ({smc['pct_change']}%)  |  <b>{smc['bias_label']}</b>\n\n"
                f"📐 <b>MULTI-TIMEFRAME STRUCTURE</b>\n"
                f"• <b>H1:</b> {smc['h1_structure']}\n"
                f"• <b>M15:</b> {smc['structure_tag']}\n"
                f"• <b>Liquidity:</b> {smc['pa_signal']}\n"
                f"• <b>DXYm:</b> {smc['dxy_bias']}\n\n"
                f"🎯 <b>INSTITUTIONAL LEVELS</b>\n"
                f"• 🔴 Supply OB: <code>{sup_z}</code>\n"
                f"• ⚖️ 50% Equilibrium: <code>${eq}</code>\n"
                f"• 🔵 Demand OB: <code>{dem_z}</code>\n"
                f"• 🕳️ Imbalance: {smc['fvg_note']}\n"
                f"• 📊 PDH / PDL: <code>${smc['pdh']}</code> / <code>${smc['pdl']}</code>\n\n"
                f"⚡ <b>IF / THEN EXECUTION PLAN</b>\n"
                f"• 🟢 <b>Bullish Scenario:</b> Hold & M5 bullish CHoCH inside <code>{dem_z}</code> → Targets <code>${eq}</code> & <code>${sup_z.split('–')[0].strip()}</code>.\n"
                f"• 🔴 <b>Bearish Scenario:</b> Rejection & M5 bearish displacement inside <code>{sup_z}</code> → Targets <code>${eq}</code> & <code>${dem_z.split('–')[-1].strip()}</code>.\n"
                f"• 🛑 <b>Primary Watch Zone:</b> <code>${w_low} – ${w_high}</code> (Invalidation: <code>${inv}</code>)\n\n"
                f"📲 Daily markups: https://{tg_link}\n"
                f"⚠️ <i>Educational analysis only. Not financial advice.</i>"
            )
        }

    result["smc"] = smc
    result["seo"] = build_seo_package(smc, session_name, result)

    os.makedirs("assets", exist_ok=True)
    with open("assets/analysis_output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def main():
    session = detect_session()
    smc = get_smc_market_data()
    build_progressive_chart_stages(smc)
    out = generate_ai_analysis(smc, session)
    print(f"✅ Analysis complete for {session} | Hook: {out.get('hook_title')}")


if __name__ == "__main__":
    main()
