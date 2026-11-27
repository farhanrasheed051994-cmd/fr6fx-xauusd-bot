import os
import json
import random
from datetime import datetime, timezone


def load_optional_json(path, default):
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def build_seo_package(smc, session_name, ai_data):
    """Generates algorithm-friendly, high-CTR SEO titles, descriptions, tags, and captions."""
    today_dt = datetime.now(timezone.utc)
    date_short = today_dt.strftime("%d %b %Y")
    month_year = today_dt.strftime("%B %Y")
    day_name = today_dt.strftime("%A")

    tg_link = (
        os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official")
        .replace("https://", "")
        .replace("http://", "")
        .strip()
    )

    research = load_optional_json("data/research_context.json", {})
    macro_headline = str(research.get("top_catalyst", "")).strip()
    trending_kw = str(research.get("trending_keyword", "")).strip()

    sup_int = int(round(float(smc["supply_high"])))
    dem_int = int(round(float(smc["demand_low"])))
    wz_low = int(round(float(smc["watch_low"])))
    wz_high = int(round(float(smc["watch_high"])))

    bias_word = (
        "Bullish" if "BULLISH" in smc["bias_label"]
        else ("Bearish" if "BEARISH" in smc["bias_label"] else "Key")
    )
    session_clean = session_name.title()
    hook_title = str(ai_data.get("hook_title", f"Gold {session_clean} Setup")).title()

    # 1. YOUTUBE SHORTS SEO
    yt_title_options = [
        f"XAUUSD Analysis Today ({date_short}) | {hook_title} #Shorts",
        f"Gold Price Prediction Today ({date_short}) | XAUUSD {session_clean} Levels #Shorts",
        f"XAUUSD {session_clean} Setup: {bias_word} Gold Levels ({dem_int}-{sup_int}) #Shorts",
    ]
    if trending_kw and len(trending_kw) <= 32:
        yt_title_options.insert(0, f"{trending_kw} ({date_short}) | {hook_title} #Shorts")

    yt_title = random.choice(yt_title_options)[:92]
    catalyst_block = f"📰 Macro Catalyst: {macro_headline}\n\n" if macro_headline else ""

    yt_description = (
        f"XAUUSD {session_clean} technical analysis and Gold price levels for {day_name}, {date_short}. "
        f"Live MT5 Smart Money Concepts (SMC) breakdown covering Institutional Supply ({smc['supply_zone']}), "
        f"50% Equilibrium (${smc['equilibrium']}), Demand ({smc['demand_zone']}), Fair Value Gaps, and DXY correlation.\n\n"
        f"{catalyst_block}"
        f"📲 Free FR6 FX Telegram (Full Chart Markups & Execution Plans): https://{tg_link}\n\n"
        f"📊 XAUUSD KEY LEVELS ({date_short}):\n"
        f"• Live Gold Price: ${smc['live_price']} ({smc['bias_label']})\n"
        f"• Institutional Supply OB: {smc['supply_zone']}\n"
        f"• Primary Watch Zone: ${smc['watch_low']} – ${smc['watch_high']}\n"
        f"• 50% Equilibrium Pivot: ${smc['equilibrium']}\n"
        f"• Institutional Demand OB: {smc['demand_zone']}\n"
        f"• Previous Day High / Low: ${smc['pdh']} / ${smc['pdl']}\n"
        f"• DXY Correlation: {smc['dxy_bias']}\n\n"
        f"🔍 Topics: XAUUSD analysis today, Gold price prediction {month_year}, XAUUSD {session_clean.lower()}, "
        f"Smart Money Concepts gold trading, XAUUSD order blocks, XAUUSD supply and demand, FR6 FX.\n\n"
        f"#XAUUSD #GoldTrading #XAUUSDAnalysis #SmartMoneyConcepts #PriceAction #GoldPricePrediction #FR6FX #Shorts\n\n"
        f"⚠️ Disclaimer: Educational technical analysis by @FR6FX. Not financial advice."
    )
    yt_tags = [
        "XAUUSD",
        "XAUUSD analysis today",
        "Gold trading",
        "Gold price prediction",
        f"XAUUSD {session_clean.lower()}",
        "Smart Money Concepts",
        "SMC trading strategy",
        "XAUUSD supply and demand",
        "XAUUSD order block",
        "Gold forex analysis",
        "MT5 gold analysis",
        "DXY gold correlation",
        f"Gold analysis {month_year}",
        "FR6 FX",
        "Shorts",
    ]
    if trending_kw:
        yt_tags.insert(1, trending_kw)

    yt_pinned_comment = (
        f"📲 Get the full high-res XAUUSD chart markup + Bullish/Bearish If-Then plan in our FREE Telegram: "
        f"https://{tg_link} 👇\n\n"
        f"Are you watching Buy confirmation at Demand ({dem_int}) 🟢 or Sell rejection at Supply ({sup_int}) 🔴 this session?"
    )

    # 2. INSTAGRAM REELS SEO
    ig_hashtag_pool = [
        "#XAUUSD", "#GoldTrading", "#SmartMoneyConcepts", "#PriceAction",
        "#XAUUSDAnalysis", "#OrderBlocks", "#LiquiditySweep", "#ForexEducation",
        "#TechnicalAnalysis", "#DayTradingGold", "#SMCTrader", "#FR6FX",
    ]
    session_tag = (
        "#LondonSession" if "LONDON" in session_name
        else ("#NewYorkSession" if "NEW YORK" in session_name else "#AsianSession")
    )
    ig_tags = " ".join(["#XAUUSD", "#GoldTrading", session_tag] + random.sample(ig_hashtag_pool, 6))
    ig_catalyst = f"📰 Catalyst: {macro_headline}\n" if macro_headline else ""

    ig_caption = (
        f"{ai_data.get('hook_title', 'GOLD LIQUIDITY SETUP')} — Watch ${wz_low}–${wz_high} 👀📊\n\n"
        f"Gold is sitting at ${smc['live_price']} ({smc['bias_label']}) heading into {session_clean}. "
        f"{ig_catalyst}"
        f"Wait for clean M5 confirmation inside the Watch Zone—never chase candles.\n\n"
        f"🎯 Institutional Map ({date_short}):\n"
        f"🔴 Supply OB: {smc['supply_zone']}\n"
        f"🟡 Watch Zone: ${smc['watch_low']} – ${smc['watch_high']}\n"
        f"⚖️ 50% Equilibrium: ${smc['equilibrium']}\n"
        f"🔵 Demand OB: {smc['demand_zone']}\n"
        f"🛑 Invalidation: ${smc['invalidation']}\n\n"
        f"📲 Full chart breakdown in our FREE Telegram (link in bio): https://{tg_link}\n"
        f"💬 Comment BUY 🟢 or SELL 🔴 below & save this level before the move!\n\n"
        f"⚠️ Educational purposes only. Not financial advice.\n\n"
        f"{ig_tags}"
    )

    # 3. FACEBOOK REELS SEO
    fb_caption = (
        f"{ai_data.get('hook_title', 'GOLD LIQUIDITY SETUP')} | Gold at ${smc['live_price']} ({date_short}) 📈\n\n"
        f"Here is our institutional XAUUSD {session_clean} map:\n"
        f"🔴 Supply Resistance: {smc['supply_zone']}\n"
        f"🟡 Primary Watch Zone: ${smc['watch_low']} – ${smc['watch_high']}\n"
        f"⚖️ 50% Equilibrium: ${smc['equilibrium']}\n"
        f"🔵 Demand Support: {smc['demand_zone']}\n"
        f"💧 Liquidity Read: {smc['pa_signal']}\n\n"
        f"📲 Free Telegram Chart Markups & Execution Plans: https://{tg_link}\n\n"
        f"👇 Team Bullish 🟢 or Team Bearish 🔴 on Gold today? Drop your bias in the comments!\n"
        f"⚠️ Educational technical analysis only. Not financial advice.\n\n"
        f"#XAUUSD #GoldTrading #XAUUSDAnalysis #SmartMoneyConcepts #PriceAction {session_tag} #FR6FX"
    )

    # 4. TELEGRAM CHANNEL SEO FOOTER
    tg_report_seo = ai_data.get("telegram_report", "").strip()

    return {
        "yt_title": yt_title,
        "yt_description": yt_description,
        "yt_tags": yt_tags[:18],
        "yt_pinned_comment": yt_pinned_comment,
        "ig_caption": ig_caption,
        "fb_caption": fb_caption,
        "tg_report_seo": tg_report_seo[:4090],
    }
