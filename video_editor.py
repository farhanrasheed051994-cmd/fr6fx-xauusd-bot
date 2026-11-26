import os
import re
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
    tts_text = text.replace("FR6 FX", "F R 6 F X").replace("FR6FX", "F R 6 F X")
    voices = ("en-US-AndrewNeural", "en-US-ChristopherNeural", "en-GB-RyanNeural")
    for v in voices:
        try:
            communicate = edge_tts.Communicate(tts_text, voice=v, rate="+2%")
            await communicate.save(out_mp3)
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 2048:
                print(f"✅ Voiceover saved ({v}): {out_mp3}")
                return
        except Exception as e:
            print(f"⚠️ Edge-TTS {v} failed: {e}")
            await asyncio.sleep(1)

    from gtts import gTTS
    gTTS(text=tts_text, lang="en", tld="com", slow=False).save(out_mp3)


def extract_word_captions(audio_path):
    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, word_timestamps=True)
    raw_words = []
    for seg in segments:
        for w in (seg.words or ()):
            clean_w = w.word.strip().replace(",", "")
            clean_w = re.sub(r"^\.+|\.+$", "", clean_w)
            if clean_w:
                raw_words.append({"word": clean_w, "start": float(w.start), "end": float(w.end)})

    merged = []
    i = 0
    while i < len(raw_words):
        cur = raw_words[i]["word"]
        if (
            i + 1 < len(raw_words)
            and cur.isdigit()
            and len(cur) == 2
            and raw_words[i + 1]["word"].isdigit()
            and len(raw_words[i + 1]["word"]) == 2
        ):
            merged.append({
                "word": cur + raw_words[i + 1]["word"],
                "start": raw_words[i]["start"],
                "end": raw_words[i + 1]["end"]
            })
            i += 2
            continue
        if cur.upper() in ("6FX", "FR6FX", "FR6"):
            cur = "FR6 FX"
        merged.append({"word": cur, "start": raw_words[i]["start"], "end": raw_words[i]["end"]})
        i += 1
    return merged
def detect_stage_timestamps(words, total_dur):
    t2 = round(total_dur * 0.24, 2)
    t3 = round(total_dur * 0.43, 2)
    t4 = round(total_dur * 0.62, 2)
    t5 = round(total_dur * 0.79, 2)

    for i, w in enumerate(words):
        cur = w["word"].lower().strip(".,!?")
        nxt = words[i + 1]["word"].lower().strip(".,!?") if i + 1 < len(words) else ""
        st = float(w["start"])
        if "resist" in cur and 1.8 <= st <= total_dur * 0.48:
            t2 = round(st, 2)
        elif "support" in cur and t2 + 1.2 <= st <= total_dur * 0.66:
            t3 = round(st, 2)
        elif cur == "watch" and "zone" in nxt and t3 + 1.2 <= st <= total_dur * 0.84:
            t4 = round(st, 2)
        elif (cur in ("5", "five") and "minute" in nxt) or cur == "dropping":
            if t4 + 1.2 <= st <= total_dur - 2.0:
                t5 = round(st, 2)

    t2 = max(2.2, min(t2, total_dur - 5.8))
    t3 = max(t2 + 1.6, min(t3, total_dur - 4.2))
    t4 = max(t3 + 1.6, min(t4, total_dur - 2.8))
    t5 = max(t4 + 1.6, min(t5, total_dur - 1.6))
    return (t2, t3, t4, t5)


def render_caption_overlays(words, total_dur):
    os.makedirs("assets/caps", exist_ok=True)
    f_cap = load_font(FONT_BOLD, 44)
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

            pad_x, pad_y = 32, 15
            box_w = min(840, int(total_w + pad_x * 2))
            x_box = int(495 - box_w * 0.5)
            y_box = 1412

            draw.rounded_rectangle(
                (x_box, y_box, x_box + box_w, y_box + 80),
                radius=18, fill=(10, 15, 28, 245), outline=(250, 204, 21, 230), width=3
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


def build_composite_stage_frame(smc, session_name, hook_title, stage_png, out_png, progress_pct=0.0):
    canvas = Image.new("RGB", (1080, 1920), (11, 16, 27))
    draw = ImageDraw.Draw(canvas)

    f_hook = load_font(FONT_BOLD, 42)
    f_meta = load_font(FONT_BOLD, 22)

    hook_clean = str(hook_title).upper()[:22]
    hw = draw.textlength(hook_clean, font=f_hook)
    pill_w = int(hw + 60)
    px1 = int((1080 - pill_w) * 0.5)
    draw.rounded_rectangle((px1, 185, px1 + pill_w, 252), radius=16, fill=(23, 32, 52), outline=(250, 204, 21), width=2)
    draw.text(((1080 - hw) * 0.5, 197), hook_clean, fill=(250, 204, 21), font=f_hook)

    live_p = smc["live_price"]
    bias_l = str(smc["bias_label"])
    draw.text((40, 272), f"{session_name} • {bias_l}", fill=(148, 163, 184), font=f_meta)
    meta_right = f"GOLD ${live_p}"
    rw = draw.textlength(meta_right, font=f_meta)
    draw.text((945 - rw, 272), meta_right, fill=(56, 189, 248), font=f_meta)

    # Full-width 1080x1080 chart (no black gap on right)
    chart = Image.open(stage_png).convert("RGB").resize((1080, 1080), Image.Resampling.LANCZOS)
    canvas.paste(chart, (0, 310))

    # Animated Gold Retention Progress Bar below chart (y=1392)
    draw.rectangle((0, 1392, 1080, 1400), fill=(30, 41, 59))
    bar_w = int(1080 * max(0.05, min(1.0, progress_pct)))
    draw.rectangle((0, 1392, bar_w, 1400), fill=(250, 204, 21))

    canvas.save(out_png)
def export_telegram_chart_graphic(smc, session_name, date_label, chart_png, out_png):
    canvas = Image.new("RGB", (1080, 1340), (11, 16, 27))
    draw = ImageDraw.Draw(canvas)
    f_title = load_font(FONT_BOLD, 25)
    f_sub = load_font(FONT_BOLD, 19)
    f_card_lbl = load_font(FONT_BOLD, 17)
    f_card_val = load_font(FONT_BOLD, 22)

    bias_l = str(smc.get("bias_label", "NEUTRAL"))
    is_bull = "BULLISH" in bias_l
    bias_col = (16, 185, 129) if is_bull else ((239, 68, 68) if "BEARISH" in bias_l else (245, 158, 11))

    draw.rounded_rectangle((28, 20, 1052, 118), radius=14, fill=(17, 25, 43), outline=(56, 189, 248), width=2)
    draw.text((48, 34), f"FR6 FX  |  XAUUSDm {session_name}", fill=(255, 255, 255), font=f_title)
    draw.text((48, 76), f"{date_label}  |  SPOT: ${smc['live_price']}  |  DXYm: {smc['dxy_now']}", fill=(250, 204, 21), font=f_sub)

    draw.rounded_rectangle((820, 34, 1032, 74), radius=8, fill=bias_col)
    draw.text((838, 43), bias_l, fill=(11, 16, 27), font=f_card_lbl)

    chart = Image.open(chart_png).convert("RGB").resize((1080, 1080), Image.Resampling.LANCZOS)
    canvas.paste(chart, (0, 132))

    cards = (
        (28, 356, "SUPPLY RESISTANCE", str(smc["supply_zone"]), (239, 68, 68), (254, 202, 202)),
        (376, 704, "PRIMARY WATCH ZONE", f"${smc['watch_low']} – ${smc['watch_high']}", (245, 158, 11), (253, 230, 138)),
        (724, 1052, "DEMAND SUPPORT", str(smc["demand_zone"]), (6, 182, 212), (165, 243, 252))
    )
    for x1, x2, lbl, val, border_c, val_c in cards:
        draw.rounded_rectangle((x1, 1222, x2, 1324), radius=12, fill=(17, 25, 43), outline=border_c, width=2)
        draw.text((x1 + 16, 1236), lbl, fill=(148, 163, 184), font=f_card_lbl)
        draw.text((x1 + 16, 1272), val, fill=val_c, font=f_card_val)

    canvas.save(out_png)


def render_progressive_reel(smc, session_name, hook_title, spoken_script, out_mp4):
    os.makedirs("assets", exist_ok=True)
    voice_mp3 = "assets/voiceover.mp3"

    asyncio.run(generate_voiceover(spoken_script, voice_mp3))
    voice_dur = get_audio_duration(voice_mp3)
    words = extract_word_captions(voice_mp3)

    total_dur = round(voice_dur + 0.4, 2)
    t2, t3, t4, t5 = detect_stage_timestamps(words, voice_dur)

    s1a = round(t2 * 0.33, 2)
    s1b = round(t2 * 0.33, 2)
    s1c = round(t2 - s1a - s1b, 2)

    d2 = round(t3 - t2, 2)
    s2a = round(d2 * 0.35, 2)
    s2b = round(d2 - s2a, 2)

    d3 = round(t4 - t3, 2)
    s3a = round(d3 * 0.35, 2)
    s3b = round(d3 - s3a, 2)

    d4 = round(t5 - t4, 2)
    s4a = round(d4 * 0.35, 2)
    s4b = round(d4 - s4a, 2)

    d5 = round(total_dur - t5, 2)

    stages_spec = (
        ("assets/stage_1a.png", "assets/frame_1a.png", s1a, 0.08),
        ("assets/stage_1b.png", "assets/frame_1b.png", s1b, 0.16),
        ("assets/stage_1c.png", "assets/frame_1c.png", s1c, 0.24),
        ("assets/stage_2a.png", "assets/frame_2a.png", s2a, 0.33),
        ("assets/stage_2b.png", "assets/frame_2b.png", s2b, 0.43),
        ("assets/stage_3a.png", "assets/frame_3a.png", s3a, 0.52),
        ("assets/stage_3b.png", "assets/frame_3b.png", s3b, 0.62),
        ("assets/stage_4a.png", "assets/frame_4a.png", s4a, 0.71),
        ("assets/stage_4b.png", "assets/frame_4b.png", s4b, 0.80),
        ("assets/stage_5.png", "assets/frame_5.png", d5, 1.00),
    )

    for st_png, fr_png, _, pct in stages_spec:
        build_composite_stage_frame(smc, session_name, hook_title, st_png, fr_png, progress_pct=pct)

    filter_parts = ""
    inputs = []
    for idx, (_, fr_png, dur, _) in enumerate(stages_spec):
        inputs.extend(["-loop", "1", "-i", fr_png])
        filter_parts += f"[{idx}:v]scale=1080:1920,trim=duration={dur},setpts=PTS-STARTPTS[v{idx}];"

    inputs.extend(["-i", voice_mp3])
    audio_idx = len(stages_spec)
    n_stages = len(stages_spec)
    concat_inputs = "".join([f"[v{i}]" for i in range(n_stages)])
    filter_parts += f"{concat_inputs}concat=n={n_stages}:v=1:a=0[vbase];"

    overlays = render_caption_overlays(words, total_dur)
    last_v = "[vbase]"
    for idx, (cap_png, st_t, en_t) in enumerate(overlays):
        in_idx = audio_idx + 1 + idx
        inputs.extend(["-i", cap_png])
        next_v = f"[vc{idx}]"
        filter_parts += f"{last_v}[{in_idx}:v]overlay=0:0:enable='between(t,{st_t},{en_t})'{next_v};"
        last_v = next_v

    filter_parts += f"[{audio_idx}:a]apad=whole_dur={total_dur}[aout]"

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
    print(f"🎬 Dynamic 10-Stage Wide Reel exported: {out_mp4}")


def main():
    with open("assets/analysis_output.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    smc = data["smc"]
    session_name = data.get("session", "LONDON SESSION")
    date_label = data.get("date_label", "")
    hook_title = data.get("hook_title", "GOLD LIQUIDITY MAP")
    spoken_script = data.get("spoken_script", "")

    export_telegram_chart_graphic(
        smc, session_name, date_label, "assets/stage_5.png", "assets/telegram_chart.png"
    )
    render_progressive_reel(
        smc, session_name, hook_title, spoken_script, "assets/final_reel.mp4"
    )


if __name__ == "__main__":
    main()
