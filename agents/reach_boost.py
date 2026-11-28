import os
import json
import requests
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()


def fetch_google_trending_gold_queries():
    queries = []
    seeds = ["xauusd analysis", "gold price prediction", "xauusd strategy"]
    for seed in seeds:
        try:
            url = f"http://google.com{requests.utils.quote(seed)}"
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                suggestions = resp.json()
                queries.extend(suggestions[:3])
        except Exception:
            pass
    return list(dict.fromkeys(queries))[:8]


def run_reach_boost(topic_title, session_name, bias_label, catalyst, live_price=""):
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    live_queries = fetch_google_trending_gold_queries()
    trending_str = ", ".join(live_queries) if live_queries else "xauusd analysis today, gold price forecast, smc trading"

    tg_link = (
        os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official")
        .replace("https://", "")
        .replace("http://", "")
        .strip()
    )
    full_tg_url = f"https://{tg_link}"

    prompt = f"""
You are ReachBoost, an elite short-form video SEO specialist for YouTube Shorts, Instagram Reels, and Facebook Reels in the XAUUSD / Smart Money Concepts niche.

VIDEO CONTEXT:
- Topic / Session: {topic_title} ({session_name})
- Bias: {bias_label} | Live Price: {live_price}
- Macro Catalyst: {catalyst}
- Official Telegram Link: {full_tg_url}
- Live Google Trending Queries Right Now: {trending_str}

Generate high-CTR, search-optimized metadata designed to maximize Shorts/Reels discovery.
CRITICAL RULE: Whenever including a Telegram link in descriptions, captions, or pinned comments, use ONLY the exact URL {full_tg_url} (never use placeholders like t.me/yourchannel).

Return ONLY valid JSON:
{{
  "yt_title": "Curiosity-driven YouTube Shorts title under 62 chars with #XAUUSD #Gold",
  "yt_description": "3-paragraph SEO description naturally weaving in live search terms + {full_tg_url} CTA + disclaimer",
  "yt_tags": ["xauusd", "gold trading", "smc trading", "xauusd analysis today", "12 more targeted tags"],
  "yt_pinned_comment": "Engaging question + CTA linking to {full_tg_url}",
  "ig_fb_caption": "Punchy 3-line Instagram/Facebook Reels caption with {full_tg_url} + 12 high-reach hashtags",
  "top_keyword_used": "{live_queries if live_queries else 'xauusd analysis today'}"
}}
"""

    seo = None
    if client:
        for model_name in ("gemini-3.8-flash", "gemini-3.1-pro-preview", "gemini-3.5-flash-lite"):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.5),
                )
                if resp and resp.text:
                    seo = json.loads(resp.text)
                    print(f"🚀 ReachBoost SEO package generated via {model_name}")
                    break
            except Exception as e:
                print(f"⚠️ ReachBoost {model_name} warning: {e}")

    if not seo:
        seo = {
            "yt_title": f"XAUUSD {session_name} Trap! Gold {bias_label} Levels #XAUUSD #Gold",
            "yt_description": (
                f"Live XAUUSD {session_name} Smart Money Concepts breakdown. {catalyst}\n\n"
                f"Trending searches: {trending_str}\n\n"
                f"Join our free FR6FX Telegram community for daily levels & chart markups: {full_tg_url}\n\n"
                f"Disclaimer: Educational analysis only, not financial advice."
            ),
            "yt_tags": ["xauusd", "gold trading", "xauusd analysis today", "smc trading", "forex gold", "ict concepts"],
            "yt_pinned_comment": f"Where is Gold heading next in {session_name}? Drop your bias below & grab full markups in our free Telegram: {full_tg_url} 👇",
            "ig_fb_caption": (
                f"Gold {session_name} Liquidity Breakdown ({bias_label}) ⚡\n"
                f"{catalyst}\n\n"
                f"📲 Free Telegram Chart Markups: {full_tg_url}\n\n"
                f"#xauusd #goldtrading #smartmoneyconcepts #forexsignals #priceaction #tradingview #fr6fx"
            ),
            "top_keyword_used": live_queries if live_queries else "xauusd analysis today",
        }

    os.makedirs("data", exist_ok=True)
    with open("data/seo_package.json", "w", encoding="utf-8") as f:
        json.dump(seo, f, indent=2)

    return seo
