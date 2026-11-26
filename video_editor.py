import os
import json
import asyncio
import subprocess
import edge_tts
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw, ImageFont

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


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
    return float(subprocess.check_output(cmd).decode().strip())


async def generate_voiceover(text, out_mp3):
    voices = ("en-US-AndrewNeural", "en-US-ChristopherNeural", "en-GB-RyanNeural")
    for v in voices:
        try:
            communicate = edge_tts.Communicate(text, voice=v, rate="+0%")
            await communicate.save(out_mp3)
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 2048:
                print(f"✅ Voiceover saved ({v}): {out_mp3}")
                return
        except Exception as e:
            print(f"⚠️ Edge-TTS {v} failed: {e}")
            await asyncio.sleep(1)

    from gtts import gTTS
    tts = gTTS(text=text, lang="en", tld="com", slow=False)
    tts.save(out_mp3)


def extract_word_captions(audio_path):
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, word_timestamps=True)
    words = []
    for seg in segments:
        for w in (seg.words or ()):
            clean_w = w.word.strip()
            if clean_w:
                words.append({"word": clean_w, "start": float(w.start), "end": float(w.end)})
    return words


def detect_stage_timestamps(words, total_dur):
    t2 = round(total_dur * 0.22, 2)
    t3 = round(total_dur * 0.40, 2)
    t4 = round(total_dur * 0.58, 2)
    t5 = round(total_dur * 0.76, 2)

    for i, w in enumerate(words):
        cur = w["word"].lower().strip(".,!?")
        nxt = words[i + 1]["word"].lower().strip(".,!?") if i + 1 < len(words) else ""
        st = float(w["start"])
        if "resist" in cur and 1.2 <= st <= total_dur * 0.48:
            t2 = round(st, 2)
        elif "support" in cur and t2 + 1.0 <= st <= total_dur * 0.66:
            t3 = round(st, 2)
        elif cur == "watch" and "zone" in nxt and t3 + 1.0 <= st <= total_dur * 0.82:
            t4 = round(st, 2)
        elif (cur in ("5", "five") and "minute" in nxt) or cur == "dropping":
            if t4 + 1.0 <= st <= total_dur - 2.0:
                t5 = round(st, 2)

    t2 = max(1.5, min(t2, total_dur - 5.5))
    t3 = max(t2 + 1.5, min(t3, total_dur - 4.0))
    t4 = max(t3 + 1.5, min(t4, total_dur - 2.8))
    t5 = max(t4 + 1.5, min(t5, total_dur - 1.6))
    return (t2, t3, t4, t5)
def render_caption_overlays(words, total_dur):
    os.makedirs("assets/caps", exist_ok=True)
    f_cap = load_font(FONT_BOLD, 48)
    overlays = []

    for idx in range(0, len(words), 3):
        chunk = words[idx : idx + 3]
        for active_i, active_w in enumerate(chunk):
            start_t = round(active_w["start"], 2)
            if active_i + 1 < len(chunk):
                end_t = round(chunk[active_i + 1]["start"], 2)
            elif idx + 3 < len(words):
                end_t = round(words[idx + 3]["start"], 2)
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

            pad_x, pad_y = 36, 18
            box_w = min(980, int(total_w + pad_x * 2))
            x_box = int((1080 - box_w) * 0.5)
            y_box = 1380

            draw.rounded_rectangle(
                (x_box, y_box, x_box + box_w, y_box + 88),
                radius=20, fill=(10, 15, 28, 245), outline=(250, 204, 21, 230), width=3
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


def build_composite_stage_frame(smc, session_name, hook_title, stage_png, out_png):
    canvas = Image.new("RGB", (1080, 1920), (11, 15, 23))
    draw = ImageDraw.Draw(canvas)

    f_hook = load_font(FONT_BOLD, 44)
    f_meta = load_font(FONT_BOLD, 24)

    # Mobile-safe top hook badge (strictly <=22 chars so YT/IG top icons never overlap)
    hook_clean = str(hook_title).upper()[:22]
    hw = draw.textlength(hook_clean, font=f_hook)
    pill_w = int(hw + 68)
    px1 = int((1080 - pill_w) * 0.5)
    draw.rounded_rectangle((px1, 195, px1 + pill_w, 265), radius=16, fill=(23, 32, 52), outline=(250, 204, 21), width=2)
    draw.text(((1080 - hw) * 0.5, 208), hook_clean, fill=(250, 204, 21), font=f_hook)

    # Session & Spot Strip
    live_p = smc["live_price"]
    bias_l = str(smc["bias_label"])
    draw.text((48, 282), f"{session_name}  •  {bias_l}", fill=(148, 163, 184), font=f_meta)
    meta_right = f"XAUUSD ${live_p}"
    rw = draw.textlength(meta_right, font=f_meta)
    draw.text((1032 - rw, 282), meta_right, fill=(56, 189, 248), font=f_meta)

    # Full-width 1080x1040 Mobile-Optimized Chart (y=320 to y=1360)
    chart = Image.open(stage_png).convert("RGB").resize((1080, 1040), Image.Resampling.LANCZOS)
    canvas.paste(chart, (0, 320))

    canvas.save(out_png)


def export_telegram_chart_graphic(smc, session_name, date_label, chart_png, out_png):
    canvas = Image.new("RGB", (1080, 1320), (11, 16, 27))
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

    chart = Image.open(chart_png).convert("RGB").resize((1080, 1040), Image.Resampling.LANCZOS)
    canvas.paste(chart, (0, 132))

    cards = (
        (28, 356, "SUPPLY RESISTANCE", str(smc["supply_zone"]), (239, 68, 68), (254, 202, 202)),
        (376, 704, "PRIMARY WATCH ZONE", f"${smc['watch_low']} – ${smc['watch_high']}", (245, 158, 11), (253, 230, 138)),
        (724, 1052, "DEMAND SUPPORT", str(smc["demand_zone"]), (6, 182, 212), (165, 243, 252))
    )
    for x1, x2, lbl, val, border_c, val_c in cards:
        draw.rounded_rectangle((x1, 1188, x2, 1298), radius=12, fill=(17, 25, 43), outline=border_c, width=2)
        draw.text((x1 + 16, 1202), lbl, fill=(148, 163, 184), font=f_card_lbl)
        draw.text((x1 + 16, 1238), val, fill=val_c, font=f_card_val)

    canvas.save(out_png)


def render_progressive_reel(smc, session_name, hook_title, spoken_script, out_mp4):
    os.makedirs("assets", exist_ok=True)
    voice_mp3 = "assets/voiceover.mp3"

    asyncio.run(generate_voiceover(spoken_script, voice_mp3))
    voice_dur = get_audio_duration(voice_mp3)
    words = extract_word_captions(voice_mp3)

    total_dur = round(voice_dur + 0.4, 2)
    t2, t3, t4, t5 = detect_stage_timestamps(words, voice_dur)

    stages_spec = (
        ("assets/stage_1.png", "assets/frame_1.png", round(t2, 2)),
        ("assets/stage_2.png", "assets/frame_2.png", round(t3 - t2, 2)),
        ("assets/stage_3.png", "assets/frame_3.png", round(t4 - t3, 2)),
        ("assets/stage_4.png", "assets/frame_4.png", round(t5 - t4, 2)),
        ("assets/stage_5.png", "assets/frame_5.png", round(total_dur - t5, 2)),
    )

    for st_png, fr_png, _ in stages_spec:
        build_composite_stage_frame(smc, session_name, hook_title, st_png, fr_png)

    d1, d2, d3, d4, d5 = [s for s in stages_spec]
    filter_parts = (
        f"[0:v]scale=1080:1920,trim=duration={d1},setpts=PTS-STARTPTS[v0];"
        f"[1:v]scale=1080:1920,trim=duration={d2},setpts=PTS-STARTPTS[v1];"
        f"[2:v]scale=1080:1920,trim=duration={d3},setpts=PTS-STARTPTS[v2];"
        f"[3:v]scale=1080:1920,trim=duration={d4},setpts=PTS-STARTPTS[v3];"
        f"[4:v]scale=1080:1920,trim=duration={d5},setpts=PTS-STARTPTS[v4];"
        f"[v0][v1][v2][v3][v4]concat=n=5:v=1:a=0[vbase];"
    )

    overlays = render_caption_overlays(words, total_dur)
    inputs = [
        "-loop", "1", "-i", "assets/frame_1.png",
        "-loop", "1", "-i", "assets/frame_2.png",
        "-loop", "1", "-i", "assets/frame_3.png",
        "-loop", "1", "-i", "assets/frame_4.png",
        "-loop", "1", "-i", "assets/frame_5.png",
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
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", "30", "-c:a", "aac", "-b:a", "192k", "-t", str(total_dur),
        out_mp4
    ]
    subprocess.run(cmd, check=True)
    print(f"🎬 Mobile-Optimized Reel exported: {out_mp4}")


def main():
    with open("assets/analysis_output.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    smc = data["smc"]
    session_name = data.get("session", "LONDON SESSION")
    date_label = data.get("date_label", "")
    hook_title = data.get("hook_title", "GOLD KEY LEVELS")
    spoken_script = data.get("spoken_script", "")

    export_telegram_chart_graphic(
        smc, session_name, date_label, "assets/stage_5.png", "assets/telegram_chart.png"
    )
    render_progressive_reel(
        smc, session_name, hook_title, spoken_script, "assets/final_reel.mp4"
    )


if __name__ == "__main__":
    main()
