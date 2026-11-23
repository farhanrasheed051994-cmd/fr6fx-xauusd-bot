import os
import re
import random
from datetime import datetime, timezone

def extract_news_keywords(news_list):
    """Extracts high-volume macro catalysts (CPI, NFP, FOMC, Powell, etc.) from today's USD news."""
    catalysts = []
    keywords_map = {
        "cpi": "CPI Inflation",
        "non-farm": "NFP Non-Farm Payrolls",
        "nfp": "NFP",
        "fomc": "FOMC Fed Rate Decision",
        "fed": "Federal Reserve",
        "powell": "Jerome Powell Speech",
        "ppi": "PPI Inflation",
        "gdp": "US GDP",
        "unemployment": "Jobless Claims",
        "retail sales": "US Retail Sales",
        "pmi": "US PMI"
    }
    joined = " ".join(news_list).lower()
    for key, label in keywords_map.items():
        if key in joined and label not in catalysts:
            catalysts.append(label)
    return catalysts[:3]

def build_seo_package(smc, news_list, session_name, ai_data):
    """Generates platform-specific SEO titles, descriptions, tags, hashtags, and pinned comments."""
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

    price_int = int(round(float(smc["live_price"])))
    bias_word = "Bullish" if "BULLISH" in smc["bias_label"] else ("Bearish" if "BEARISH" in smc["bias_label"] else "Range")
    session_clean = session_name.title()
    catalysts = extract_news_keywords(news_list)
    catalyst_str = f" | {catalysts[0]} Impact" if catalysts else ""
    catalyst_line = f"📰 Today's USD Catalyst: {', '.join(catalysts)}\n" if catalysts else ""

    # 1. YOUTUBE SHORTS SEO (Title < 95 chars, Search-Indexed Description, 15 Tags, Pinned Comment)
    yt_title_options = [
        f"XAUUSD {session_clean} Analysis Today ({date_short}) | Gold ${price_int} SMC Setup #Shorts",
        f"Gold Price Prediction Today ({date_short}) | XAUUSD {session_clean}{catalyst_str} #Shorts",
        f"XAUUSD Live Analysis: {bias_word} Gold Levels (${smc['strong_low']}-${smc['strong_high']}) #Shorts"
    ]
    yt_title = random.choice(yt_title_options)[:95]

    yt_description = (
        f"XAUUSD {session_clean} technical analysis and Gold price prediction for {day_name}, {date_short}. "
        f"Live OANDA XAUUSD Smart Money Concepts (SMC) breakdown covering Institutional Supply (${smc['strong_high']}), "
        f"50% Equilibrium (${smc['equilibrium']}), Demand (${smc['strong_low']}), Fair Value Gaps, and DXY correlation.\n\n"
        f"📲 Join Free FR6 FX Telegram (Full Chart Markups & Live USD News): https://{tg_link}\n\n"
        f"📊 XAUUSD KEY LEVELS ({date_short}):\n"
        f"• Live Gold Spot: ${smc['live_price']} ({smc['bias_label']})\n"
        f"• Institutional Supply Zone: {smc['supply_zone']}\n"
        f"• 50% Equilibrium Pivot: ${smc['equilibrium']}\n"
        f"• Institutional Demand Zone: {smc['demand_zone']}\n"
        f"• Previous Day High / Low: ${smc['pdh']} / ${smc['pdl']}\n"
        f"• Asian Range: ${smc['asia_low']} – ${smc['asia_high']}\n"
        f"• DXY Correlation: {smc['dxy_bias']}\n"
        f"{catalyst_line}\n"
        f"⏱️ CHAPTERS:\n"
        f"0:00 XAUUSD {session_clean} Liquidity Read\n"
        f"0:12 Institutional Supply & 50% Equilibrium\n"
        f"0:25 Demand Zone & DXY Macro Correlation\n"
        f"0:35 Free Telegram Chart Markups\n\n"
        f"🔍 Search Topics: XAUUSD analysis today, Gold price prediction {month_year}, XAUUSD {session_clean.lower()}, "
        f"Smart Money Concepts gold trading, XAUUSD supply and demand, OANDA XAUUSD live chart, FR6 FX.\n\n"
        f"#XAUUSD #GoldTrading #XAUUSDAnalysis #SmartMoneyConcepts #ForexTrading #GoldPricePrediction #TradingView #FR6FX #Shorts\n\n"
        f"⚠️ Disclaimer: All analysis by @FR6FX is strictly for educational purposes and does not constitute financial advice."
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
        "Gold forex analysis",
        "OANDA XAUUSD",
        "TradingView live chart",
        "DXY gold correlation",
        f"Gold analysis {month_year}",
        "FR6 FX",
        "Shorts"
    ] + catalysts

    yt_pinned_comment = (
        f"📲 Get the full annotated 15M & 5M XAUUSD chart markup + real-time USD news alerts in our FREE Telegram channel: "
        f"https://{tg_link} 👇\n\n"
        f"Are you looking for Buy entries at Demand (${smc['strong_low']}) 🟢 or Sell rejections at Supply (${smc['strong_high']}) 🔴 this session?"
    )
    # 2. INSTAGRAM REELS SEO (Keyword-rich hook line + 10 rotated niche hashtags)
    ig_hashtag_pool = [
        "#XAUUSD", "#GoldTrading", "#SmartMoneyConcepts", "#ForexAnalysis",
        "#GoldSignals", "#XAUUSDAnalysis", "#PriceActionTrading", "#ForexTrader",
        "#OrderBlocks", "#LiquiditySweep", "#TradingView", "#FR6FX"
    ]
    session_tag = "#LondonSession" if "LONDON" in session_name else ("#NewYorkSession" if "NEW YORK" in session_name else "#ForexMarket")
    ig_tags = " ".join(["#XAUUSD", "#GoldTrading", session_tag] + random.sample(ig_hashtag_pool, 7))

    ig_caption = (
        f"XAUUSD {session_clean} Analysis ({date_short}) — Gold ${smc['live_price']} Smart Money Setup 📊\n\n"
        f"{ai_data.get('spoken_script', '')[:220].strip()}...\n\n"
        f"🎯 Key Institutional Gold Levels:\n"
        f"🔴 Supply Zone: {smc['supply_zone']}\n"
        f"⚖️ 50% Equilibrium: ${smc['equilibrium']}\n"
        f"🔵 Demand Zone: {smc['demand_zone']}\n"
        f"💵 DXY Impact: {smc['dxy_bias']}\n"
        f"{catalyst_line}\n"
        f"📲 Join our FREE Telegram channel (link in bio) for full chart markups & live USD news: https://{tg_link}\n"
        f"💾 Save this setup before the session move & follow @FR6FX!\n\n"
        f"⚠️ Educational purposes only. Not financial advice.\n\n"
        f"{ig_tags}"
    )

    # 3. FACEBOOK REELS SEO (Search-indexed summary + interactive poll CTA + clean tags)
    fb_caption = (
        f"XAUUSD {session_clean} Gold Price Analysis ({date_short}) | Spot Gold at ${smc['live_price']} ({smc['bias_label']}) 📈\n\n"
        f"🔴 Supply Resistance: {smc['supply_zone']}\n"
        f"⚖️ 50% Equilibrium Pivot: ${smc['equilibrium']}\n"
        f"🔵 Demand Support: {smc['demand_zone']}\n"
        f"💧 Liquidity Read: {smc['pa_signal']}\n"
        f"{catalyst_line}\n"
        f"📲 Free Telegram Chart Markups & Live USD News Alerts: https://{tg_link}\n\n"
        f"👇 Team Bullish 🟢 or Team Bearish 🔴 for Gold this session? Drop your bias in the comments!\n"
        f"⚠️ Educational analysis only. Not financial advice.\n\n"
        f"#XAUUSD #GoldTrading #XAUUSDAnalysis #SmartMoneyConcepts #ForexTrading {session_tag} #FR6FX"
    )

    # 4. TELEGRAM CHANNEL SEO (Searchable cashtags/hashtags header + footer on the separate mentor text post)
    catalyst_tags = " ".join([f"#{re.sub(r'[^A-Za-z0-9]', '', c)}" for c in catalysts])
    tg_seo_footer = (
        f"\n\n🔍 #XAUUSD #GOLD #SMC {session_tag} #DXY #ForexAnalysis {catalyst_tags} #FR6FX"
    ).replace("  ", " ")

    base_tg_report = ai_data.get("telegram_report", "").strip()
    if "#XAUUSD" not in base_tg_report:
        tg_report_seo = f"{base_tg_report}{tg_seo_footer}"
    else:
        tg_report_seo = base_tg_report

    return {
        "yt_title": yt_title,
        "yt_description": yt_description,
        "yt_tags": yt_tags[:20],
        "yt_pinned_comment": yt_pinned_comment,
        "ig_caption": ig_caption,
        "fb_caption": fb_caption,
        "tg_report_seo": tg_report_seo[:4090]
    }
