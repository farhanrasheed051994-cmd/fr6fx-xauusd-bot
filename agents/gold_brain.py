import os
import sys
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import requests
from google import genai
from google.genai import types

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
PRIVATE_CHAT_ID = (os.environ.get("PRIVATE_TELEGRAM_ID") or os.environ.get("TELEGRAM_CHAT_ID", "")).strip()


def fetch_usd_economic_calendar():
    """Fetches today's High/Medium impact USD economic events from free ForexFactory XML feed."""
    url = "https://faireconomy.media"
    today_str = datetime.now(timezone.utc).strftime("%m-%d-%Y")
    events = []
    try:
        resp = requests.get(url, timeout=12)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            for item in root.findall("event"):
                country = (item.findtext("country") or "").strip()
                impact = (item.findtext("impact") or "").strip()
                ev_date = (item.findtext("date") or "").strip()
                if country == "USD" and impact in ("High", "Medium") and ev_date == today_str:
                    title = (item.findtext("title") or "").strip()
                    ev_time = (item.findtext("time") or "").strip()
                    forecast = (item.findtext("forecast") or "N/A").strip()
                    previous = (item.findtext("previous") or "N/A").strip()
                    events.append(f"[{impact}] {ev_time} UTC: {title} (Forecast: {forecast}, Prev: {previous})")
    except Exception as e:
        print(f"Calendar fetch warning: {e}")
    return events[:6]


def fetch_gold_macro_headlines():
    """Fetches latest XAUUSD / DXY / Fed macro headlines via Google News RSS."""
    rss_url = "https://google.com"
    headlines = []
    try:
        resp = requests.get(rss_url, timeout=12)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item")[:5]:
                title = (item.findtext("title") or "").strip()
                if title:
                    headlines.append(title)
    except Exception as e:
        print(f"Headlines fetch warning: {e}")
    return headlines


def retrieve_trained_rules(client, query_text, top_k=4):
    """Queries Supabase pgvector gold_knowledge table for matching user strategy rules."""
    if not SUPABASE_URL or not SUPABASE_KEY or not client:
        return []
    try:
        emb_res = client.models.embed_content(
            model="text-embedding-004",
            contents=query_text,
            config=types.EmbedContentConfig(output_dimensionality=768),
        )
        query_vec = emb_res.embeddings[0].values

        rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/match_gold_knowledge"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            rpc_url,
            headers=headers,
            json={"query_embedding": query_vec, "match_threshold": 0.50, "match_count": top_k},
            timeout=15,
        )
        if resp.status_code == 200:
            rows = resp.json()
            return [f"[{r.get('title', 'Rule')}]: {r.get('content', '')}" for r in rows]
    except Exception as e:
        print(f"Supabase RAG lookup warning: {e}")
    return []
def check_duplicate_alert(bias, key_level):
    """Prevents spamming the exact same setup repeatedly."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    try:
        url = f"{SUPABASE_URL}/rest/v1/xauusd_alerts?select=bias,key_level,created_at&order=created_at.desc&limit=1"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200 and resp.json():
            last = resp.json()[0]
            if last.get("bias") == bias and last.get("key_level") == key_level:
                return True
    except Exception:
        pass
    return False


def log_alert_to_supabase(session, bias, key_level, summary):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    try:
        url = f"{SUPABASE_URL}/rest/v1/xauusd_alerts"
        headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        requests.post(
            url,
            headers=headers,
            json={"session": session, "bias": bias, "key_level": key_level, "summary": summary},
            timeout=10,
        )
    except Exception:
        pass


def send_private_copilot_alert(text):
    if not TELEGRAM_BOT_TOKEN or not PRIVATE_CHAT_ID:
        return
    clean_tok = TELEGRAM_BOT_TOKEN.replace("bot", "") if TELEGRAM_BOT_TOKEN.startswith("bot") else TELEGRAM_BOT_TOKEN
    url = f"https://telegram.org{clean_tok}/sendMessage"
    try:
        requests.post(
            url,
            data={"chat_id": PRIVATE_CHAT_ID, "text": text[:4090], "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=15,
        )
    except Exception as e:
        print(f"Private Telegram alert warning: {e}")


def run_gold_brain(smc, session_name, monitor_only=False):
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

    calendar_events = fetch_usd_economic_calendar()
    headlines = fetch_gold_macro_headlines()

    rag_query = (
        f"XAUUSD {session_name} {smc['bias_label']} {smc['pa_signal']} "
        f"H1 {smc['h1_structure']} M15 {smc['structure_tag']} DXY {smc['dxy_bias']}"
    )
    matched_rules = retrieve_trained_rules(client, rag_query, top_k=4)

    rules_block = "\n".join(matched_rules) if matched_rules else "Standard FR6FX SMC liquidity sweep + M5 CHoCH rules."
    cal_block = "\n".join(calendar_events) if calendar_events else "No high-impact USD news scheduled today."
    news_block = "\n".join(headlines) if headlines else "Normal macro session conditions."

    prompt = f"""
You are GoldBrain, an institutional XAUUSD (Gold) Technical & Fundamental Co-Pilot Analyst.
Analyze the live MT5 Smart Money Concepts data, macro calendar, news, and the trader's trained rules.
Act strictly as an analytical assistant (never auto-trade).

SESSION: {session_name} | UTC: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}
LIVE SMC DATA:
- Spot Gold: ${smc['live_price']} ({smc['pct_change']}%) | ATR(15m): {smc['atr_m15']}
- Technical Score: {smc['bias_score']}/100 ({smc['bias_label']})
- H1 Structure: {smc['h1_structure']} | M15 Structure: {smc['structure_tag']}
- Asia Range: ${smc['asia_low']} - ${smc['asia_high']} | Liquidity Read: {smc['pa_signal']}
- EQH Pool: {smc.get('eqh_pool')} | EQL Pool: {smc.get('eql_pool')} | Unmitigated FVG: {smc.get('fvg')}
- Supply OB: {smc['supply_zone']} | Demand OB: {smc['demand_zone']} | 50% EQ: ${smc['equilibrium']}
- Watch Zone: ${smc['watch_low']} - ${smc['watch_high']} | Invalidation: ${smc['invalidation']}
- R:R Setup: {smc['trade_setup']['direction']} Entry ${smc['trade_setup']['entry']} | SL ${smc['trade_setup']['sl']} | TP ${smc['trade_setup']['tp']} (1:{smc['trade_setup']['rr']})
- DXY: {smc['dxy_bias']}

TODAY'S USD ECONOMIC CALENDAR:
{cal_block}

LIVE GOLD / MACRO HEADLINES:
{news_block}

TRADER'S TRAINED STRATEGY RULES (FROM KNOWLEDGE BASE):
{rules_block}

Return ONLY valid JSON:
{{
  "institutional_bias": "BULLISH" or "BEARISH" or "NEUTRAL",
  "confidence_score": 1-100,
  "top_catalyst": "1 short sentence summarizing the main fundamental/macro driver right now",
  "news_risk_warning": "Warning if high-impact USD news is near, else 'Clear macro window'",
  "market_narrative": "3-4 sentences explaining true SMC liquidity narrative + DXY/fundamental confluence",
  "execution_plan": "Exact M5 confirmation criteria inside Watch Zone ${smc['watch_low']}-${smc['watch_high']} and invalidation",
  "alert_worthy": true or false,
  "private_alert_html": "Concise HTML alert for the trader's private Telegram if alert_worthy is true"
}}
"""

    analysis = None
    if client:
        for model_name in ("gemini-2.5-pro", "gemini-2.5-flash"):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.3),
                )
                if resp and resp.text:
                    analysis = json.loads(resp.text)
                    print(f"GoldBrain analysis complete via {model_name}")
                    break
            except Exception as e:
                print(f"GoldBrain {model_name} warning: {e}")

    if not analysis:
        first_event = calendar_events[0] if calendar_events else "Technical liquidity rotation around Asia range & DXY flow"
        first_warn = calendar_events[0] if calendar_events else "Clear macro window"
        analysis = {
            "institutional_bias": "BULLISH" if "BULLISH" in smc["bias_label"] else ("BEARISH" if "BEARISH" in smc["bias_label"] else "NEUTRAL"),
            "confidence_score": smc["bias_score"],
            "top_catalyst": first_event,
            "news_risk_warning": first_warn,
            "market_narrative": f"Gold is trading at ${smc['live_price']} with {smc['pa_signal']}. DXY sits at {smc['dxy_bias']} while H1 shows {smc['h1_structure']}.",
            "execution_plan": f"Wait for M5 CHoCH inside ${smc['watch_low']}-${smc['watch_high']} with invalidation beyond ${smc['invalidation']}.",
            "alert_worthy": bool(smc.get("volatility_alert")),
            "private_alert_html": f"<b>GoldBrain Co-Pilot ({session_name})</b>\nSpot: <b>${smc['live_price']}</b> | {smc['bias_label']}\n{smc['pa_signal']}\nWatch Zone: <code>${smc['watch_low']}-${smc['watch_high']}</code>",
        }

    os.makedirs("data", exist_ok=True)
    with open("data/session_analysis.json", "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)

    research_ctx = {
        "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "top_catalyst": analysis.get("top_catalyst", ""),
        "news_risk_warning": analysis.get("news_risk_warning", ""),
        "calendar_events": calendar_events,
    }
    with open("data/research_context.json", "w", encoding="utf-8") as f:
        json.dump(research_ctx, f, indent=2)

    key_lvl = f"{smc['watch_low']}-{smc['watch_high']}"
    if monitor_only and analysis.get("alert_worthy"):
        if not check_duplicate_alert(analysis["institutional_bias"], key_lvl):
            send_private_copilot_alert(analysis["private_alert_html"])
            log_alert_to_supabase(session_name, analysis["institutional_bias"], key_lvl, analysis["top_catalyst"])
            print("Private GoldBrain co-pilot alert sent!")

    return analysis


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from smc_engine import get_smc_market_data
    from analyze_session import detect_session

    smc_data = get_smc_market_data()
    sess = detect_session()
    run_gold_brain(smc_data, sess, monitor_only="--monitor" in sys.argv)
