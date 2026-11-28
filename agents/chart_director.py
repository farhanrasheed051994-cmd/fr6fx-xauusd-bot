import os
import re
import json
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()


def load_winning_hook():
    if os.path.exists("state/winning_hooks.json"):
        try:
            with open("state/winning_hooks.json", "r", encoding="utf-8") as f:
                return json.load(f).get("best_hook_formula", "Question Hook + Live Liquidity Level")
        except Exception:
            pass
    return "Question Hook + Live Liquidity Level"


def clean_spoken_numbers(text):
    txt = re.sub(r"\$(\d+)\.\d+", r"\1", str(text))
    txt = re.sub(r"(\d{4})\.\d+", r"\1", txt)
    txt = txt.replace("$", "").replace("XAUUSDm", "Gold").replace("XAUUSD", "Gold")
    return txt.strip()


def run_chart_director(smc, session_name, gold_brain_analysis):
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    hook_style = load_winning_hook()

    live_int = int(round(float(smc["live_price"])))
    a_low_int = int(round(float(smc["asia_low"])))
    a_high_int = int(round(float(smc["asia_high"])))
    w_low_int = int(round(float(smc["watch_low"])))
    w_high_int = int(round(float(smc["watch_high"])))
    inv_int = int(round(float(smc["invalidation"])))

    prompt = f"""
You are ChartDirector, an elite TradingView Reel scriptwriter and visual choreographer for FR6FX.
Turn GoldBrain's institutional XAUUSD analysis into a 35-45 second human-sounding voiceover script
and structured chart cues for our Remotion TradingViewReel renderer.

SESSION: {session_name}
WINNING HOOK FORMULA: {hook_style}
GOLDBRAIN INSTITUTIONAL BRIEF:
- Bias: {gold_brain_analysis.get('institutional_bias')} (Confidence: {gold_brain_analysis.get('confidence_score')}%)
- Catalyst: {gold_brain_analysis.get('top_catalyst')}
- News Risk: {gold_brain_analysis.get('news_risk_warning')}
- Narrative: {gold_brain_analysis.get('market_narrative')}
- Execution Plan: {gold_brain_analysis.get('execution_plan')}

EXACT WHOLE-NUMBER PRICE LEVELS TO SPEAK:
- Live Gold: {live_int}
- Asia Range: {a_low_int} to {a_high_int}
- Watch Zone: {w_low_int} to {w_high_int}
- Invalidation: {inv_int}
- Setup: {smc['trade_setup']['direction']} (1:{smc['trade_setup']['rr']} R:R)

STRICT RULES:
1. Voiceover script must be 90 to 110 words (~36 seconds), conversational, authoritative, zero emojis, zero markdown, NO dollar signs ($), NO decimal cents—use whole integers only (e.g. say "{live_int}", not "${smc['live_price']}"). Say "Gold" instead of XAUUSD.
2. Start with a strong pattern-interrupt hook referencing the live price or liquidity sweep.
3. Explicitly mention the fundamental catalyst / DXY driver AND the exact SMC watch zone.
4. End with: "Full Smart Money breakdown and exact levels are posted free in our Telegram, link in bio."

Return ONLY valid JSON:
{{
  "hook_headline": "4-5 word punchy on-screen banner text in ALL CAPS",
  "voiceover_script": "90-110 word natural spoken script",
  "telegram_caption": "Clean 4-bullet institutional Telegram summary",
  "chart_focus": {{
    "highlight_asia": true,
    "highlight_fvg": true,
    "show_rr_box": true,
    "callout_label": "Short 2-3 word chart badge e.g. LONDON SWEEP"
  }}
}}
"""

    result = None
    if client:
        for model_name in ("gemini-3.1-pro-preview", "gemini-3.8-flash", "gemini-3.5-flash-lite"):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.45),
                )
                if resp and resp.text:
                    result = json.loads(resp.text)
                    print(f"🎬 ChartDirector script ready via {model_name}")
                    break
            except Exception as e:
                print(f"⚠️ ChartDirector {model_name} warning: {e}")

    if not result:
        result = {
            "hook_headline": f"GOLD {session_name.upper()} TRAP",
            "voiceover_script": (
                f"Look at Gold right now near {live_int} heading into the {session_name}. "
                f"{gold_brain_analysis.get('market_narrative', '')} "
                f"We are watching the liquidity zone between {w_low_int} and {w_high_int} "
                f"for a 5 minute change of character, with invalidation beyond {inv_int}. "
                f"With {gold_brain_analysis.get('top_catalyst', 'DXY flow')} in play, patience here separates liquidity from smart money. "
                f"Full Smart Money breakdown and exact levels are posted free in our Telegram, link in bio."
            ),
            "telegram_caption": (
                f"🟡 XAUUSD {session_name} Institutional Brief\n"
                f"• Spot: ${smc['live_price']} | Bias: {gold_brain_analysis.get('institutional_bias')}\n"
                f"• Catalyst: {gold_brain_analysis.get('top_catalyst')}\n"
                f"• Watch Zone: ${smc['watch_low']} - ${smc['watch_high']} (Inv: ${smc['invalidation']})"
            ),
            "chart_focus": {
                "highlight_asia": True,
                "highlight_fvg": True,
                "show_rr_box": True,
                "callout_label": "LIQUIDITY ZONE",
            },
        }

    result["voiceover_script"] = clean_spoken_numbers(result.get("voiceover_script", ""))
    return result
