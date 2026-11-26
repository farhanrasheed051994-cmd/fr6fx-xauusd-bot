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
            communicate = edge_tts.Communicate(text, voice=v, rate="+5%")
            await communicate.save(out_mp3)
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 2048:
                print(f"✅ Voiceover saved using Edge-TTS ({v}): {out_mp3}")
                return
        except Exception as e:
            print(f"⚠️ Edge-TTS {v} failed: {e}")
            await asyncio.sleep(1)

    from gtts import gTTS
    tts = gTTS(text=text, lang="en", tld="com", slow=False)
    raw_gtts = out_mp3 + ".raw.mp3"
    tts.save(raw_gtts)
    subprocess.run(
        ("ffmpeg", "-y", "-i", raw_gtts, "-filter:a", "atempo=1.15", "-vn", out_mp3),
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def extract_word_captions(audio_path):
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, word_timestamps=True)
    words = []
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
    t5 = round(total_dur * 0.75, 2)

    n_words = len(words)
    for i in range(n_words):
        w_cur = words[i].get("word", "").lower().strip(".,!?")
        w_next = words[i + 1].get("word", "").lower().strip(".,!?") if (i + 1) < n_words else ""
        st = float(words[i].get("start", 0.0))
        if "resist" in w_cur and 1.2 <= st <= total_dur * 0.45:
            t2 = round(st, 2)
        elif "support" in w_cur and t2 + 1.0 <= st <= total_dur * 0.65:
            t3 = round(st, 2)
        elif w_cur == "watch" and "zone" in w_next and t3 + 1.0 <= st <= total_dur * 0.82:
            t4 = round(st, 2)
        elif (w_cur in ("5", "five") and "minute" in w_next) or w_cur == "dropping":
            if t4 + 1.0 <= st <= total_dur - 2.0:
                t5 = round(st, 2)

    t2 = max(1.5, min(t2, total_dur - 5.5))
    t3 = max(t2 + 1.5, min(t3, total_dur - 4.0))
    t4 = max(t3 + 1.5, min(t4, total_dur - 2.8))
    t5 = max(t4 + 1.5, min(t5, total_dur - 1.6))
    return (t2, t3, t4, t5)
def render_caption_overlays(words, total_dur):
    """Creates transparent 1080x1920 PNG overlays for 3-word karaoke-style captions."""
    os.makedirs("assets/caps", exist_ok=True)
    f_cap = load_font(FONT_BOLD, 46)
    overlays = []

    chunk_size = 3
    for idx in range(0, len(words), chunk_size):
        chunk = words[idx : idx + chunk_size]
        for active_i, active_w in enumerate(chunk):
            start_t = round(active_w["start"], 2)
            if active_i + 1 < len(chunk):
                end_t = round(chunk[active_i + 1]["start"], 2)
            elif idx + chunk_size < len(words):
                end_t = round(words[idx + chunk_size]["start"], 2)
            else:
                end_t = round(min(active_w["end"] + 0.35, total_dur), 2)

            if end_t <= start_t:
                continue

            img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            tokens = [w["word"].upper() for w in chunk]
            space_w = draw.textlength(" ", font=f_cap)
            widths = [draw.textlength(t, font=f_cap) for t in tokens]
            total_w = sum(widths) + space_w * (len(tokens) - 1)

            pad_x, pad_y = 34, 18
            box_w = int(total_w + pad_x * 2)
            x_box = int((1080 - box_w) * 0.5)
            y_box = 1320

            draw.rounded_rectangle(
                (x_box, y_box, x_box + box_w, y_box + 84),
                radius=20, fill=(10, 15, 28, 230), outline=(56, 189, 248, 180), width=2
            )

            cur_x = x_box + pad_x
            for j, tok in enumerate(tokens):
                col = (250, 204, 21, 255) if j == active_i else (255, 255, 255, 255)
                draw.text((cur_x, y_box + pad_y), tok, fill=col, font=f_cap)
                cur_x += widths[j] + space_w

            cap_path = f"assets/caps/cap_{len(overlays):03d}.png"
            img.save(cap_path)
            overlays.append((cap_path, start_t, end_t))

    return overlays


def build_composite_stage_frame(smc, session_name, hook_title, stage_png, pill_text, out_png):
    canvas = Image.new("RGB", (1080, 1920), (11, 15, 23))
    draw = ImageDraw.Draw(canvas)

    f_hook = load_font(FONT_BOLD, 46)
    f_meta = load_font(FONT_BOLD, 24)
    f_pill = load_font(FONT_BOLD, 30)
    f_cta = load_font(FONT_BOLD, 22)
    f_disc = load_font(FONT_REG, 18)

    # Top Curiosity Hook Banner
    hook_clean = str(hook_title).upper()[:38]
    hw = draw.textlength(hook_clean, font=f_hook)
    draw.text(((1080 - hw) * 0.5, 165), hook_clean, fill=(250, 204, 21), font=f_hook)

    # Session + Live Price Strip
    live_p = smc["live_price"]
    bias_l = str(smc["bias_label"])
    meta_left = f"{session_name}  •  {bias_l}"
    meta_right = f"GOLD ${live_p}"
    draw.text((54, 242), meta_left, fill=(148, 163, 184), font=f_meta)
    rw = draw.textlength(meta_right, font=f_meta)
    draw.text((1026 - rw, 242), meta_right, fill=(56, 189, 248), font=f_meta)

    # Institutional Chart
    chart = Image.open(stage_png).convert("RGB").resize((1080, 960), Image.Resampling.LANCZOS)
    canvas.paste(chart, (0, 290))

    # Stage Level Pill (above captions)
    pw = draw.textlength(pill_text, font=f_pill)
    box_w = min(940, max(480, int(pw + 72)))
    x1 = int((1080 - box_w) * 0.5)
    draw.rounded_rectangle((x1, 1265, x1 + box_w, 1312), radius=14, fill=(17, 24, 39), outline=(245, 158, 11), width=2)
    draw.text(((1080 - pw) * 0.5, 1272), pill_text, fill=(255, 255, 255), font=f_pill)

    # Bottom Brand CTA (below captions at y=1430+)
    tg_link = (
        os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official")
        .replace("https://", "")
        .replace("http://", "")
        .strip()
    )
    cta_txt = f"Follow @FR6FX  •  Free Telegram: {tg_link}"
    cw = draw.textlength(cta_txt, font=f_cta)
    draw.text(((1080 - cw) * 0.5, 1445), cta_txt, fill=(56, 189, 248), font=f_cta)

    disc_txt = "Educational analysis only • Not financial advice"
    dw = draw.textlength(disc_txt, font=f_disc)
    draw.text(((1080 - dw) * 0.5, 1485), disc_txt, fill=(100, 116, 139), font=f_disc)

    canvas.save(out_png)


def export_telegram_chart_graphic(smc, session_name, date_label, chart_png, out_png):
    canvas = Image.new("RGB", (1080, 1260), (11, 16, 27))
    draw = ImageDraw.Draw(canvas)
    f_title = load_font(FONT_BOLD, 25)
    f_sub = load_font(FONT_BOLD, 19)
    f_card_lbl = load_font(FONT_BOLD, 17)
    f_card_val = load_font(FONT_BOLD, 23)

    bias_l = str(smc.get("bias_label", "NEUTRAL"))
    is_bull = "BULLISH" in bias_l
    bias_col = (16, 185, 129) if is_bull else ((239, 68, 68) if "BEARISH" in bias_l else (245, 158, 11))

    draw.rounded_rectangle((28, 20, 1052, 118), radius=14, fill=(17, 25, 43), outline=(56, 189, 248), width=2)
    draw.text((48, 34), f"FR6 FX  |  XAUUSDm {session_name}", fill=(255, 255, 255), font=f_title)
    draw.text((48, 76), f"{date_label}  |  SPOT: ${smc['live_price']}  |  DXYm: {smc['dxy_now']}", fill=(250, 204, 21), font=f_sub)

    draw.rounded_rectangle((820, 34, 1032, 74), radius=8, fill=bias_col)
    draw.text((838, 43), bias_l, fill=(11, 16, 27), font=f_card_lbl)

    chart = Image.open(chart_png).convert("RGB").resize((1080, 960), Image.Resampling.LANCZOS)
    canvas.paste(chart, (0, 132))

    cards = (
        (28, 356, "SUPPLY OB", str(smc["supply_zone"]), (239, 68, 68), (254, 202, 202)),
        (376, 704, "PRIMARY WATCH ZONE", f"${smc['watch_low']} – ${smc['watch_high']}", (245, 158, 11), (253, 230, 138)),
        (724, 1052, "DEMAND OB", str(smc["demand_zone"]), (6, 182, 212), (165, 243, 252))
    )
    for x1, x2, lbl, val, border_c, val_c in cards:
        draw.rounded_rectangle((x1, 1112, x2, 1228), radius=12, fill=(17, 25, 43), outline=border_c, width=2)
        draw.text((x1 + 16, 1126), lbl, fill=(148, 163, 184), font=f_card_lbl)
        draw.text((x1 + 16, 1164), val, fill=val_c, font=f_card_val)

    canvas.save(out_png)
    print(f"✅ Telegram institutional chart saved: {out_png}")


def render_progressive_reel(smc, session_name, hook_title, spoken_script, out_mp4):
    os.makedirs("assets", exist_ok=True)
    voice_mp3 = "assets/voiceover.mp3"

    asyncio.run(generate_voiceover(spoken_script, voice_mp3))
    voice_dur = get_audio_duration(voice_mp3)
    words = extract_word_captions(voice_mp3)

    total_dur = round(voice_dur + 0.4, 2)
    t2, t3, t4, t5 = detect_stage_timestamps(words, voice_dur)

    sup_int = int(round(float(smc["supply_high"])))
    dem_int = int(round(float(smc["demand_low"])))
    wz_low = int(round(float(smc["watch_low"])))
    wz_high = int(round(float(smc["watch_high"])))

    stages_spec = (
        ("assets/stage_1.png", f"M15 Structure: {smc['struct_dir']}", "assets/frame_1.png", round(t2, 2)),
        ("assets/stage_2.png", f"Supply Resistance: {sup_int}", "assets/frame_2.png", round(t3 - t2, 2)),
        ("assets/stage_3.png", f"Demand Support: {dem_int}", "assets/frame_3.png", round(t4 - t3, 2)),
        ("assets/stage_4.png", f"Watch Zone: {wz_low} – {wz_high}", "assets/frame_4.png", round(t5 - t4, 2)),
        ("assets/stage_5.png", "M5 Confirmation Only • No Chase", "assets/frame_5.png", round(total_dur - t5, 2))
    )

    for st_png, pill, fr_png, _ in stages_spec:
        build_composite_stage_frame(smc, session_name, hook_title, st_png, pill, fr_png)

    # Smooth zoom motion per stage (eliminates static screenshot feel)
    zoom_filters = []
    for idx, (_, _, _, dur) in enumerate(stages_spec):
        frames = max(int(round(dur * 30)), 15)
        zoom_filters.append(
            f"[{idx}:v]scale=1134:2016,zoompan=z='min(zoom+0.0005,1.05)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,setpts=PTS-STARTPTS[v{idx}];"
        )

    filter_parts = "".join(zoom_filters) + "[v0][v1][v2][v3][v4]concat=n=5:v=1:a=0[vbase];"

    # Burned-in animated word-by-word captions
    overlays = render_caption_overlays(words, total_dur)
    inputs = [
        "-i", "assets/frame_1.png",
        "-i", "assets/frame_2.png",
        "-i", "assets/frame_3.png",
        "-i", "assets/frame_4.png",
        "-i", "assets/frame_5.png",
        "-i", voice_mp3
    ]

    last_v = "[vbase]"
    for idx, (cap_png, st_t, en_t) in enumerate(overlays):
        in_idx = 6 + idx
        inputs.extend(["-i", cap_png])
        next_v = f"[vc{idx}]"
        filter_parts += f"{last_v}[{in_idx}:v]overlay=0:0:enable='between(t,{st_t},{en_t})'{next_v};"
        last_v = next_v

    filter_parts += f"[5:a]apad=whole_dur={total_dur}[aout]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_parts,
        "-map", last_v, "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-r", "30", "-c:a", "aac", "-b:a", "192k", "-t", str(total_dur),
        out_mp4
    ]
    subprocess.run(cmd, check=True)
    print(f"🎬 High-Retention Animated Reel exported: {out_mp4}")


def main():
    with open("assets/analysis_output.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    smc = data["smc"]
    session_name = data.get("session", "LONDON SESSION")
    date_label = data.get("date_label", "")
    hook_title = data.get("hook_title", "GOLD LIQUIDITY SETUP")
    spoken_script = data.get("spoken_script", "")

    export_telegram_chart_graphic(
        smc, session_name, date_label, "assets/stage_5.png", "assets/telegram_chart.png"
    )
    render_progressive_reel(
        smc, session_name, hook_title, spoken_script, "assets/final_reel.mp4"
    )


if __name__ == "__main__":
    main()
