import os
import re
import json
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def _tg_url(method):
    clean_tok = re.sub(r"[\r\n\t\"']", "", TELEGRAM_BOT_TOKEN).strip()
    clean_tok = re.sub(r"^https?://[^/]+/bot", "", clean_tok)
    clean_tok = re.sub(r"^bot(?=\d+:)", "", clean_tok)
    return f"https://telegram.org{clean_tok}/{method}"


def post_channel_update(video_path, chart_path, analysis_data, yt_url=""):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials missing; skipping ChannelPilot.")
        return False

    smc = analysis_data.get("smc", {})
    brain = analysis_data.get("gold_brain", {})
    session = analysis_data.get("session", "XAUUSD Update")
    is_weekend = analysis_data.get("is_weekend", False)

    yt_line = f"\n🎬 <b>Watch HD Breakdown:</b> <a href='{yt_url}'>YouTube Shorts</a>" if yt_url else ""
    news_line = (
        f"\n⚠️ <i>{brain['news_risk_warning']}</i>"
        if brain.get("news_risk_warning") and brain["news_risk_warning"] != "Clear macro window"
        else ""
    )

    if is_weekend:
        caption = (
            f"📚 <b>FR6FX {session.upper()}</b>\n\n"
            f"{analysis_data.get('telegram_caption', '')}\n"
            f"{yt_line}\n\n"
            f"📌 <i>Prepare your charts before Monday's Asian session open.</i>"
        )
    else:
        caption = (
            f"🟡 <b>FR6FX {session.upper()} — XAUUSD DESK</b>\n\n"
            f"💰 <b>Spot Gold:</b> <code>${smc.get('live_price')}</code> ({smc.get('pct_change')}%)\n"
            f"🧭 <b>Institutional Bias:</b> {brain.get('institutional_bias', smc.get('bias_label'))}\n"
            f"📰 <b>Macro Catalyst:</b> {brain.get('top_catalyst', 'Technical liquidity rotation')}\n\n"
            f"{analysis_data.get('telegram_caption', '')}\n"
            f"{news_line}"
            f"{yt_line}"
        )

    if os.path.exists(chart_path):
        try:
            with open(chart_path, "rb") as img:
                r = requests.post(
                    _tg_url("sendPhoto"),
                    data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1020], "parse_mode": "HTML"},
                    files={"photo": img},
                    timeout=30,
                ).json()
                if r.get("ok"):
                    print("✅ ChannelPilot posted annotated chart photo.")
                else:
                    print("⚠️ ChannelPilot photo API response:", r)
        except Exception as e:
            print(f"⚠️ ChannelPilot photo warning: {e}")

    if os.path.exists(video_path):
        try:
            with open(video_path, "rb") as vid:
                r = requests.post(
                    _tg_url("sendVideo"),
                    data={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "caption": f"🎥 <b>{analysis_data.get('hook_headline', 'XAUUSD Reel')}</b>{yt_line}",
                        "parse_mode": "HTML",
                        "supports_streaming": True,
                    },
                    files={"video": vid},
                    timeout=60,
                ).json()
                if r.get("ok"):
                    print("✅ ChannelPilot posted Reel video.")
                else:
                    print("⚠️ ChannelPilot video API response:", r)
        except Exception as e:
            print(f"⚠️ ChannelPilot video warning: {e}")

    if is_weekend:
        try:
            requests.post(
                _tg_url("sendPoll"),
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "question": f"📊 FR6FX Community Poll: What is your XAUUSD bias for Monday's Open (Gold @ ${smc.get('live_price')})?",
                    "options": json.dumps([
                        "🟢 Bullish (Sweep Lows & Rally)",
                        "🔴 Bearish (Reject Supply & Drop)",
                        "⏳ Waiting for London Killzone",
                    ]),
                    "is_anonymous": True,
                },
                timeout=15,
            )
            print("📊 ChannelPilot posted weekend community poll!")
        except Exception as e:
            print(f"⚠️ ChannelPilot poll warning: {e}")

    return True
