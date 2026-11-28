import os
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


def run_chart_director(smc, session_name, gold_brain_analysis):
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    hook_style = load_winning_hook()

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

EXACT PRICE LEVELS TO INCLUDE:
- Live Gold: ${smc['live_price']}
- Asia Range: ${smc['asia_low']} - ${smc['asia_high']}
- Watch Zone: ${smc['watch_low']} - ${smc['watch_high']}
- Invalidation: ${smc['invalidation']}
- Setup: {smc['trade_setup']['direction']} Entry ${smc['trade_setup']['entry']} | SL ${smc['trade_setup']['sl']} | TP ${smc['trade_setup']['tp']} (1:{smc['trade_setup']['rr']})

STRICT RULES:
1. Voiceover script must be 95 to 115 words (around 38 seconds), conversational, authoritative, zero robotic intros, zero emojis, zero markdown.
2. Start with a strong pattern-interrupt hook referencing the live price or liquidity sweep.
3. Explicitly mention the fundamental catalyst / DXY driver AND the exact SMC levels.
4. End with: "Full Smart Money breakdown and exact levels are posted free in our Telegram, link in bio."

Return ONLY valid JSON:
{{
  "hook_headline": "4-6 word punchy on-screen banner text",
  "voiceover_script": "95-115 word natural spoken script",
  "telegram_caption": "Clean 4-bullet institutional Telegram summary (no HTML broken tags)",
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
        for model_name in ("gemini-2.5-pro", "gemini-2.5-flash"):
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
                f"Look at Gold right now at {smc['live_price']} heading into the {session_name}. "
                f"{gold_brain_analysis.get('market_narrative', '')} "
                f"We are watching the liquidity zone between {smc['watch_low']} and {smc['watch_high']} "
                f"for an M5 change of character, with invalidation beyond {smc['invalidation']}. "
                f"With {gold_brain_analysis.get('top_catalyst', 'DXY pressure')} in play, patience here separates liquidity from smart money. "
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

    return result
