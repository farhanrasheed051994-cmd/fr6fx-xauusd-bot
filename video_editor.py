import os
import json
import asyncio
import subprocess
import edge_tts
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw, ImageFont

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def get_audio_duration(audio_path):
    cmd = (
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    )
    out = subprocess.check_output(cmd).decode().strip()
    return float(out)

async def generate_voiceover(text, out_mp3):
    voices = (
        "en-US-AndrewNeural",
        "en-US-GuyNeural",
        "en-GB-RyanNeural",
        "en-US-ChristopherNeural"
    )
    for v in voices:
        try:
            communicate = edge_tts.Communicate(text, voice=v, rate="+2%")
            await communicate.save(out_mp3)
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 2048:
                print(f"✅ Voiceover saved using Edge-TTS ({v}): {out_mp3}")
                return
        except Exception as e:
            print(f"⚠️ Edge-TTS {v} failed: {e}")
            await asyncio.sleep(1)

    print("🔄 Falling back to Google TTS (gTTS)...")
    from gtts import gTTS
    tts = gTTS(text=text, lang="en", tld="com", slow=False)
    raw_gtts = out_mp3 + ".raw.mp3"
    tts.save(raw_gtts)
    cmd = (
        "ffmpeg", "-y", "-i", raw_gtts,
        "-filter:a", "atempo=1.12",
        "-vn", out_mp3
    )
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"✅ Voiceover saved using gTTS: {out_mp3}")

def extract_word_captions(audio_path):
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, word_timestamps=True)
    words = list()
    for seg in segments:
        for w in (seg.words or ()):
            clean_w = w.word.strip()
            if clean_w:
                words.append({
                    "word": clean_w,
                    "start": float(w.start),
                    "end": float(w.end)
                })
    return words

def detect_stage_timestamps(words, total_dur):
    t2 = round(total_dur * 0.20, 2)
    t3 = round(total_dur * 0.38, 2)
    t4 = round(total_dur * 0.56, 2)
    t5 = round(total_dur * 0.74, 2)

    n_words = len(words)
    for i in range(n_words):
        w_cur = words.__getitem__(i).get("word", "").lower().strip(".,!?")
        w_next = words.__getitem__(i + 1).get("word", "").lower().strip(".,!?") if (i + 1) < n_words else ""
        st = float(words.__getitem__(i).get("start", 0.0))
        if "resist" in w_cur and 1.5 <= st <= total_dur * 0.45:
            t2 = round(st, 2)
        elif "support" in w_cur and t2 + 1.0 <= st <= total_dur * 0.65:
            t3 = round(st, 2)
        elif w_cur == "watch" and "zone" in w_next and t3 + 1.0 <= st <= total_dur * 0.80:
            t4 = round(st, 2)
        elif (w_cur in ("5", "five") and "minute" in w_next) or w_cur == "dropping":
            if t4 + 1.0 <= st <= total_dur - 2.5:
                t5 = round(st, 2)

    t2 = max(1.5, min(t2, total_dur - 6.0))
    t3 = max(t2 + 1.5, min(t3, total_dur - 4.5))
    t4 = max(t3 + 1.5, min(t4, total_dur - 3.0))
    t5 = max(t4 + 1.5, min(t5, total_dur - 1.8))
    return (t2, t3, t4, t5)

def build_composite_stage_frame(smc, session_name, hook_title, stage_png, pill_text, show_follow, out_png):
    canvas = Image.new("RGB", (1080, 1920), (11, 15, 23))
    draw = ImageDraw.Draw(canvas)

    f_title = load_font(FONT_BOLD, 40)
    f_meta = load_font(FONT_BOLD, 25)
    f_pill = load_font(FONT_BOLD, 32)
    f_follow = load_font(FONT_BOLD, 24)
    f_cta = load_font(FONT_BOLD, 21)
    f_disc = load_font(FONT_REG, 18)

    header_txt = f"XAUUSD {session_name} ANALYSIS"
    hw = draw.textlength(header_txt, font=f_title)
    draw.text(((1080 - hw) * 0.5, 195), header_txt, fill=(250, 204, 21), font=f_title)

    live_p = smc.get("live_price")
    bias_l = str(smc.get("bias_label", ""))
    meta_left = f"XAUUSD  •  {bias_l}"
    meta_right = f"${live_p}"
    draw.text((64, 275), meta_left, fill=(148, 163, 184), font=f_meta)
    rw = draw.textlength(meta_right, font=f_meta)
    draw.text((1016 - rw, 275), meta_right, fill=(250, 204, 21), font=f_meta)

    chart = Image.open(stage_png).convert("RGB").resize((1080, 990), Image.Resampling.LANCZOS)
    canvas.paste(chart, (0, 320))

    pw = draw.textlength(pill_text, font=f_pill)
    box_w = min(920, max(500, int(pw + 80)))
    x1 = int((1080 - box_w) * 0.5)
    x2 = x1 + box_w
    draw.rounded_rectangle((x1, 1340, x2, 1420), radius=22, fill=(17, 24, 39), outline=(245, 158, 11), width=4)
    draw.text(((1080 - pw) * 0.5, 1362), pill_text, fill=(255, 255, 255), font=f_pill)

    if show_follow:
        fol_txt = "Follow @fr6fx for daily Gold analysis"
        fw = draw.textlength(fol_txt, font=f_follow)
        draw.text(((1080 - fw) * 0.5, 1445), fol_txt, fill=(255, 255, 255), font=f_follow)

    tg_link = (
        os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official")
        .replace("https://", "")
        .replace("http://", "")
        .strip()
    )
    cta_txt = f"Join Telegram for daily XAUUSD analysis: {tg_link}"
    cw = draw.textlength(cta_txt, font=f_cta)
    draw.text(((1080 - cw) * 0.5, 1490), cta_txt, fill=(56, 189, 248), font=f_cta)

    disc_txt = "Not financial advice"
    dw = draw.textlength(disc_txt, font=f_disc)
    draw.text(((1080 - dw) * 0.5, 1528), disc_txt, fill=(100, 116, 139), font=f_disc)

    canvas.save(out_png)
def export_telegram_chart_graphic(smc, session_name, date_label, chart_png, out_png):
    canvas = Image.new("RGB", (1080, 1280), (11, 16, 27))
    draw = ImageDraw.Draw(canvas)
    f_title = load_font(FONT_BOLD, 24)
    f_sub = load_font(FONT_BOLD, 19)
    f_card_lbl = load_font(FONT_BOLD, 18)
    f_card_val = load_font(FONT_BOLD, 24)

    bias_l = str(smc.get("bias_label", "NEUTRAL"))
    is_bull = "BULLISH" in bias_l
    bias_col = (34, 197, 94) if is_bull else ((239, 68, 68) if "BEARISH" in bias_l else (245, 158, 11))

    draw.rounded_rectangle((28, 22, 1052, 122), radius=14, fill=(17, 25, 43), outline=(56, 189, 248), width=2)
    draw.text((48, 36), f"FR6 FX  |  XAUUSD {session_name}", fill=(255, 255, 255), font=f_title)
    draw.text((48, 78), f"{date_label}  |  SPOT: ${smc.get('live_price')}  |  DXY: {smc.get('dxy_now')}", fill=(250, 204, 21), font=f_sub)

    draw.rounded_rectangle((835, 34, 1032, 74), radius=8, fill=bias_col)
    draw.text((852, 43), bias_l, fill=(11, 16, 27), font=f_card_lbl)

    chart = Image.open(chart_png).convert("RGB").resize((1080, 1000), Image.Resampling.LANCZOS)
    canvas.paste(chart, (0, 134))

    cards = (
        (28, 356, "RESISTANCE", f"${smc.get('strong_high')}", (239, 68, 68), (254, 202, 202)),
        (376, 704, "WATCH ZONE", str(smc.get("demand_zone") if is_bull else smc.get("supply_zone")), (245, 158, 11), (253, 230, 138)),
        (724, 1052, "SUPPORT", f"${smc.get('strong_low')}", (6, 182, 212), (165, 243, 252))
    )
    for x1, x2, lbl, val, border_c, val_c in cards:
        draw.rounded_rectangle((x1, 1148, x2, 1254), radius=12, fill=(17, 25, 43), outline=border_c, width=2)
        draw.text((x1 + 16, 1162), lbl, fill=(148, 163, 184), font=f_card_lbl)
        draw.text((x1 + 16, 1198), val, fill=val_c, font=f_card_val)

    canvas.save(out_png)
    print(f"✅ Telegram institutional chart saved: {out_png}")

def render_progressive_reel(smc, session_name, hook_title, spoken_script, out_mp4):
    os.makedirs("assets", exist_ok=True)
    voice_mp3 = "assets/voiceover.mp3"

    asyncio.run(generate_voiceover(spoken_script, voice_mp3))
    voice_dur = get_audio_duration(voice_mp3)
    words = extract_word_captions(voice_mp3)

    total_dur = round(voice_dur + 0.5, 2)
    t2, t3, t4, t5 = detect_stage_timestamps(words, voice_dur)
    print(f"⏱️ Progressive Reel ({total_dur}s) | Res: {t2}s | Sup: {t3}s | WatchZone: {t4}s | M5 Entry: {t5}s")

    is_bull = "BULLISH" in str(smc.get("bias_label", ""))
    res_int = int(round(float(smc.get("strong_high"))))
    sup_int = int(round(float(smc.get("strong_low"))))
    wz_low = int(round(float(smc.get("strong_low")))) if is_bull else int(round(float(smc.get("retest_res"))))
    wz_high = int(round(float(smc.get("retest_sup")))) if is_bull else int(round(float(smc.get("strong_high"))))

    stages_spec = (
        ("assets/stage_1.png", "Gold M15: full chart analysis", False, "assets/frame_1.png", round(t2, 2)),
        ("assets/stage_2.png", f"Resistance: {res_int}", False, "assets/frame_2.png", round(t3 - t2, 2)),
        ("assets/stage_3.png", f"Support: {sup_int}", False, "assets/frame_3.png", round(t4 - t3, 2)),
        ("assets/stage_4.png", f"Watch zone: {wz_low} - {wz_high}", False, "assets/frame_4.png", round(t5 - t4, 2)),
        ("assets/stage_5.png", "Wait for confirmation, no chase", True, "assets/frame_5.png", round(total_dur - t5, 2))
    )

    for st_png, pill, show_fol, fr_png, _ in stages_spec:
        build_composite_stage_frame(smc, session_name, hook_title, st_png, pill, show_fol, fr_png)

    d1 = stages_spec.__getitem__(0).__getitem__(4)
    d2 = stages_spec.__getitem__(1).__getitem__(4)
    d3 = stages_spec.__getitem__(2).__getitem__(4)
    d4 = stages_spec.__getitem__(3).__getitem__(4)
    d5 = stages_spec.__getitem__(4).__getitem__(4)

    filter_complex = (
        f"[0:v]scale=1080:1920,trim=duration={d1},setpts=PTS-STARTPTS[v0];"
        f"[1:v]scale=1080:1920,trim=duration={d2},setpts=PTS-STARTPTS[v1];"
        f"[2:v]scale=1080:1920,trim=duration={d3},setpts=PTS-STARTPTS[v2];"
        f"[3:v]scale=1080:1920,trim=duration={d4},setpts=PTS-STARTPTS[v3];"
        f"[4:v]scale=1080:1920,trim=duration={d5},setpts=PTS-STARTPTS[v4];"
        f"[v0][v1][v2][v3][v4]concat=n=5:v=1:a=0[vout];"
        f"[5:a]apad=whole_dur={total_dur}[aout]"
    )

    cmd = (
        "ffmpeg", "-y",
        "-loop", "1", "-i", "assets/frame_1.png",
        "-loop", "1", "-i", "assets/frame_2.png",
        "-loop", "1", "-i", "assets/frame_3.png",
        "-loop", "1", "-i", "assets/frame_4.png",
        "-loop", "1", "-i", "assets/frame_5.png",
        "-i", voice_mp3,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-r", "30", "-c:a", "aac", "-b:a", "192k", "-t", str(total_dur),
        out_mp4
    )
    subprocess.run(cmd, check=True)
    print(f"🎬 Final Progressive 1080x1920 FR6 FX Reel exported: {out_mp4}")

def main():
    with open("assets/analysis_output.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    smc = data.get("smc", {})
    session_name = data.get("session", "LONDON ANALYSIS")
    date_label = data.get("date_label", "")
    hook_title = data.get("hook_title", "WILL GOLD PUMP FROM DEMAND?")
    spoken_script = data.get("spoken_script", "")

    export_telegram_chart_graphic(
        smc, session_name, date_label, "assets/stage_5.png", "assets/telegram_chart.png"
    )
    render_progressive_reel(
        smc, session_name, hook_title, spoken_script, "assets/final_reel.mp4"
    )

if __name__ == "__main__":
    main()
