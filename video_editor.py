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

def text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box.__getitem__(2) - box.__getitem__(0)

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
    cmd = (
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    )
    res = subprocess.check_output(cmd).decode().strip()
    return max(float(res), 15.0)

def derive_viral_hook(smc, session_name):
    pa = str(smc.get("pa_signal", "")).lower()
    bias = str(smc.get("bias_label", "")).upper()
    if "sweep" in pa and "bearish" in bias.lower():
        return "GOLD LIQUIDITY TRAP", "#ef4444"
    elif "sweep" in pa and "bullish" in bias.lower():
        return "GOLD STOP HUNT", "#00d09c"
    elif "bearish" in bias:
        return "GOLD SUPPLY REJECTION", "#ef4444"
    elif "bullish" in bias:
        return "GOLD DEMAND BOUNCE", "#00d09c"
    first_word = str(session_name).split().__getitem__(0)
    return f"{first_word} GOLD SETUP", "#f59e0b"

def build_viral_cover_frame(smc, session_name, date_label, chart_png_path, out_png):
    img = Image.new("RGB", (W, H), (9, 13, 24))
    draw = ImageDraw.Draw(img)

    f_brand = load_font(FONT_BOLD, 34)
    f_sess = load_font(FONT_BOLD, 29)
    f_hook = load_font(FONT_BOLD, 64)
    f_price = load_font(FONT_BOLD, 34)
    f_card_lbl = load_font(FONT_BOLD, 22)
    f_card_val = load_font(FONT_BOLD, 34)
    f_cta = load_font(FONT_BOLD, 26)

    hook_text, accent_hex = derive_viral_hook(smc, session_name)
    accent_rgb = tuple(int(accent_hex.lstrip("#").__getitem__(slice(i, i + 2)), 16) for i in (0, 2, 4))

    draw.rounded_rectangle((56, 70, W - 56, 152), radius=18, fill=(17, 25, 42), outline=(45, 62, 92), width=3)
    draw.ellipse((86, 97, 114, 125), fill=(245, 158, 11))
    draw.text((135, 92), f"FR6 FX  |  XAUUSD {session_name}", fill=(255, 255, 255), font=f_brand)

    draw.rounded_rectangle((56, 172, W - 56, 344), radius=22, fill=(15, 22, 38), outline=accent_rgb, width=4)
    hw = text_width(draw, hook_text, f_hook)
    draw.text(((W - hw) // 2, 198), hook_text, fill=(255, 255, 255), font=f_hook)

    live_p = smc.get("live_price")
    bias_lbl = smc.get("bias_label")
    sub_line = f"LIVE GOLD: ${live_p}   |   {bias_lbl}   |   {date_label}"
    sw = text_width(draw, sub_line, f_sess)
    draw.text(((W - sw) // 2, 286), sub_line, fill=accent_rgb, font=f_sess)

    draw.rounded_rectangle((54, 368, W - 54, 1244), radius=22, fill=(13, 18, 29), outline=(45, 62, 92), width=3)
    if os.path.exists(chart_png_path):
        c_img = Image.open(chart_png_path).convert("RGB").resize((956, 860), Image.Resampling.LANCZOS)
        img.paste(c_img, (62, 377))

    s_high = smc.get("strong_high")
    eq_val = smc.get("equilibrium")
    s_low = smc.get("strong_low")
    cards = (
        ("SUPPLY ZONE", f"${s_high}", (239, 68, 68), (44, 18, 26)),
        ("50% EQUILIBRIUM", f"${eq_val}", (245, 158, 11), (42, 32, 16)),
        ("DEMAND ZONE", f"${s_low}", (6, 182, 212), (14, 38, 48)),
    )
    card_w = 304
    for idx, (lbl, val, col, bg) in enumerate(cards):
        cx = 56 + idx * 332
        cy = 1272
        draw.rounded_rectangle((cx, cy, cx + card_w, cy + 125), radius=18, fill=bg, outline=col, width=3)
        draw.text((cx + 22, cy + 20), lbl, fill=col, font=f_card_lbl)
        draw.text((cx + 22, cy + 58), val, fill=(255, 255, 255), font=f_card_val)

    draw.rounded_rectangle((120, 1435, W - 120, 1515), radius=40, fill=accent_rgb)
    badge_txt = "WATCH LIVE INSTITUTIONAL ZONES"
    bw = text_width(draw, badge_txt, f_price)
    draw.text(((W - bw) // 2, 1456), badge_txt, fill=(10, 14, 24), font=f_price)

    tg_link = os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official").replace("https://", "").strip()
    draw.rounded_rectangle((56, 1545, W - 56, 1622), radius=14, fill=(18, 28, 46), outline=(56, 189, 248), width=2)
    cta = f"FREE TELEGRAM CHARTS & NEWS: {tg_link}"
    cw = text_width(draw, cta, f_cta)
    draw.text(((W - cw) // 2, 1570), cta, fill=(224, 242, 254), font=f_cta)

    img.save(out_png)
def build_background_plate(smc, session_name, date_label, out_png):
    img = Image.new("RGB", (W, H), (9, 13, 24))
    draw = ImageDraw.Draw(img)

    f_title = load_font(FONT_BOLD, 34)
    f_sub = load_font(FONT_BOLD, 24)
    f_lbl = load_font(FONT_BOLD, 20)
    f_val = load_font(FONT_BOLD, 31)
    f_cta = load_font(FONT_BOLD, 24)
    f_foot = load_font(FONT_REG, 19)

    bias_str = str(smc.get("bias_label", "NEUTRAL")).upper()
    bias_col = (0, 208, 156) if "BULLISH" in bias_str else ((239, 68, 68) if "BEARISH" in bias_str else (245, 158, 11))

    draw.rounded_rectangle((56, 68, W - 56, 232), radius=20, fill=(16, 24, 41), outline=(45, 62, 92), width=2)
    draw.ellipse((84, 94, 110, 120), fill=(245, 158, 11))
    draw.text((130, 88), f"FR6 FX  |  {session_name} (LIVE SMC CHART)", fill=(255, 255, 255), font=f_title)

    dxy_val = smc.get("dxy_now")
    live_p = smc.get("live_price")
    sub = f"{bias_str}   |   DXY: {dxy_val}   |   GOLD: ${live_p}"
    draw.text((84, 162), sub, fill=bias_col, font=f_sub)

    draw.rounded_rectangle((54, 254, W - 54, 1126), radius=20, fill=(13, 18, 29), outline=(45, 62, 92), width=2)

    s_high = smc.get("strong_high")
    eq_val = smc.get("equilibrium")
    s_low = smc.get("strong_low")
    cards = (
        ("SUPPLY CAP", f"${s_high}", (239, 68, 68), (44, 18, 26)),
        ("50% EQUILIBRIUM", f"${eq_val}", (245, 158, 11), (42, 32, 16)),
        ("DEMAND FLOOR", f"${s_low}", (6, 182, 212), (14, 38, 48)),
    )
    card_w = 304
    for idx, (lbl, val, col, bg) in enumerate(cards):
        cx = 56 + idx * 332
        cy = 1148
        draw.rounded_rectangle((cx, cy, cx + card_w, cy + 114), radius=16, fill=bg, outline=col, width=2)
        draw.text((cx + 20, cy + 16), lbl, fill=col, font=f_lbl)
        draw.text((cx + 20, cy + 52), val, fill=(255, 255, 255), font=f_val)

    tg_link = os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official").replace("https://", "").strip()
    draw.rounded_rectangle((56, 1484, W - 56, 1556), radius=14, fill=(18, 28, 46), outline=(56, 189, 248), width=2)
    cta = f"FREE TELEGRAM CHARTS & NEWS: {tg_link}"
    cw = text_width(draw, cta, f_cta)
    draw.text(((W - cw) // 2, 1506), cta, fill=(224, 242, 254), font=f_cta)

    foot = f"@FR6FX  |  {date_label}  |  Educational purposes only. Not financial advice."
    fw = text_width(draw, foot, f_foot)
    draw.text(((W - fw) // 2, 1580), foot, fill=(148, 163, 184), font=f_foot)

    img.save(out_png)

def fmt_ass_time(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"

def build_ass_subtitles(words, out_ass, time_offset=0.0):
    header = (
        "Script Info\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n\n"
        "V4+ Styles\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,DejaVu Sans,52,&H00FFFFFF,&H0000D7FF,&H00090D18,&H80000000,-1,0,0,0,100,100,0,0,1,4,0,2,60,60,500,1\n\n"
        "Events\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = list()
    chunk_size = 3
    for i in range(0, len(words), chunk_size):
        chunk = list(words).__getitem__(slice(i, i + chunk_size))
        if not chunk:
            continue
        t_start = fmt_ass_time(chunk.__getitem__(0).get("start") + time_offset)
        t_end = fmt_ass_time(chunk.__getitem__(len(chunk) - 1).get("end") + time_offset + 0.08)
        rendered_words = list()
        for idx, item in enumerate(chunk):
            w_txt = item.get("word")
            if idx == len(chunk) - 1:
                rendered_words.append(f"{{\\c&H0015CCFA&}}{w_txt}{{\\c&H00FFFFFF&}}")
            else:
                rendered_words.append(w_txt)
        line_str = " ".join(rendered_words)
        lines.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{line_str}")

    with open(out_ass, "w", encoding="utf-8") as f:
        f.write(header.replace("Script Info", "[Script Info]").replace("V4+ Styles", "[V4+ Styles]").replace("Events", "[Events]"))
        f.write("\n".join(lines) + "\n")
def export_telegram_chart(smc, session_name, date_label, out_png):
    base_chart = "assets/tv_5m.png" if os.path.exists("assets/tv_5m.png") else "assets/tv_15m.png"
    chart = Image.open(base_chart).convert("RGB").resize((1200, 1075), Image.Resampling.LANCZOS)

    canvas = Image.new("RGB", (1200, 1230), (11, 16, 27))
    draw = ImageDraw.Draw(canvas)
    f_hdr = load_font(FONT_BOLD, 30)
    f_sub = load_font(FONT_BOLD, 21)

    draw.rounded_rectangle((20, 16, 1180, 134), radius=16, fill=(18, 27, 46), outline=(56, 189, 248), width=2)
    draw.text((44, 30), f"FR6 FX INSTITUTIONAL DESK  |  XAUUSD {session_name} ({date_label})", fill=(255, 255, 255), font=f_hdr)

    sup_z = smc.get("supply_zone")
    eq_v = smc.get("equilibrium")
    dem_z = smc.get("demand_zone")
    sub = f"Supply: {sup_z}   |   50% EQ: ${eq_v}   |   Demand: {dem_z}"
    draw.text((44, 82), sub, fill=(250, 204, 21), font=f_sub)

    canvas.paste(chart, (0, 150))
    canvas.save(out_png)
    print(f"✅ Clean Telegram chart exported: {out_png}")

def render_reel_video(
    voice_mp3,
    ass_path,
    cover_png,
    bg_png,
    clip_15m,
    clip_5m,
    out_mp4,
    total_dur,
    cover_dur=0.45
):
    body_dur = max(total_dur, 16.0)
    half_dur = round(body_dur / 2.0, 2)
    body_mp4 = out_mp4.replace(".mp4", "_body.mp4")
    cover_mp4 = out_mp4.replace(".mp4", "_cover.mp4")

    cmd_cover = (
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(cover_dur), "-i", cover_png,
        "-f", "lavfi", "-t", str(cover_dur), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-vf", "scale=1080:1920,fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-shortest", cover_mp4
    )
    subprocess.run(cmd_cover, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    filter_complex = (
        "1:v]setpts=PTS-STARTPTS,scale=960:860,fps=30[v15];"
        "2:v]setpts=PTS-STARTPTS,scale=960:860,fps=30[v5];"
        "v15][v5]concat=n=2:v=1:a=0[chart];"
        "0:v][chart]overlay=60:260:shortest=1[bgchart];"
        f"bgchart]subtitles={ass_path},fps=30,format=yuv420p[vout]"
    )
    fc_fixed = (
        filter_complex
        .replace("1:v]", "[1:v]")
        .replace("2:v]", "[2:v]")
        .replace("v15][v5]", "[v15][v5]")
        .replace("0:v][chart]", "[0:v][chart]")
        .replace("bgchart]subtitles", "[bgchart]subtitles")
    )

    cmd_body = (
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(body_dur), "-i", bg_png,
        "-stream_loop", "-1", "-t", str(half_dur), "-i", clip_15m,
        "-stream_loop", "-1", "-t", str(body_dur - half_dur + 0.5), "-i", clip_5m,
        "-i", voice_mp3,
        "-filter_complex", fc_fixed,
        "-map", "[vout]", "-map", "3:a",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-t", str(body_dur), body_mp4
    )
    subprocess.run(cmd_body, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    concat_txt = out_mp4.replace(".mp4", "_concat.txt")
    with open(concat_txt, "w") as f:
        f.write(f"file '{os.path.abspath(cover_mp4)}'\n")
        f.write(f"file '{os.path.abspath(body_mp4)}'\n")

    cmd_final = (
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_txt,
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        out_mp4
    )
    subprocess.run(cmd_final, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"✅ Viral Reel rendered with 44.1kHz stereo audio & full-height candles: {out_mp4}")

async def main():
    with open("assets/analysis_output.json", "r") as f:
        data = json.load(f)

    smc = data.get("smc")
    session_name = data.get("session")
    date_label = data.get("date_label")
    spoken_script = data.get("spoken_script")

    export_telegram_chart(smc, session_name, date_label, "assets/telegram_chart.png")

    cover_png = "assets/viral_cover.png"
    bg_png = "assets/bg_plate.png"
    chart_preview = "assets/tv_5m.png" if os.path.exists("assets/tv_5m.png") else "assets/tv_15m.png"
    build_viral_cover_frame(smc, session_name, date_label, chart_preview, cover_png)
    build_background_plate(smc, session_name, date_label, bg_png)

    voice_mp3 = "assets/voice_main.mp3"
    await generate_voiceover(spoken_script, voice_mp3)
    dur = get_audio_duration(voice_mp3) + 0.6

    words = extract_word_captions(voice_mp3)
    ass_path = "assets/captions_main.ass"
    build_ass_subtitles(words, ass_path, time_offset=0.0)

    clip_15m = "assets/tv_15m.webm"
    clip_5m = "assets/tv_5m.webm" if os.path.exists("assets/tv_5m.webm") else clip_15m
    render_reel_video(
        voice_mp3, ass_path, cover_png, bg_png,
        clip_15m, clip_5m, "assets/final_reel.mp4", dur, cover_dur=0.45
    )

    if data.get("recap_enabled") and data.get("recap_spoken_script"):
        recap_mp3 = "assets/voice_recap.mp3"
        await generate_voiceover(data.get("recap_spoken_script"), recap_mp3)
        rdur = get_audio_duration(recap_mp3) + 0.6
        rwords = extract_word_captions(recap_mp3)
        rass = "assets/captions_recap.ass"
        build_ass_subtitles(rwords, rass, time_offset=0.0)
        render_reel_video(
            recap_mp3, rass, cover_png, bg_png,
            clip_5m, clip_15m, "assets/bonus_recap_reel.mp4", rdur, cover_dur=0.45
        )

if __name__ == "__main__":
    asyncio.run(main())
