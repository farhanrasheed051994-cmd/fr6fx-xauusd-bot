import os
import json
import time
import random
import subprocess
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_youtube_short(video_path, title, description):
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://googleapis.com",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"]
    )
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:95],
            "description": f"{description}\n\nFollow @FR6FX for daily London & New York Open XAUUSD live breakdowns.\nDisclaimer: For educational purposes only. Not financial advice.\n\n#XAUUSD #GoldTrading #Forex #SmartMoneyConcepts #TradingView #Shorts",
            "tags": ["XAUUSD", "Gold Trading", "Forex Analysis", "Smart Money Concepts", "TradingView", "FR6FX", "Shorts"],
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

    # Auto-post first engagement comment
    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": vid_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": "📊 Where is Gold heading next? Reply BUY 🟢 or SELL 🔴 below! (Educational only • Not financial advice)"
                        }
                    }
                }
            }
        ).execute()
    except Exception as e:
        print("⚠️ YouTube comment skipped:", e)

def create_temp_public_url(video_path, release_tag):
    """Temporarily hosts the .mp4 via GitHub Releases so Meta Graph APIs can download it."""
    subprocess.run(["gh", "release", "delete", release_tag, "-y"], stderr=subprocess.DEVNULL)
    subprocess.run(["gh", "release", "create", release_tag, video_path, "--title", "FR6FX Media", "--notes", "Auto"], check=True)
    repo = os.environ["GITHUB_REPOSITORY"]
    fname = os.path.basename(video_path)
    return f"https://github.com{repo}/releases/download/{release_tag}/{fname}"

def upload_instagram_reel(video_url, caption):
    ig_id = os.environ["IG_USER_ID"]
    token = os.environ["META_ACCESS_TOKEN"]

    # 1. Initialize Reels Container
    r = requests.post(
        f"https://facebook.com{ig_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",
            "access_token": token
        }
    ).json()

    creation_id = r.get("id")
    if not creation_id:
        print("❌ Instagram Container Error:", r)
        return

    # 2. Wait for Meta servers to process video
    for _ in range(18):
        time.sleep(10)
        st = requests.get(
            f"https://facebook.com{creation_id}",
            params={"fields": "status_code", "access_token": token}
        ).json().get("status_code")
        if st == "FINISHED":
            break
        if st == "ERROR":
            print("❌ Instagram Processing Failed")
            return

    # 3. Publish Reel
    pub = requests.post(
        f"https://facebook.com{ig_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token}
    ).json()
    print("✅ Instagram Reel Live:", pub)

def upload_facebook_reel(video_url, caption):
    page_id = os.environ["FB_PAGE_ID"]
    page_token = os.environ["FB_PAGE_TOKEN"]

    # 1. Start Upload
    start_res = requests.post(
        f"https://facebook.com{page_id}/video_reels",
        data={"upload_phase": "start", "access_token": page_token}
    ).json()

    video_id = start_res.get("video_id")
    if not video_id:
        print("❌ Facebook Start Error:", start_res)
        return

    # 2. Transfer Hosted Video URL
    requests.post(
        f"https://facebook.com{video_id}",
        headers={"Authorization": f"OAuth {page_token}", "file_url": video_url}
    )

    # 3. Finish & Publish
    fb_text = f"{caption}\n\n👇 Team Bullish 🟢 or Team Bearish 🔴 for this session? Vote in comments!"
    fin_res = requests.post(
        f"https://facebook.com{page_id}/video_reels",
        data={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "description": fb_text,
            "access_token": page_token
        }
    ).json()
    print("✅ Facebook Reel Live:", fin_res)

def broadcast_reel(video_path, yt_title, social_caption, tag_name):
    upload_youtube_short(video_path, yt_title, social_caption)
    public_mp4_url = create_temp_public_url(video_path, tag_name)
    try:
        upload_instagram_reel(public_mp4_url, social_caption)
        upload_facebook_reel(public_mp4_url, social_caption)
    finally:
        subprocess.run(["gh", "release", "delete", tag_name, "-y"], stderr=subprocess.DEVNULL)

def main():
    # Natural human jitter delay (30s to 150s)
    time.sleep(random.randint(30, 150))

    with open("assets/analysis_output.json") as f:
        data = json.load(f)

    # 1. If a Bonus "CALLED IT ✅" Proof Reel was created, post it first
    if os.path.exists("assets/recap_reel.mp4"):
        broadcast_reel(
            "assets/recap_reel.mp4",
            f"XAUUSD Target Smashed! How Our Gold Levels Played Out ({data['date_label']}) ✅ #Shorts",
            f"Another clean XAUUSD Smart Money level played out to the dollar ✅\n\nFollow @FR6FX and save our daily Pre-London & Pre-New York Gold gameplans!\n\n⚠️ Educational purposes only. Not financial advice.\n#XAUUSD #GoldTrading #SmartMoneyConcepts #ForexAnalysis #FR6FX",
            "fr6fx-temp-recap"
        )
        time.sleep(25)

    # 2. Post the Main Upcoming Session Analysis Reel
    broadcast_reel(
        "assets/final_reel.mp4",
        data["youtube_title"],
        data["social_caption"],
        "fr6fx-temp-main"
    )

if __name__ == "__main__":
    main()
