import os
import re
import json
import time
import random
import subprocess
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

GOOGLE_TOKEN_URL = "https://googleapis.com"
FB_GRAPH_BASE = "https://facebook.com"
FB_RUPLOAD_BASE = "https://facebook.com"
TG_API_BASE = "https://telegram.org"

def clean_secret(name):
    """Strips accidental newlines, spaces, or quotes from GitHub Secrets."""
    val = os.environ.get(name, "")
    return re.sub(r"[\r\n\t\"']", "", val).strip()

def post_to_telegram_channel(chart_png_path, mentor_report):
    """Posts the annotated TradingView chart image first, then the full SEO mentor analysis as a separate message."""
    bot_token = clean_secret("TELEGRAM_BOT_TOKEN")
    chat_id = clean_secret("TELEGRAM_CHAT_ID")
    if not bot_token or not chat_id:
        print("⚠️ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is empty—skipping Telegram post.")
        return

    # 1. Send Annotated Chart Image
    photo_url = f"{TG_API_BASE}{bot_token}/sendPhoto"
    with open(chart_png_path, "rb") as img_file:
        photo_resp = requests.post(
            photo_url,
            data={"chat_id": chat_id},
            files={"photo": img_file},
            timeout=20
        ).json()

    if photo_resp.get("ok"):
        print(f"✅ Telegram Chart Image Posted to {chat_id}")
    else:
        print("❌ Telegram Chart Image Error:", photo_resp)

    time.sleep(1.5)

    # 2. Send Full Mentor Description as Separate Message (up to 4096 chars)
    msg_url = f"{TG_API_BASE}{bot_token}/sendMessage"
    msg_resp = requests.post(
        msg_url,
        data={
            "chat_id": chat_id,
            "text": mentor_report[:4090],
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        },
        timeout=20
    ).json()

    if msg_resp.get("ok"):
        print(f"✅ Telegram Mentor Analysis Posted to {chat_id}")
    else:
        plain_text = re.sub(r"<[^>]+>", "", mentor_report)[:4090]
        retry = requests.post(
            msg_url,
            data={
                "chat_id": chat_id,
                "text": plain_text,
                "disable_web_page_preview": True
            },
            timeout=20
        ).json()
        print("✅ Telegram Text Fallback Result:", retry)

def upload_youtube_short(video_path, title, description, tags=None, pinned_comment=None):
    refresh_token = clean_secret("YT_REFRESH_TOKEN")
    client_id = clean_secret("YT_CLIENT_ID")
    client_secret = clean_secret("YT_CLIENT_SECRET")

    if not refresh_token or not client_id or not client_secret:
        print("⚠️ YouTube secrets are empty—skipping YouTube upload.")
        return

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret
    )
    youtube = build("youtube", "v3", credentials=creds, static_discovery=False)

    default_tags = [
        "XAUUSD", "Gold Trading", "Forex Analysis",
        "Smart Money Concepts", "TradingView", "FR6FX", "Shorts"
    ]

    body = {
        "snippet": {
            "title": title[:95],
            "description": description,
            "tags": (tags or default_tags)[:20],
            "categoryId": "27"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    res = youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()
    vid_id = res["id"]
    print(f"✅ YouTube Short Live: https://youtube.com{vid_id}")

    if pinned_comment:
        try:
            youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": vid_id,
                        "topLevelComment": {
                            "snippet": {"textOriginal": pinned_comment}
                        }
                    }
                }
            ).execute()
            print("✅ YouTube SEO Pinned/Top Comment Posted")
        except Exception as ce:
            print("⚠️ YouTube Comment Skipped (requires youtube.force-ssl scope):", ce)

def create_temp_public_url(video_path, release_tag):
    subprocess.run(["gh", "release", "delete", release_tag, "-y"], stderr=subprocess.DEVNULL)
    subprocess.run(
        ["gh", "release", "create", release_tag, video_path, "--title", "FR6FX Media", "--notes", "Auto"],
        check=True
    )
    time.sleep(5)
    repo = clean_secret("GITHUB_REPOSITORY")
    fname = os.path.basename(video_path)
    return f"https://github.com/{repo}/releases/download/{release_tag}/{fname}"
def safe_json(resp, label):
    try:
        return resp.json()
    except Exception:
        print(f"❌ {label} Non-JSON Response (HTTP {resp.status_code}): {resp.text[:300]}")
        return {}

def upload_instagram_reel(video_url, caption):
    ig_id = clean_secret("IG_USER_ID")
    token = clean_secret("META_ACCESS_TOKEN")
    if not ig_id or not token:
        print("⚠️ IG_USER_ID or META_ACCESS_TOKEN is empty—skipping Instagram upload.")
        return

    resp = requests.post(
        f"{FB_GRAPH_BASE}/{ig_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": token
        },
        timeout=30
    )
    r = safe_json(resp, "Instagram Container")

    creation_id = r.get("id")
    if not creation_id:
        print("❌ Instagram Container Error:", r)
        return

    for _ in range(18):
        time.sleep(10)
        st_resp = requests.get(
            f"{FB_GRAPH_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=20
        )
        st = safe_json(st_resp, "Instagram Status").get("status_code")
        if st == "FINISHED":
            break
        if st == "ERROR":
            print("❌ Instagram Processing Failed")
            return

    pub_resp = requests.post(
        f"{FB_GRAPH_BASE}/{ig_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=30
    )
    pub = safe_json(pub_resp, "Instagram Publish")
    print("✅ Instagram Reel Live:", pub)

def upload_facebook_reel(video_url, caption):
    page_id = clean_secret("FB_PAGE_ID")
    page_token = clean_secret("FB_PAGE_TOKEN")
    if not page_id or not page_token:
        print("⚠️ FB_PAGE_ID or FB_PAGE_TOKEN is empty—skipping Facebook upload.")
        return

    start_resp = requests.post(
        f"{FB_GRAPH_BASE}/{page_id}/video_reels",
        data={"upload_phase": "start", "access_token": page_token},
        timeout=30
    )
    start_res = safe_json(start_resp, "Facebook Start")

    video_id = start_res.get("video_id")
    if not video_id:
        print("❌ Facebook Start Error:", start_res)
        return

    requests.post(
        f"{FB_RUPLOAD_BASE}/{video_id}",
        headers={"Authorization": f"OAuth {page_token}", "file_url": video_url},
        timeout=30
    )

    fin_resp = requests.post(
        f"{FB_GRAPH_BASE}/{page_id}/video_reels",
        data={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": caption,
            "access_token": page_token
        },
        timeout=30
    )
    fin_res = safe_json(fin_resp, "Facebook Finish")
    print("✅ Facebook Reel Live:", fin_res)

def broadcast_reel(video_path, yt_title, yt_desc, yt_tags, yt_comment, ig_caption, fb_caption, tag_name):
    try:
        upload_youtube_short(video_path, yt_title, yt_desc, yt_tags, yt_comment)
    except Exception as e:
        print("❌ YouTube Upload Error:", e)

    public_mp4_url = create_temp_public_url(video_path, tag_name)
    try:
        upload_instagram_reel(public_mp4_url, ig_caption)
        upload_facebook_reel(public_mp4_url, fb_caption)
    finally:
        subprocess.run(["gh", "release", "delete", tag_name, "-y"], stderr=subprocess.DEVNULL)

def main():
    time.sleep(random.randint(25, 75))

    with open("assets/analysis_output.json") as f:
        data = json.load(f)

    seo = data.get("seo", {})

    # 1. Post Annotated TradingView Chart Image + Full SEO Mentor Breakdown as Separate Posts to Telegram
    tg_report = seo.get("tg_report_seo") or data.get("telegram_report")
    if os.path.exists("assets/telegram_chart.png") and tg_report:
        try:
            post_to_telegram_channel("assets/telegram_chart.png", tg_report)
        except Exception as e:
            print("❌ Telegram Post Error:", e)

    # 2. If a Bonus "CALLED IT ✅" Proof Reel was created, broadcast it
    if os.path.exists("assets/recap_reel.mp4"):
        recap_title = f"XAUUSD Target Smashed! How Our Gold Levels Played Out ({data['date_label']}) ✅ #Shorts"
        recap_caption = (
            f"Another clean XAUUSD Smart Money level played out to the dollar ✅\n\n"
            f"Follow @FR6FX and join our free Telegram channel in bio/description for live chart markups!\n\n"
            f"⚠️ Educational purposes only. Not financial advice.\n\n"
            f"#XAUUSD #GoldTrading #SmartMoneyConcepts #ForexResults #FR6FX"
        )
        broadcast_reel(
            "assets/recap_reel.mp4",
            recap_title,
            recap_caption,
            seo.get("yt_tags"),
            seo.get("yt_pinned_comment"),
            recap_caption,
            recap_caption,
            "fr6fx-temp-recap"
        )
        time.sleep(20)

    # 3. Broadcast the Main Session Analysis Reel with Platform-Specific SEO
    broadcast_reel(
        "assets/final_reel.mp4",
        seo.get("yt_title", data["youtube_title"]),
        seo.get("yt_description", data["social_caption"]),
        seo.get("yt_tags"),
        seo.get("yt_pinned_comment"),
        seo.get("ig_caption", data["social_caption"]),
        seo.get("fb_caption", data["social_caption"]),
        "fr6fx-temp-main"
    )

if __name__ == "__main__":
    main()
