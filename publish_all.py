import os
import re
import json
import time
import subprocess
from datetime import datetime, timezone
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from seo_engine import build_seo_package
from agents.channel_pilot import post_channel_update

GOOGLE_TOKEN_URL = "https://" + ".".join(["oauth2", "googleapis", "com"]) + "/token"
FB_GRAPH_BASE = "https://" + ".".join(["graph", "facebook", "com"]) + "/v21.0"
FB_RUPLOAD_BASE = "https://" + ".".join(["rupload", "facebook", "com"]) + "/video-upload/v21.0"


def get_secret(name):
    val = os.environ.get(name, "")
    val = re.sub(r"[\r\n\t\"']", "", val).strip()
    if name == "TELEGRAM_BOT_TOKEN":
        val = re.sub(r"^https?://[^/]+/bot", "", val)
        val = re.sub(r"^bot(?=\d+:)", "", val)
    return val


def safe_json(resp, label):
    try:
        return resp.json()
    except Exception:
        print(f"❌ {label} Non-JSON Response (HTTP {resp.status_code}): {resp.text[:300]}")
        return {}


def upload_youtube_short(video_path, title, description, tags=None, pinned_comment=None):
    refresh_token = get_secret("YT_REFRESH_TOKEN")
    client_id = get_secret("YT_CLIENT_ID")
    client_secret = get_secret("YT_CLIENT_SECRET")

    if not refresh_token or not client_id or not client_secret:
        print("⚠️ YouTube secrets missing—skipping YouTube upload.")
        return {"status": "SKIPPED"}

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URL,
        client_id=client_id,
        client_secret=client_secret
    )
    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title[:95],
            "description": description,
            "tags": (tags or ["XAUUSD", "Gold Trading", "Smart Money Concepts", "FR6FX", "Shorts"])[:18],
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
    vid_url = "https://" + ".".join(["www", "youtube", "com"]) + f"/watch?v={vid_id}"
    print(f"✅ YouTube Short Live: {vid_url}")

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
            print("✅ YouTube SEO Top Comment Posted")
        except Exception as ce:
            print("⚠️ YouTube Comment Skipped:", ce)

    return {"status": "OK", "video_id": vid_id, "url": vid_url}


def create_temp_public_url(video_path, release_tag):
    subprocess.run(["gh", "release", "delete", release_tag, "-y"], stderr=subprocess.DEVNULL)
    subprocess.run(
        ["gh", "release", "create", release_tag, video_path, "--title", "FR6FX Media", "--notes", "Auto"],
        check=True
    )
    time.sleep(10)
    repo = get_secret("GITHUB_REPOSITORY")
    fname = os.path.basename(video_path)
    gh_host = ".".join(["github", "com"])
    return f"https://{gh_host}/{repo}/releases/download/{release_tag}/{fname}"
def upload_instagram_reel(video_url, caption):
    ig_id = get_secret("IG_USER_ID")
    token = get_secret("META_ACCESS_TOKEN")
    if not ig_id or not token:
        print("⚠️ Instagram secrets missing—skipping Instagram upload.")
        return {"status": "SKIPPED"}

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
        return {"status": "ERROR", "detail": r}

    for _ in range(18):
        time.sleep(10)
        st_resp = requests.get(
            f"{FB_GRAPH_BASE}/{creation_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=20
        )
        st_data = safe_json(st_resp, "Instagram Status")
        st = st_data.get("status_code")
        if st == "FINISHED":
            break
        if st == "ERROR":
            print("❌ Instagram Processing Failed:", st_data)
            return {"status": "ERROR", "detail": st_data}

    pub_resp = requests.post(
        f"{FB_GRAPH_BASE}/{ig_id}/media_publish",
        data={"creation_id": creation_id, "access_token": token},
        timeout=30
    )
    pub_json = safe_json(pub_resp, "Instagram Publish")
    print("✅ Instagram Reel Live:", pub_json)
    return {"status": "OK" if pub_json.get("id") else "ERROR", "media_id": pub_json.get("id")}


def upload_facebook_reel(video_url, caption):
    page_id = get_secret("FB_PAGE_ID")
    page_token = get_secret("FB_PAGE_TOKEN")
    if not page_id or not page_token:
        print("⚠️ Facebook secrets missing—skipping Facebook upload.")
        return {"status": "SKIPPED"}

    start_resp = requests.post(
        f"{FB_GRAPH_BASE}/{page_id}/video_reels",
        data={"upload_phase": "start", "access_token": page_token},
        timeout=30
    )
    video_id = safe_json(start_resp, "Facebook Start").get("video_id")
    if not video_id:
        print("❌ Facebook Start Error")
        return {"status": "ERROR", "detail": "FB_START_ERROR"}

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
    fin_json = safe_json(fin_resp, "Facebook Finish")
    print("✅ Facebook Reel Live:", fin_json)
    return {"status": "OK" if fin_json.get("success") or video_id else "ERROR", "video_id": video_id, "detail": fin_json}


def save_run_state(data, seo, results):
    os.makedirs("state", exist_ok=True)
    smc = data.get("smc", {})
    record = {
        "published_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "session": data.get("session"),
        "hook_title": data.get("hook_headline") or data.get("hook_title"),
        "yt_title": seo.get("yt_title"),
        "live_price": smc.get("live_price"),
        "bias_label": smc.get("bias_label"),
        "trade_setup": smc.get("trade_setup"),
        "platforms": results,
    }
    with open("state/last_run.json", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    log_path = "state/analytics_log.json"
    history = []
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
    history.append(record)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(history[-60:], f, indent=2)


def broadcast_reel(video_path, yt_title, yt_desc, yt_tags, yt_comment, ig_caption, fb_caption, tag_name):
    outcomes = {}
    try:
        outcomes["youtube"] = upload_youtube_short(video_path, yt_title, yt_desc, yt_tags, yt_comment)
    except Exception as e:
        print("❌ YouTube Upload Error:", e)
        outcomes["youtube"] = {"status": "ERROR", "detail": str(e)}

    public_mp4_url = create_temp_public_url(video_path, tag_name)
    try:
        try:
            outcomes["instagram"] = upload_instagram_reel(public_mp4_url, ig_caption)
        except Exception as e:
            print("❌ Instagram Upload Error:", e)
            outcomes["instagram"] = {"status": "ERROR", "detail": str(e)}

        try:
            outcomes["facebook"] = upload_facebook_reel(public_mp4_url, fb_caption)
        except Exception as e:
            print("❌ Facebook Upload Error:", e)
            outcomes["facebook"] = {"status": "ERROR", "detail": str(e)}
    finally:
        subprocess.run(["gh", "release", "delete", tag_name, "-y"], stderr=subprocess.DEVNULL)

    return outcomes


def main():
    with open("assets/analysis_output.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    smc = data.get("smc", {})
    session_name = data.get("session", "LONDON SESSION")

    # 1. Load ReachBoost SEO package if present, otherwise fall back to seo_engine
    if os.path.exists("data/seo_package.json"):
        with open("data/seo_package.json", "r", encoding="utf-8") as f:
            rb_seo = json.load(f)
        seo = {
            "yt_title": rb_seo.get("yt_title", f"XAUUSD {session_name} Setup #Shorts"),
            "yt_description": rb_seo.get("yt_description", ""),
            "yt_tags": rb_seo.get("yt_tags", []),
            "yt_pinned_comment": rb_seo.get("yt_pinned_comment", ""),
            "ig_caption": rb_seo.get("ig_fb_caption", ""),
            "fb_caption": rb_seo.get("ig_fb_caption", ""),
        }
        print("📦 Loaded ReachBoost SEO package from data/seo_package.json")
    else:
        seo = data.get("seo") or build_seo_package(smc, session_name, data)

    results = {}
    yt_url = ""

    # 2. Publish Reel to YouTube, Instagram, and Facebook first so we get the live YouTube URL
    if os.path.exists("assets/final_reel.mp4"):
        reel_res = broadcast_reel(
            "assets/final_reel.mp4",
            seo["yt_title"],
            seo["yt_description"],
            seo.get("yt_tags"),
            seo.get("yt_pinned_comment"),
            seo["ig_caption"],
            seo["fb_caption"],
            "fr6fx-temp-main"
        )
        results.update(reel_res)
        yt_url = reel_res.get("youtube", {}).get("url", "")

    # 3. Hand off to Agent 6 (ChannelPilot) to publish chart, reel & weekend poll to Telegram
    try:
        tg_ok = post_channel_update("assets/final_reel.mp4", "assets/telegram_chart.png", data, yt_url=yt_url)
        results["telegram"] = {"status": "OK" if tg_ok else "SKIPPED"}
    except Exception as e:
        print("❌ ChannelPilot Error:", e)
        results["telegram"] = {"status": "ERROR", "detail": str(e)}

    save_run_state(data, seo, results)
    print("📊 Run state saved to state/last_run.json")


if __name__ == "__main__":
    main()
