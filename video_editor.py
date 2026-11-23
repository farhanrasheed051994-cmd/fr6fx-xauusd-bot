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

    print("🔄 Falling back to Google TTS (gTTS) for guaranteed voiceover...")
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
    print(f"✅ Voiceover saved using gTTS fallback: {out_mp3}")

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

def detect_timeframe_switch_sec(words, total_dur):
    default_switch = round(total_dur * 0.48, 2)
    n_words = len(words)
    for i in range(n_words):
        w_cur = words.__getitem__(i).get("word", "").lower().strip(".,!?")
        w_next = words.__getitem__(i + 1).get("word", "").lower().strip(".,!?") if (i + 1) < n_words else ""
        if (w_cur in ("5", "five") and "minute" in w_next) or w_cur == "dropping":
            t_val = float(words.__getitem__(i).get("start", default_switch))
            if 4.0 <= t_val <= (total_dur - 4.0):
                return round(t_val, 2)
    return default_switch

def format_ass_time(sec):
    s = max(0.0, float(sec))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    rem = s % 60
    return f"{h}:{m:02d}:{rem:05.2f}"
def build_ass_subtitles(words, ass_path, time_offset=0.0):
    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,DejaVu Sans,54,&H00FFFFFF,&H0000D4FF,&H000B101B,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,5,70,70,0,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = list((header,))
    chunk_size = 3
    n_words = len(words)

    for i in range(0, n_words, chunk_size):
        chunk = list()
        for k in range(i, min(i + chunk_size, n_words)):
            chunk.append(words.__getitem__(k))
        if not chunk:
            continue

        for active_idx in range(len(chunk)):
            w_obj = chunk.__getitem__(active_idx)
            st = float(w_obj.get("start")) + time_offset
            if active_idx + 1 < len(chunk):
                en = float(chunk.__getitem__(active_idx + 1).get("start")) + time_offset
            elif (i + chunk_size) < n_words:
                en = float(words.__getitem__(i + chunk_size).get("start")) + time_offset
            else:
                en = float(w_obj.get("end")) + time_offset + 0.35

            if en <= st:
                en = st + 0.12

            styled_parts = list()
            for idx_w in range(len(chunk)):
                txt = str(chunk.__getitem__(idx_w).get("word", "")).upper()
                if idx_w == active_idx:
                    styled_parts.append("{\\c&H0015CCFA&}" + txt + "{\\c&H00FFFFFF&}")
                else:
                    styled_parts.append(txt)

            line_txt = " ".join(styled_parts)
            lines.append(
                f"Dialogue: 0,{format_ass_time(st)},{format_ass_time(en)},Default,,0,0,0,,{{\\pos(540,1475)}}{line_txt}\n"
            )

    with open(ass_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

def draw_header_and_cards(draw, smc, session_name, date_label):
    f_brand = load_font(FONT_BOLD, 30)
    f_meta = load_font(FONT_BOLD, 22)
    f_card_lbl = load_font(FONT_BOLD, 19)
    f_card_val = load_font(FONT_BOLD, 25)
    f_cta = load_font(FONT_BOLD, 24)
    f_disc = load_font(FONT_REG, 17)

    bias_l = str(smc.get("bias_label", "NEUTRAL"))
    is_bull = "BULLISH" in bias_l
    bias_col = (34, 197, 94) if is_bull else ((239, 68, 68) if "BEARISH" in bias_l else (245, 158, 11))

    draw.rounded_rectangle((36, 45, 1044, 208), radius=18, fill=(17, 25, 43), outline=(56, 189, 248), width=2)
    draw.text((62, 64), f"FR6 FX  |  XAUUSD {session_name}", fill=(255, 255, 255), font=f_brand)

    draw.rounded_rectangle((795, 60, 1020, 104), radius=10, fill=bias_col)
    draw.text((818, 70), bias_l, fill=(11, 16, 27), font=f_card_lbl)

    live_p = smc.get("live_price")
    dxy_n = smc.get("dxy_now")
    struct_t = str(smc.get("structure_tag", ""))
    meta_txt = f"SPOT: ${live_p}   |   DXY: {dxy_n}   |   {date_label}"
    draw.text((62, 118), meta_txt, fill=(250, 204, 21), font=f_meta)
    draw.text((62, 158), f"STRUCTURE: {struct_t}", fill=(148, 163, 184), font=f_card_lbl)

    sup_z = str(smc.get("supply_zone", ""))
    eq_v = f"${smc.get('equilibrium')}"
    dem_z = str(smc.get("demand_zone", ""))

    cards = (
        (36, 360, "SUPPLY ZONE", sup_z, (239, 68, 68), (254, 202, 202)),
        (378, 702, "50% EQUILIBRIUM", eq_v, (245, 158, 11), (253, 230, 138)),
        (720, 1044, "DEMAND ZONE", dem_z, (6, 182, 212), (165, 243, 252))
    )
    for x1, x2, lbl, val, border_c, val_c in cards:
        draw.rounded_rectangle((x1, 1245, x2, 1362), radius=14, fill=(17, 25, 43), outline=border_c, width=2)
        draw.text((x1 + 18, 1262), lbl, fill=(148, 163, 184), font=f_card_lbl)
        draw.text((x1 + 18, 1302), val, fill=val_c, font=f_card_val)

    tg_link = (
        os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official")
        .replace("https://", "")
        .replace("http://", "")
        .strip()
    )
    draw.rounded_rectangle((70, 1580, 1010, 1642), radius=31, fill=(14, 165, 233))
    draw.text((135, 1597), f"FREE TELEGRAM CHARTS & NEWS: {tg_link}", fill=(255, 255, 255), font=f_cta)
    draw.text((235, 1656), "@FR6FX  |  Educational analysis only. Not financial advice.", fill=(100, 116, 139), font=f_disc)

def build_background_plate(smc, session_name, date_label, out_png):
    canvas = Image.new("RGB", (1080, 1920), (11, 16, 27))
    draw = ImageDraw.Draw(canvas)
    draw_header_and_cards(draw, smc, session_name, date_label)
    canvas.save(out_png)

def build_viral_cover_frame(smc, session_name, date_label, chart_png, out_png):
    canvas = Image.new("RGB", (1080, 1920), (11, 16, 27))
    draw = ImageDraw.Draw(canvas)
    draw_header_and_cards(draw, smc, session_name, date_label)
    chart = Image.open(chart_png).convert("RGB").resize((1080, 1000), Image.Resampling.LANCZOS)
    canvas.paste(chart, (0, 225))
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
    draw.text((48, 36), f"FR6 FX DESK  |  XAUUSD {session_name} ({date_label})", fill=(255, 255, 255), font=f_title)
    draw.text((48, 78), f"LIVE SPOT: ${smc.get('live_price')}  |  DXY: {smc.get('dxy_now')}  |  {smc.get('structure_tag')}", fill=(250, 204, 21), font=f_sub)

    draw.rounded_rectangle((835, 34, 1032, 74), radius=8, fill=bias_col)
    draw.text((852, 43), bias_l, fill=(11, 16, 27), font=f_card_lbl)

    chart = Image.open(chart_png).convert("RGB").resize((1080, 1000), Image.Resampling.LANCZOS)
    canvas.paste(chart, (0, 134))

    cards = (
        (28, 356, "SUPPLY ZONE", str(smc.get("supply_zone", "")), (239, 68, 68), (254, 202, 202)),
        (376, 704, "50% EQUILIBRIUM", f"${smc.get('equilibrium')}", (245, 158, 11), (253, 230, 138)),
        (724, 1052, "DEMAND ZONE", str(smc.get("demand_zone", "")), (6, 182, 212), (165, 243, 252))
    )
    for x1, x2, lbl, val, border_c, val_c in cards:
        draw.rounded_rectangle((x1, 1148, x2, 1254), radius=12, fill=(17, 25, 43), outline=border_c, width=2)
        draw.text((x1 + 16, 1162), lbl, fill=(148, 163, 184), font=f_card_lbl)
        draw.text((x1 + 16, 1198), val, fill=val_c, font=f_card_val)

    canvas.save(out_png)
    print(f"✅ Telegram institutional chart saved: {out_png}")

def render_vertical_reel(
    smc, session_name, date_label, spoken_script,
    clip_15m, clip_5m, cover_chart_png, out_mp4
):
    os.makedirs("assets", exist_ok=True)
    voice_mp3 = "assets/voiceover.mp3"
    ass_path = "assets/captions.ass"
    plate_png = "assets/bg_plate.png"
    cover_png = "assets/cover_hook.png"

    asyncio.run(generate_voiceover(spoken_script, voice_mp3))
    voice_dur = get_audio_duration(voice_mp3)
    words = extract_word_captions(voice_mp3)

    hook_dur = 0.45
    total_dur = round(voice_dur + hook_dur + 0.4, 2)
    switch_sec = detect_timeframe_switch_sec(words, voice_dur) + hook_dur
    print(f"⏱️ Total Reel Duration: {total_dur}s | 15M -> 5M Cut Synced at: {switch_sec}s")

    build_ass_subtitles(words, ass_path, time_offset=hook_dur)
    build_background_plate(smc, session_name, date_label, plate_png)
    build_viral_cover_frame(smc, session_name, date_label, cover_chart_png, cover_png)

    filter_complex = (
        f"[0:v]scale=1080:1920,trim=duration={total_dur},setpts=PTS-STARTPTS[bg];"
        f"[1:v]scale=1080:1000,loop=-1:size=660:start=0,trim=duration={switch_sec},setpts=PTS-STARTPTS[c15];"
        f"[2:v]scale=1080:1000,loop=-1:size=660:start=0,trim=duration={total_dur - switch_sec},setpts=PTS-STARTPTS[c5];"
        f"[c15][c5]concat=n=2:v=1:a=0[chart];"
        f"[bg][chart]overlay=0:225:shortest=1[with_chart];"
        f"[with_chart]ass={ass_path}[subbed];"
        f"[3:v]scale=1080:1920,trim=duration={hook_dur},setpts=PTS-STARTPTS[hook];"
        f"[subbed][hook]overlay=0:0:enable='between(t,0,{hook_dur})'[vout];"
        f"[4:a]adelay={int(hook_dur * 1000)}|{int(hook_dur * 1000)},apad=whole_dur={total_dur}[aout]"
    )

    cmd = (
        "ffmpeg", "-y",
        "-loop", "1", "-i", plate_png,
        "-i", clip_15m,
        "-i", clip_5m,
        "-loop", "1", "-i", cover_png,
        "-i", voice_mp3,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-r", "30", "-c:a", "aac", "-b:a", "192k", "-t", str(total_dur),
        out_mp4
    )
    subprocess.run(cmd, check=True)
    print(f"🎬 Final 1080x1920 FR6 FX Reel exported: {out_mp4}")

def main():
    with open("assets/analysis_output.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    smc = data.get("smc", {})
    session_name = data.get("session", "LONDON SESSION")
    date_label = data.get("date_label", "")
    spoken_script = data.get("spoken_script", "")

    export_telegram_chart_graphic(
        smc, session_name, date_label, "assets/tv_5m.png", "assets/telegram_chart.png"
    )
    render_vertical_reel(
        smc, session_name, date_label, spoken_script,
        "assets/tv_15m.webm", "assets/tv_5m.webm", "assets/tv_15m.png",
        "assets/final_reel.mp4"
    )

if __name__ == "__main__":
    main()
