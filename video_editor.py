import os
import re
import json
import asyncio
import subprocess
import edge_tts
from gtts import gTTS
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

async def generate_voiceover(text, out_mp3):
    clean_text = re.sub(r"\s+", " ", text).strip()
    try:
        communicate = edge_tts.Communicate(
            clean_text,
            voice="en-US-ChristopherNeural",
            rate="-4%",
            pitch="-2Hz"
        )
        await communicate.save(out_mp3)
        if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1000:
            print("✅ Natural Mentor Voiceover generated via Edge-TTS")
            return
    except Exception as e:
        print(f"⚠️ Edge-TTS fallback triggered: {e}")

    tts = gTTS(text=clean_text, lang="en", slow=False)
    tts.save(out_mp3)
    print("✅ Voiceover generated via gTTS fallback")

def extract_word_captions(audio_path):
    """Uses Whisper to get exact word timestamps and auto-corrects trading terms like 'buy-side'."""
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, word_timestamps=True)
    words = []
    for seg in segments:
        for w in seg.words:
            txt = w.word.strip().upper()
            txt = txt.replace("BICIDE", "BUY-SIDE").replace("BY SIDE", "BUY-SIDE").replace("CELL SIDE", "SELL-SIDE")
            if txt:
                words.append({"word": txt, "start": w.start, "end": w.end})
    return words

def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    res = subprocess.check_output(cmd).decode().strip()
    return max(float(res), 15.0)

def derive_viral_hook(smc, session_name):
    """Generates a consistent, high-CTR 3-word cover headline based on live market structure."""
    pa = smc.get("pa_signal", "").lower()
    bias = smc.get("bias_label", "").upper()
    if "sweep" in pa and "bearish" in bias.lower():
        return "GOLD LIQUIDITY TRAP", "#ef4444"
    elif "sweep" in pa and "bullish" in bias.lower():
        return "GOLD STOP HUNT", "#00c896"
    elif "bearish" in bias:
        return "GOLD SUPPLY REJECTION", "#ef4444"
    elif "bullish" in bias:
        return "GOLD DEMAND BOUNCE", "#00c896"
    return f"{session_name.split()[0]} GOLD SETUP", "#f59e0b"

def build_viral_cover_frame(smc, session_name, date_label, chart_png_path, out_png):
    """Creates a uniform, eye-catching static cover frame (0.0s–0.45s) for consistent channel grid thumbnails."""
    img = Image.new("RGB", (W, H), (9, 13, 24))
    draw = ImageDraw.Draw(img)

    f_brand = load_font(FONT_BOLD, 34)
    f_sess = load_font(FONT_BOLD, 30)
    f_hook = load_font(FONT_BOLD, 66)
    f_price = load_font(FONT_BOLD, 36)
    f_card_lbl = load_font(FONT_BOLD, 22)
    f_card_val = load_font(FONT_BOLD, 34)
    f_cta = load_font(FONT_BOLD, 28)

    hook_text, accent_hex = derive_viral_hook(smc, session_name)
    accent_rgb = tuple(int(accent_hex.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))

    # Top Brand Bar (Identical layout across all Shorts for uniform grid branding)
    draw.rounded_rectangle([56, 70, 1024, 155], radius=18, fill=(17, 25, 42), outline=(45, 62, 92), width=3)
    draw.ellipse([86, 97, 118, 129], fill=(245, 158, 11))
    draw.text((135, 92), f"FR6 FX  •  XAUUSD {session_name}", fill=(255, 255, 255), font=f_brand)

    # Big Bold Viral Hook Banner (Frame 0 Thumbnail Headline)
    draw.rounded_rectangle([56, 178, 1024, 345], radius=22, fill=(15, 22, 38), outline=accent_rgb, width=4)
    bbox = draw.textbbox((0, 0), hook_text, font=f_hook)
    hw = bbox[2] - bbox[0]
    draw.text(((W - hw) // 2, 198), hook_text, fill=(255, 255, 255), font=f_hook)

    sub_line = f"LIVE GOLD: ${smc['live_price']}   |   {smc['bias_label']}   |   {date_label}"
    sbbox = draw.textbbox((0, 0), sub_line, font=f_sess)
    sw = sbbox[2] - sbbox[0]
    draw.text(((W - sw) // 2, 286), sub_line, fill=accent_rgb, font=f_sess)

    # Crisp Chart Preview Window with Exact Supply/Demand Rectangles
    draw.rounded_rectangle([56, 370, 1024, 1245], radius=22, fill=(13, 18, 29), outline=(45, 62, 92), width=3)
    if os.path.exists(chart_png_path):
        c_img = Image.open(chart_png_path).convert("RGB").resize((956, 860), Image.Resampling.LANCZOS)
        img.paste(c_img, (62, 377))

    # 3 Clean Bottom Key-Level Cards
    cards = [
        ("SUPPLY ZONE", f"${smc['strong_high']}", (239, 68, 68), (44, 18, 26)),
        ("50% EQUILIBRIUM", f"${smc['equilibrium']}", (245, 158, 11), (42, 32, 16)),
        ("DEMAND ZONE", f"${smc['strong_low']}", (6, 182, 212), (14, 38, 48)),
    ]
    card_w = 304
    for idx, (lbl, val, col, bg) in enumerate(cards):
        cx = 56 + idx * 332
        cy = 1272
        draw.rounded_rectangle([cx, cy, cx + card_w, cy + 125], radius=18, fill=bg, outline=col, width=3)
        draw.text((cx + 22, cy + 20), lbl, fill=col, font=f_card_lbl)
        draw.text((cx + 22, cy + 58), val, fill=(255, 255, 255), font=f_card_val)

    # Bottom Viral Badge Pill
    draw.rounded_rectangle([140, 1445, 940, 1525], radius=40, fill=accent_rgb)
    badge_txt = "⚡ WATCH LIVE INSTITUTIONAL ZONES ⚡"
    bb = draw.textbbox((0, 0), badge_txt, font=f_price)
    bw = bb[2] - bb[0]
    draw.text(((W - bw) // 2, 1463), badge_txt, fill=(10, 14, 24), font=f_price)

    tg_link = os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official").replace("https://", "").strip()
    draw.rounded_rectangle([120, 1565, 960, 1625], radius=14, fill=(18, 28, 46), outline=(56, 189, 248), width=2)
    cta = f"FREE TELEGRAM CHARTS & NEWS: {tg_link}"
    cb = draw.textbbox((0, 0), cta, font=f_cta)
    draw.text(((W - (cb[2] - cb[0])) // 2, 1580), cta, fill=(224, 242, 254), font=f_cta)

    img.save(out_png)
def build_background_plate(smc, session_name, date_label, out_png):
    """Creates the clean, unobstructed vertical terminal frame (no floating boxes covering candles)."""
    img = Image.new("RGB", (W, H), (9, 13, 24))
    draw = ImageDraw.Draw(img)

    f_brand = load_font(FONT_BOLD, 32)
    f_sub = load_font(FONT_BOLD, 27)
    f_card_lbl = load_font(FONT_BOLD, 21)
    f_card_val = load_font(FONT_BOLD, 34)
    f_cta = load_font(FONT_BOLD, 25)
    f_disc = load_font(FONT_REG, 20)

    # Top Header Bar
    draw.rounded_rectangle([56, 70, W - 56, 152], radius=18, fill=(17, 25, 42), outline=(45, 62, 92), width=2)
    draw.ellipse([82, 96, 110, 124], fill=(245, 158, 11))
    draw.text((126, 93), f"FR6 FX  •  {session_name}  [LIVE SMC CHART]", fill=(255, 255, 255), font=f_brand)

    # Second Status Strip
    bias_col = (239, 68, 68) if "BEARISH" in smc["bias_label"].upper() else (0, 200, 150)
    draw.rounded_rectangle([56, 170, W - 56, 236], radius=14, fill=(15, 22, 38), outline=(36, 50, 77), width=2)
    status_txt = f"{smc['bias_label']}   |   DXY: {smc['dxy_now']}   |   GOLD: ${smc['live_price']}"
    draw.text((84, 188), status_txt, fill=bias_col, font=f_sub)

    # Chart Frame Border (960x860 live candle video sits cleanly inside)
    draw.rounded_rectangle([54, 254, W - 54, 1126], radius=20, fill=(11, 16, 27), outline=(45, 62, 92), width=3)

    # 3 Clean Bottom Summary Cards (below the chart so zero candles are blocked)
    cards = [
        ("SUPPLY CAP", f"${smc['strong_high']}", (239, 68, 68), (44, 18, 26)),
        ("50% EQUILIBRIUM", f"${smc['equilibrium']}", (245, 158, 11), (42, 32, 16)),
        ("DEMAND FLOOR", f"${smc['strong_low']}", (6, 182, 212), (14, 38, 48)),
    ]
    card_w = 304
    for idx, (lbl, val, col, bg) in enumerate(cards):
        cx = 56 + idx * 332
        cy = 1152
        draw.rounded_rectangle([cx, cy, cx + card_w, cy + 120], radius=16, fill=bg, outline=col, width=2)
        draw.text((cx + 20, cy + 18), lbl, fill=col, font=f_card_lbl)
        draw.text((cx + 20, cy + 54), val, fill=(255, 255, 255), font=f_card_val)

    # Bottom Free Telegram CTA Bar
    tg_link = os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official").replace("https://", "").strip()
    draw.rounded_rectangle([56, 1545, W - 56, 1622], radius=14, fill=(18, 28, 46), outline=(56, 189, 248), width=2)
    cta = f"FREE TELEGRAM CHARTS & NEWS: {tg_link}"
    cb = draw.textbbox((0, 0), cta, font=f_cta)
    draw.text(((W - (cb[2] - cb[0])) // 2, 1570), cta, fill=(224, 242, 254), font=f_cta)

    disc = f"@FR6FX • {date_label} • Educational purposes only. Not financial advice."
    db = draw.textbbox((0, 0), disc, font=f_disc)
    draw.text(((W - (db[2] - db[0])) // 2, 1642), disc, fill=(148, 163, 184), font=f_disc)

    img.save(out_png)

def build_ass_subtitles(words, out_ass, time_offset=0.45):
    """Generates punchy 3-word Hormozi-style dynamic captions shifted by cover duration."""
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,58,&H00FFFFFF,&H0000FFFF,&H00080C14,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,475,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def fmt_ts(sec):
        sec = max(sec, 0.0)
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = sec % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines = [header]
    chunk_size = 3
    for i in range(0, len(words), chunk_size):
        chunk = words[i:i + chunk_size]
        if not chunk:
            continue
        start_t = chunk[0]["start"] + time_offset
        end_t = chunk[-1]["end"] + time_offset + 0.12
        for j, w in enumerate(chunk):
            w_start = w["start"] + time_offset
            w_end = (chunk[j + 1]["start"] + time_offset) if j + 1 < len(chunk) else end_t
            styled_tokens = []
            for k, tok in enumerate(chunk):
                if k == j:
                    styled_tokens.append(r"{\c&H0015CCFA&\fscx108\fscy108}" + tok["word"] + r"{\c&H00FFFFFF&\fscx100\fscy100}")
                else:
                    styled_tokens.append(tok["word"])
            dialogue = " ".join(styled_tokens)
            lines.append(f"Dialogue: 0,{fmt_ts(w_start)},{fmt_ts(w_end)},Default,,0,0,0,,{dialogue}\n")

    with open(out_ass, "w", encoding="utf-8") as f:
        f.writelines(lines)
def export_telegram_chart(smc, session_name, date_label, out_png):
    """Creates the crisp, high-resolution annotated chart image posted to Telegram."""
    canvas = Image.new("RGB", (1080, 1140), (9, 13, 24))
    draw = ImageDraw.Draw(canvas)

    f_title = load_font(FONT_BOLD, 30)
    f_sub = load_font(FONT_BOLD, 24)
    f_lbl = load_font(FONT_BOLD, 19)
    f_val = load_font(FONT_BOLD, 28)

    draw.rounded_rectangle([32, 24, 1048, 104], radius=16, fill=(17, 25, 42), outline=(45, 62, 92), width=2)
    draw.text((56, 46), f"FR6 FX  •  XAUUSD {session_name} ({date_label})", fill=(255, 255, 255), font=f_title)

    if os.path.exists("assets/tv_5m.png"):
        chart = Image.open("assets/tv_5m.png").convert("RGB").resize((1016, 860), Image.Resampling.LANCZOS)
        canvas.paste(chart, (32, 122))

    cards = [
        ("SUPPLY ZONE", f"${smc['strong_high']}", (239, 68, 68), (44, 18, 26)),
        ("50% EQUILIBRIUM", f"${smc['equilibrium']}", (245, 158, 11), (42, 32, 16)),
        ("DEMAND ZONE", f"${smc['strong_low']}", (6, 182, 212), (14, 38, 48)),
    ]
    for idx, (lbl, val, col, bg) in enumerate(cards):
        cx = 32 + idx * 348
        cy = 1002
        draw.rounded_rectangle([cx, cy, cx + 320, cy + 112], radius=14, fill=bg, outline=col, width=2)
        draw.text((cx + 18, cy + 16), lbl, fill=col, font=f_lbl)
        draw.text((cx + 18, cy + 48), val, fill=(255, 255, 255), font=f_val)

    canvas.save(out_png)
    print("✅ High-res Telegram SMC Chart exported.")

async def render_reel_video(spoken_script, smc, session_name, date_label, out_mp4, prefix="main"):
    audio_mp3 = f"assets/{prefix}_voice.mp3"
    cover_png = f"assets/{prefix}_cover.png"
    bg_png = f"assets/{prefix}_bg.png"
    ass_file = f"assets/{prefix}_subs.ass"
    body_mp4 = f"assets/{prefix}_body.mp4"
    cover_mp4 = f"assets/{prefix}_cover.mp4"

    await generate_voiceover(spoken_script, audio_mp3)
    words = extract_word_captions(audio_mp3)
    dur = get_audio_duration(audio_mp3)
    cover_dur = 0.45

    build_viral_cover_frame(smc, session_name, date_label, "assets/tv_5m.png", cover_png)
    build_background_plate(smc, session_name, date_label, bg_png)
    build_ass_subtitles(words, ass_file, time_offset=0.0)

    # 1. Render 0.45s Uniform Viral Cover Clip (guarantees cohesive grid thumbnails on YouTube & IG)
    cmd_cover = [
        "ffmpeg", "-y", "-loop", "1", "-t", str(cover_dur), "-i", cover_png,
        "-f", "lavfi", "-t", str(cover_dur), "-i", "anullsrc=r=44100:cl=stereo",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-preset", "veryfast",
        "-c:a", "aac", "-b:a", "128k", "-shortest", cover_mp4
    ]
    subprocess.run(cmd_cover, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. Render Main Live-Candle Chart Analysis Body (15M first half -> 5M second half)
    half_dur = dur / 2.0
    filter_complex = (
        f"[1:v]scale=960:860,trim=duration={half_dur},setpts=PTS-STARTPTS[c15];"
        f"[2:v]scale=960:860,trim=duration={half_dur + 0.5},setpts=PTS-STARTPTS[c5];"
        f"[c15][c5]concat=n=2:v=1:a=0[chart];"
        f"[0:v][chart]overlay=60:260[bg_chart];"
        f"[bg_chart]ass={ass_file}[v]"
    )

    cmd_body = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(dur + 0.3), "-i", bg_png,
        "-stream_loop", "-1", "-i", "assets/tv_15m.webm",
        "-stream_loop", "-1", "-i", "assets/tv_5m.webm",
        "-i", audio_mp3,
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "3:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-shortest", body_mp4
    ]
    subprocess.run(cmd_body, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 3. Concatenate Uniform Cover Frame + Main Live Chart Video
    concat_txt = f"assets/{prefix}_concat.txt"
    with open(concat_txt, "w") as f:
        f.write(f"file '{os.path.abspath(cover_mp4)}'\n")
        f.write(f"file '{os.path.abspath(body_mp4)}'\n")

    cmd_final = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c", "copy", out_mp4
    ]
    subprocess.run(cmd_final, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"✅ Rendered {out_mp4} ({dur + cover_dur:.1f}s with uniform viral cover thumbnail)")

async def main():
    with open("assets/analysis_output.json", "r") as f:
        data = json.load(f)

    smc = data["smc"]
    session = data["session"]
    date_label = data["date_label"]

    export_telegram_chart(smc, session, date_label, "assets/telegram_chart.png")

    await render_reel_video(
        data["spoken_script"],
        smc,
        session,
        date_label,
        "assets/final_reel.mp4",
        prefix="main"
    )

    if data.get("recap_enabled") and data.get("recap_spoken_script"):
        await render_reel_video(
            data["recap_spoken_script"],
            smc,
            f"{session} RECAP",
            date_label,
            "assets/recap_reel.mp4",
            prefix="recap"
        )

if __name__ == "__main__":
    asyncio.run(main())
