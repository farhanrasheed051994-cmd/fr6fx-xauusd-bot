import os
import json
import requests
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()


def fetch_google_trending_gold_queries():
    """Fetches real-time Google Autocomplete search queries for XAUUSD / Gold trading."""
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

    prompt = f"""
You are ReachBoost, an elite short-form video SEO specialist for YouTube Shorts, Instagram Reels, and Facebook Reels in the XAUUSD / Smart Money Concepts niche.

VIDEO CONTEXT:
- Topic / Session: {topic_title} ({session_name})
- Bias: {bias_label} | Live Price: {live_price}
- Macro Catalyst: {catalyst}
- Live Google Trending Queries Right Now: {trending_str}

Generate high-CTR, search-optimized metadata designed to maximize Shorts/Reels discovery.
Return ONLY valid JSON:
{{
  "yt_title": "Curiosity-driven YouTube Shorts title under 62 chars with #XAUUSD #Gold",
  "yt_description": "3-paragraph SEO description naturally weaving in live search terms + disclaimer + Telegram CTA",
  "yt_tags": ["xauusd", "gold trading", "smc trading", "xauusd analysis today", "12 more targeted tags"],
  "yt_pinned_comment": "Engaging question + CTA for pinned comment",
  "ig_fb_caption": "Punchy 3-line Instagram/Facebook Reels caption + 12 high-reach hashtags",
  "top_keyword_used": "{live_queries if live_queries else 'xauusd analysis today'}"
}}
"""

    seo = None
    if client:
        for model_name in ("gemini-2.5-flash", "gemini-2.5-pro"):
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
                f"Join our free Telegram community for daily levels. Educational analysis only, not financial advice."
            ),
            "yt_tags": ["xauusd", "gold trading", "xauusd analysis today", "smc trading", "forex gold", "ict concepts"],
            "yt_pinned_comment": f"Where is Gold heading next in {session_name}? Drop your bias below! 👇",
            "ig_fb_caption": f"Gold {session_name} Liquidity Breakdown ({bias_label}) ⚡\n{catalyst}\n\n#xauusd #goldtrading #smartmoneyconcepts #forexsignals #priceaction #tradingview",
            "top_keyword_used": live_queries if live_queries else "xauusd analysis today",
        }

    os.makedirs("data", exist_ok=True)
    with open("data/seo_package.json", "w", encoding="utf-8") as f:
        json.dump(seo, f, indent=2)

    return seo
