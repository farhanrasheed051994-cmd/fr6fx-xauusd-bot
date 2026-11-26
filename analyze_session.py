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
from seo_engine import build_seo_package, load_optional_json


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
    txt = txt.replace("FVG", "fair value gap").replace("OB", "order block")
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

    research = load_optional_json("data/research_context.json", {})
    winning_hooks = load_optional_json("state/winning_hooks.json", {})

    macro_note = research.get("top_catalyst", "Normal session liquidity flow")
    hook_guidance = winning_hooks.get(
        "best_hook_formula",
        "Use specific Gold dollar numbers + curiosity gap (e.g., ASIA TRAP AT 2745?)"
    )

    live_p = smc["live_price"]
    s_high = smc["supply_high"]
    s_low = smc["supply_low"]
    d_high = smc["demand_high"]
    d_low = smc["demand_low"]
    eq = smc["equilibrium"]
    w_low = smc["watch_low"]
    w_high = smc["watch_high"]
    inv = smc["invalidation"]
    a_low = smc["asia_low"]
    a_high = smc["asia_high"]

    prompt = f"""
You are the lead Smart Money Concepts (SMC) strategist & viral short-form scriptwriter for @FR6FX.
Return ONLY valid JSON based on these live MT5 XAUUSDm metrics.

LIVE METRICS ({session_name} | {today_label}):
- Gold Price: ${live_p} ({smc['pct_change']}%) | Bias: {smc['bias_label']}
- Asia Range: ${a_low} – ${a_high} | Liquidity Event: {smc['pa_signal']}
- H1: {smc['h1_structure']} | M15: {smc['structure_tag']} | DXYm: {smc['dxy_bias']}
- Supply Resistance Zone: ${s_low} – ${s_high} | If broken -> Next Expansion Zone: {smc['next_supply_zone']}
- Demand Support Zone: ${d_low} – ${d_high} | If broken -> Next Expansion Zone: {smc['next_demand_zone']}
- 50% Equilibrium: ${eq} | Primary Watch Zone: ${w_low} – ${w_high} | Invalidation: ${inv}
- Macro / News Catalyst: {macro_note}
- Proven Winning Hook Guidance: {hook_guidance}

REQUIREMENTS:
1. "hook_title": Bold 3-to-4 word curiosity hook in ALL CAPS, STRICTLY <= 22 chars (e.g. "ASIA TRAP AT {int(round(a_high))}?" or "GOLD NEXT ZONE {int(round(smc['bull_tp1']))}").
2. "spoken_script": High-retention 30-second institutional voiceover (~75 words), whole integers only, NO dollar signs, say "Gold" not XAUUSD:
   - Beat 1 (Pattern-Interrupt Hook & Session Trap): Start with a punchy 1-sentence hook about Gold near {int(round(live_p))} and the Asia range ({int(round(a_low))} to {int(round(a_high))}).
   - Beat 2 (Must include word "resistance"): Explain Supply resistance at {int(round(s_high))} and next upside target {int(round(smc['bull_tp1']))} if broken.
   - Beat 3 (Must include word "support"): Explain Demand support at {int(round(d_low))} and next downside target {int(round(smc['bear_tp1']))} if broken.
   - Beat 4 (Must include phrase "watch zone"): Highlight the primary watch zone ({int(round(w_low))} to {int(round(w_high))}).
   - Beat 5 (Must include "5 minute" or "dropping"): Tell traders to drop to the 5 minute chart for a structure shift, never chase, and follow FR6 FX / join our free Telegram link in bio.
3. "telegram_report": Institutional Telegram breakdown (1,100–1,400 chars) using ONLY <b>, <i>, <code> tags. Include Asia Range, Liquidity Sweep, Macro Catalyst, Supply/Demand OBs, Primary Watch Zone, and BOTH Breakout Expansion Scenarios.

Return ONLY JSON:
{{
  "hook_title": "HOOK <= 22 CHARS",
  "date_label": "{today_label}",
  "session": "{session_name}",
  "spoken_script": "75-word session story & next-zone voiceover",
  "telegram_report": "HTML Telegram breakdown"
}}
"""
    result = None

    if os.environ.get("GEMINI_API_KEY"):
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
            http_options=types.HttpOptions(timeout=120_000),
        )
        img_stage4 = Image.open("assets/stage_4.png").resize((540, 540), Image.Resampling.LANCZOS)
        img_stage5 = Image.open("assets/stage_5.png").resize((540, 540), Image.Resampling.LANCZOS)

        for model_name in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=(prompt, img_stage4, img_stage5),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.4,
                    ),
                )
                if response and response.text:
                    result = json.loads(response.text)
                    print(f"✅ AI analysis generated using {model_name}")
                    break
            except Exception as e:
                print(f"⚠️ {model_name} busy: {e}")

    if not result and os.environ.get("GROQ_API_KEY"):
        groq_url = "https://groq.com"
        for g_model in ("llama-3.3-70b-versatile", "openai/gpt-oss-120b"):
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
                            {"role": "system", "content": "Return ONLY raw valid JSON."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.4,
                    },
                    timeout=25,
                )
                if g_resp.status_code == 200:
                    raw_txt = g_resp.json()["choices"][0]["message"]["content"].strip()
                    raw_txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_txt)
                    if raw_txt:
                        result = json.loads(raw_txt)
                        print(f"✅ AI analysis generated using Groq ({g_model})")
                        break
            except Exception as e:
                print(f"⚠️ Groq {g_model} warning: {e}")

    is_bull = "BULLISH" in str(smc.get("bias_label", ""))
    if result:
        result["spoken_script"] = clean_spoken_text(result.get("spoken_script", ""))
        result["hook_title"] = str(result.get("hook_title", "GOLD LIQUIDITY MAP")).upper()[:22]
    else:
        hook_def = f"ASIA TRAP AT {int(round(a_high))}?" if not is_bull else f"GOLD NEXT ZONE {int(round(smc['bull_tp1']))}"
        result = {
            "hook_title": hook_def[:22],
            "date_label": today_label,
            "session": session_name,
            "spoken_script": (
                f"During Asia, Gold built liquidity between {int(round(a_low))} and {int(round(a_high))}, now trading near {int(round(live_p))}. "
                f"Resistance sits at {int(round(s_high))}, and if buyers break above it, the next expansion target is {int(round(smc['bull_tp1']))}. "
                f"Support holds at {int(round(d_low))}, and if that breaks, the next downside target is {int(round(smc['bear_tp1']))}. "
                f"Our primary watch zone is {int(round(w_low))} to {int(round(w_high))}. "
                f"Dropping to the 5 minute chart, wait for a structure shift and never chase. "
                f"Follow FR6 FX and join our free Telegram link in bio."
            ),
            "telegram_report": (
                f"🟡 <b>FR6 FX | XAUUSD {session_name}</b> ({today_label})\n"
                f"💰 Spot: <b>${live_p}</b> ({smc['pct_change']}%)  |  <b>{smc['bias_label']}</b>\n\n"
                f"🌊 <b>SESSION LIQUIDITY & FLOW</b>\n"
                f"• <b>Asia Range:</b> <code>${a_low} – ${a_high}</code>\n"
                f"• <b>Liquidity Read:</b> {smc['pa_signal']}\n"
                f"• <b>H1 / M15:</b> {smc['h1_structure']} | {smc['structure_tag']}\n"
                f"• <b>DXYm:</b> {smc['dxy_bias']}\n\n"
                f"🎯 <b>PRIMARY & NEXT EXPANSION ZONES</b>\n"
                f"• 🔴 <b>Supply Resistance:</b> <code>${s_low} – ${s_high}</code>\n"
                f"  ↳ <i>If broken above ${s_high}:</i> Next Bullish Zone <code>{smc['next_supply_zone']}</code>\n"
                f"• ⚖️ <b>50% Equilibrium:</b> <code>${eq}</code>\n"
                f"• 🔵 <b>Demand Support:</b> <code>${d_low} – ${d_high}</code>\n"
                f"  ↳ <i>If broken below ${d_low}:</i> Next Bearish Zone <code>{smc['next_demand_zone']}</code>\n\n"
                f"⚡ <b>EXECUTION PLAN</b>\n"
                f"• 🟡 <b>Primary Watch Zone:</b> <code>${w_low} – ${w_high}</code> (Invalidation <code>${inv}</code>)\n"
                f"• 🧠 <b>Rule:</b> Wait for M5 CHoCH confirmation inside the Watch Zone—never chase.\n\n"
                f"📲 Daily markups: https://{tg_link}\n"
                f"⚠️ <i>Educational analysis only. Not financial advice.</i>"
            ),
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
    print(f"✅ Analysis complete for {session} | Hook: {out.get('hook_title')} | R:R 1:{smc['trade_setup']['rr']}")


if __name__ == "__main__":
    main()
