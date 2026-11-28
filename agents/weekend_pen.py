import os
import sys
import json
from google import genai
from google.genai import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from smc_engine import get_smc_market_data
from agents.gold_brain import retrieve_trained_rules
from agents.reach_boost import run_reach_boost

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()


def run_weekend_pen():
    if not os.path.exists("data/weekend_trends.json"):
        raise FileNotFoundError("Run agents/trend_radar.py first.")

    with open("data/weekend_trends.json", "r", encoding="utf-8") as f:
        trends = json.load(f)

    smc = get_smc_market_data()
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    trained_rules = retrieve_trained_rules(client, "XAUUSD Smart Money Concepts liquidity sweep risk management", top_k=4)
    rules_str = "\n".join(trained_rules) if trained_rules else "FR6FX Core SMC Playbook"

    queue = []
    for item in trends.get("topics", [])[:4]:
        prompt = f"""
You are WeekendPen, an elite short-form trading scriptwriter for FR6FX.
Write a 38-second educational/recap Reel script for XAUUSD using Friday's closing chart levels and the trader's personal SMC rules.

SLOT: {item['slot']} | LABEL: {item['session_label']}
TOPIC: {item['topic']}
ANGLE: {item['angle']}
FRIDAY CLOSING LEVELS:
- Gold Close: ${smc['live_price']} | Asia Range: ${smc['asia_low']}-${smc['asia_high']}
- Watch Zone: ${smc['watch_low']}-${smc['watch_high']} | Supply: {smc['supply_zone']} | Demand: {smc['demand_zone']}
TRADER'S PERSONAL RULES:
{rules_str}

RULES:
- 95 to 115 words spoken script, zero emojis, zero markdown, energetic human mentor tone.
- Reference the actual chart levels visible on screen so the Remotion chart matches what you say.
- End with: "Save this for Monday's open and join our free Telegram channel in bio."

Return ONLY valid JSON:
{{
  "hook_headline": "4-6 word punchy banner text",
  "voiceover_script": "95-115 word natural spoken script",
  "telegram_caption": "Clean 4-bullet educational Telegram summary",
  "chart_focus": {{
    "highlight_asia": true,
    "highlight_fvg": true,
    "show_rr_box": true,
    "callout_label": "2-3 word chart badge"
  }}
}}
"""
        script_obj = None
        if client:
            for model_name in ("gemini-3.8-flash", "gemini-3.1-pro-preview"):
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.5),
                    )
                    if resp and resp.text:
                        script_obj = json.loads(resp.text)
                        break
                except Exception as e:
                    print(f"⚠️ WeekendPen {model_name} warning: {e}")

        if not script_obj:
            script_obj = {
                "hook_headline": item["topic"][:36].upper(),
                "voiceover_script": (
                    f"{item['topic']}. Look at Friday's Gold chart around {smc['live_price']}. "
                    f"Most retail traders chase breakouts right into the {smc['supply_zone']} supply zone without waiting for liquidity to sweep. "
                    f"Instead, mark the {smc['watch_low']} to {smc['watch_high']} zone and wait for a clean five-minute change of character. "
                    f"Save this for Monday's open and join our free Telegram channel in bio."
                ),
                "telegram_caption": f"📚 <b>{item['topic']}</b>\n• Key Watch Zone: ${smc['watch_low']} - ${smc['watch_high']}\n• Save this breakdown before Monday's Asian session!",
                "chart_focus": {"highlight_asia": True, "highlight_fvg": True, "show_rr_box": True, "callout_label": "WEEKEND LESSON"},
            }

        seo_pkg = run_reach_boost(
            topic_title=item["topic"],
            session_name=item["session_label"],
            bias_label=smc["bias_label"],
            catalyst=item["angle"],
            live_price=f"${smc['live_price']}",
        )

        queue.append({
            "slot": item["slot"],
            "session_label": item["session_label"],
            "hook_headline": script_obj["hook_headline"],
            "voiceover_script": script_obj["voiceover_script"],
            "telegram_caption": script_obj["telegram_caption"],
            "chart_focus": script_obj.get("chart_focus", {}),
            "seo": seo_pkg,
            "used": False,
        })
        print(f"✍️ WeekendPen drafted Reel {item['slot']}: {script_obj['hook_headline']}")

    os.makedirs("queue", exist_ok=True)
    with open("queue/weekend_reels.json", "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)
    print("✅ Saved 4 weekend Reels to queue/weekend_reels.json")


if __name__ == "__main__":
    sys.argv.append("--weekend")
    run_weekend_pen()
