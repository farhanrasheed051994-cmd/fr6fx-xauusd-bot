import os
import json
import xml.etree.ElementTree as ET
import requests
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()


def fetch_reddit_trading_hot():
    """Fetches top weekly discussions from r/Forex and r/Gold without API keys."""
    posts = []
    headers = {"User-Agent": "FR6FX-TrendRadar/1.0"}
    for sub in ("Forex", "Gold"):
        try:
            url = f"https://reddit.com{sub}/top.json?t=week&limit=6"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                children = resp.json().get("data", {}).get("children", [])
                for c in children:
                    title = c.get("data", {}).get("title", "").strip()
                    if title:
                        posts.append(f"[r/{sub}] {title}")
        except Exception:
            pass
    return posts


def fetch_weekly_gold_news():
    rss_url = "https://google.com"
    items = []
    try:
        resp = requests.get(rss_url, timeout=10)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            for item in root.findall(".//item")[:6]:
                title = (item.findtext("title") or "").strip()
                if title:
                    items.append(title)
    except Exception:
        pass
    return items


def run_trend_radar():
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
    reddit_posts = fetch_reddit_trading_hot()
    weekly_news = fetch_weekly_gold_news()

    prompt = f"""
You are TrendRadar, a viral content strategist for XAUUSD & Smart Money Concepts creators.
Forex markets are closed on Saturday and Sunday. Analyze this week's trader discussions and Gold news to select 4 high-retention weekend Reel topics (2 for Saturday, 2 for Sunday).

REDDIT TRADER DISCUSSIONS THIS WEEK:
{chr(10).join(reddit_posts) if reddit_posts else 'SMC liquidity sweeps, Gold ATH volatility, risk management'}

WEEKLY GOLD & MACRO NEWS:
{chr(10).join(weekly_news) if weekly_news else 'Gold weekly session range and DXY reaction'}

Select 4 distinct topics:
1. Saturday Reel 1: Weekly XAUUSD Liquidity Recap (what trapped retail traders this week)
2. Saturday Reel 2: Smart Money / ICT Concept Breakdown applied to Gold
3. Sunday Reel 1: Trading Psychology / Risk Management mistake most Gold traders made this week
4. Sunday Reel 2: Monday Market Open Watchlist & Key Levels to prepare for

Return ONLY valid JSON:
{{
  "best_hook_formula": "Most viral hook structure observed this week",
  "topics": [
    {{
      "slot": "Saturday_1",
      "session_label": "Weekly Gold Recap",
      "topic": "Specific engaging topic title",
      "angle": "Why traders will watch until the end"
    }}
  ]
}}
"""

    data = None
    if client:
        for model_name in ("gemini-2.5-flash", "gemini-2.5-pro"):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.5),
                )
                if resp and resp.text:
                    data = json.loads(resp.text)
                    print(f"📡 TrendRadar found 4 weekend topics via {model_name}")
                    break
            except Exception as e:
                print(f"⚠️ TrendRadar {model_name} warning: {e}")

    if not data:
        data = {
            "best_hook_formula": "Contrarian Mistake Hook + Exact Price Level",
            "topics": [
                {"slot": "Saturday_1", "session_label": "Weekly Gold Recap", "topic": "How Smart Money Trapped Breakout Buyers on Gold This Week", "angle": "Show the exact liquidity sweep before reversal"},
                {"slot": "Saturday_2", "session_label": "SMC Masterclass", "topic": "Why Your Fair Value Gaps Fail on XAUUSD", "angle": "Explain liquidity sweep requirement before FVG entry"},
                {"slot": "Sunday_1", "session_label": "Trader Psychology", "topic": "The 15-Minute News Rule That Saves Gold Accounts", "angle": "Why trading right into NFP/CPI destroys R:R"},
                {"slot": "Sunday_2", "session_label": "Monday Open Prep", "topic": "XAUUSD Key Liquidity Pools to Watch on Monday Open", "angle": "Highlight unmitigated Friday highs/lows and DXY"},
            ],
        }

    os.makedirs("data", exist_ok=True)
    os.makedirs("state", exist_ok=True)
    with open("data/weekend_trends.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    with open("state/winning_hooks.json", "w", encoding="utf-8") as f:
        json.dump({"best_hook_formula": data.get("best_hook_formula", "")}, f, indent=2)

    return data


if __name__ == "__main__":
    run_trend_radar()
