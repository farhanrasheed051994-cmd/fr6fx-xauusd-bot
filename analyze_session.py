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

    live_p = smc["live_price"]
    s_high = smc["supply_high"]
    s_low = smc["supply_low"]
    d_high = smc["demand_high"]
    d_low = smc["demand_low"]
    eq = smc["equilibrium"]
    w_low = smc["watch_low"]
    w_high = smc["watch_high"]
    inv = smc["invalidation"]

    prompt = f"""
You are the head Smart Money Concepts (SMC) analyst for @FR6FX.
Return ONLY valid JSON based on the exact MT5 XAUUSDm metrics below.

METRICS ({session_name} | {today_label}):
- Live Gold: ${live_p} ({smc['pct_change']}%) | Bias: {smc['bias_label']} ({smc['bias_score']}/100)
- H1: {smc['h1_structure']} | M15: {smc['structure_tag']}
- Liquidity: {smc['pa_signal']} | DXY: {smc['dxy_bias']}
- Supply Resistance (above price): ${s_low} – ${s_high}
- Demand Support (below price): ${d_low} – ${d_high}
- 50% Equilibrium: ${eq} | Primary Watch Zone: ${w_low} – ${w_high}
- Bullish Scenario: Break & hold above ${s_high} -> TP1 ${smc['bull_tp1']}, TP2 ${smc['bull_tp2']} (SL below ${d_low})
- Bearish Scenario: Rejection at ${s_low} or break below ${d_low} -> TP1 ${smc['bear_tp1']}, TP2 ${smc['bear_tp2']} (SL above ${s_high})

STRICT RULES:
1. "hook_title": Bold 3-to-4 word hook in ALL CAPS, STRICTLY <= 22 characters (e.g. "GOLD TRAP AT {int(round(s_high))}?" or "GOLD KEY ZONE {int(round(w_low))}").
2. "spoken_script": Crisp 26-second voiceover (~65 words), whole integers only, NO dollar signs, say "Gold" not XAUUSD:
   - Hook Gold at {int(round(live_p))} and current liquidity/bias.
   - State "Resistance sits at {int(round(s_high))}."
   - State "Support holds at {int(round(d_low))}."
   - State "Our watch zone is {int(round(w_low))} to {int(round(w_high))}."
   - State "Dropping to the 5 minute chart, wait for confirmation and never chase."
   - End with "Follow FR6 FX and join our free Telegram in bio."
3. "telegram_report": Clean institutional Telegram post (1,000-1,300 chars) using ONLY <b>, <i>, <code> tags. Keep DXY decimal intact ({smc['dxy_now']}). Use the EXACT Bullish & Bearish targets given above.

Return ONLY JSON:
{{
  "hook_title": "SHORT HOOK <=22 CHARS",
  "date_label": "{today_label}",
  "session": "{session_name}",
  "spoken_script": "65-word clean voiceover",
  "telegram_report": "HTML Telegram report"
}}
"""
    result = None

    if os.environ.get("GEMINI_API_KEY"):
        client = genai.Client(
            api_key=os.environ.get("GEMINI_API_KEY"),
            http_options={"timeout": 45}
        )
        img_stage4 = Image.open("assets/stage_4.png").resize((540, 520), Image.Resampling.LANCZOS)
        img_stage5 = Image.open("assets/stage_5.png").resize((540, 520), Image.Resampling.LANCZOS)

        for model_name in ("gemini-2.5-flash", "gemini-2.5-flash-lite"):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=(prompt, img_stage4, img_stage5),
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.3
                    )
                )
                if response and response.text:
                    result = json.loads(response.text)
                    print(f"✅ AI analysis generated using {model_name}")
                    break
            except Exception as e:
                print(f"⚠️ {model_name} busy: {e}")

    if not result and os.environ.get("GROQ_API_KEY"):
        groq_url = "https://" + ".".join(["api", "groq", "com"]) + "/openai/v1/chat/completions"
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
                            {"role": "system", "content": "Return ONLY raw valid JSON."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3
                    },
                    timeout=25
                )
                if g_resp.status_code == 200:
                    raw_txt = g_resp.json().get("choices").__getitem__(0).get("message").get("content").strip()
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
        result["hook_title"] = str(result.get("hook_title", "GOLD KEY LEVELS")).upper()[:22]
    else:
        hook_def = f"GOLD DEMAND AT {int(round(d_low))}?" if is_bull else f"GOLD TRAP AT {int(round(s_high))}?"
        result = {
            "hook_title": hook_def[:22],
            "date_label": today_label,
            "session": session_name,
            "spoken_script": (
                f"Gold is trading near {int(round(live_p))} entering {session_name.lower()} with a {smc['bias_label'].lower()}. "
                f"Resistance sits at {int(round(s_high))}. "
                f"Support holds at {int(round(d_low))}. "
                f"Our watch zone is {int(round(w_low))} to {int(round(w_high))}. "
                f"Dropping to the 5 minute chart, wait for confirmation and never chase. "
                f"Follow FR6 FX and join our free Telegram in bio."
            ),
            "telegram_report": (
                f"🟡 <b>FR6 FX | XAUUSD {session_name}</b> ({today_label})\n"
                f"💰 Spot: <b>${live_p}</b> ({smc['pct_change']}%)  |  <b>{smc['bias_label']}</b>\n\n"
                f"📐 <b>STRUCTURE & FLOW</b>\n"
                f"• <b>H1:</b> {smc['h1_structure']}\n"
                f"• <b>M15:</b> {smc['structure_tag']}\n"
                f"• <b>Liquidity:</b> {smc['pa_signal']}\n"
                f"• <b>DXYm:</b> {smc['dxy_bias']}\n\n"
                f"🎯 <b>INSTITUTIONAL LEVELS</b>\n"
                f"• 🔴 Supply Resistance: <code>${s_low} – ${s_high}</code>\n"
                f"• ⚖️ 50% Equilibrium: <code>${eq}</code>\n"
                f"• 🔵 Demand Support: <code>${d_low} – ${d_high}</code>\n"
                f"• 📊 PDH / PDL: <code>${smc['pdh']}</code> / <code>${smc['pdl']}</code>\n\n"
                f"⚡ <b>IF / THEN EXECUTION PLAN</b>\n"
                f"• 🟢 <b>Bullish:</b> Reclaim above <code>${s_high}</code> → TP1 <code>${smc['bull_tp1']}</code>, TP2 <code>${smc['bull_tp2']}</code> (Invalidation <code>${d_low}</code>)\n"
                f"• 🔴 <b>Bearish:</b> Rejection at <code>${s_low}</code> or break below <code>${d_low}</code> → TP1 <code>${smc['bear_tp1']}</code>, TP2 <code>${smc['bear_tp2']}</code> (Invalidation <code>${s_high}</code>)\n"
                f"• 🟡 <b>Primary Watch Zone:</b> <code>${w_low} – ${w_high}</code> (SL <code>${inv}</code>)\n\n"
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
