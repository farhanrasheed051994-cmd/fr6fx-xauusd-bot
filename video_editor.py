import os
import re
import json
import asyncio
import subprocess
import edge_tts
from gtts import gTTS
from PIL import Image, ImageDraw, ImageFont
from faster_whisper import WhisperModel

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def build_fr6fx_frame(tv_png_path, out_png_path, session_label, tf_badge, hook_title, smc, is_recap=False):
    W, H = 1080, 1920
    canvas = Image.new("RGBA", (W, H), (9, 12, 18, 255))
    draw = ImageDraw.Draw(canvas)

    for x in range(0, W, 90):
        draw.line([(x, 0), (x, H)], fill=(18, 23, 34, 255), width=1)
    for y in range(0, H, 90):
        draw.line([(0, y), (W, y)], fill=(18, 23, 34, 255), width=1)

    f_brand = ImageFont.truetype(FONT_BOLD, 28)
    f_hook = ImageFont.truetype(FONT_BOLD, 42)
    f_pill_lbl = ImageFont.truetype(FONT_BOLD, 20)
    f_pill_val = ImageFont.truetype(FONT_BOLD, 28)
    f_disc = ImageFont.truetype(FONT_REG, 21)

    accent = (16, 185, 129, 255) if is_recap else (245, 180, 35, 255)
    draw.rounded_rectangle([(50, 210), (1030, 275)], radius=14, fill=(18, 24, 36, 255), outline=accent, width=2)
    draw.ellipse([(75, 233), (95, 253)], fill=(239, 68, 68, 255))
    draw.text((110, 227), f"FR6 FX  •  {session_label}  [{tf_badge}]", font=f_brand, fill=accent)

    draw.text((55, 295), hook_title[:36], font=f_hook, fill=(255, 255, 255, 255))

    tv_img = Image.open(tv_png_path).convert("RGBA").resize((1000, 860), Image.Resampling.LANCZOS)
    mask = Image.new("L", (1000, 860), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (1000, 860)], radius=20, fill=255)

    draw.rounded_rectangle([(38, 363), (1042, 1227)], radius=22, outline=(45, 55, 75, 255), width=3)
    canvas.paste(tv_img, (40, 365), mask)

    if not is_recap:
        draw.rounded_rectangle([(40, 1245), (355, 1345)], radius=14, fill=(52, 18, 26, 255), outline=(239, 68, 68, 255), width=2)
        draw.text((60, 1258), "PREMIUM HIGH", font=f_pill_lbl, fill=(248, 113, 113, 255))
        draw.text((60, 1290), f"${smc['strong_high']}", font=f_pill_val, fill=(255, 255, 255, 255))

        draw.rounded_rectangle([(375, 1245), (705, 1345)], radius=14, fill=(48, 38, 16, 255), outline=(245, 180, 35, 255), width=2)
        draw.text((395, 1258), "50% EQUILIBRIUM", font=f_pill_lbl, fill=(252, 211, 77, 255))
        draw.text((395, 1290), f"${smc['equilibrium']}", font=f_pill_val, fill=(255, 255, 255, 255))

        draw.rounded_rectangle([(725, 1245), (1040, 1345)], radius=14, fill=(16, 36, 58, 255), outline=(59, 130, 246, 255), width=2)
        draw.text((745, 1258), "DISCOUNT LOW", font=f_pill_lbl, fill=(96, 165, 250, 255))
        draw.text((745, 1290), f"${smc['strong_low']}", font=f_pill_val, fill=(255, 255, 255, 255))
    else:
        draw.rounded_rectangle([(40, 1245), (1040, 1345)], radius=14, fill=(14, 48, 38, 255), outline=(16, 185, 129, 255), width=3)
        draw.text((255, 1278), "PREVIOUS SMC LEVEL PLAYED OUT ✅", font=f_brand, fill=(52, 211, 153, 255))

    draw.text((195, 1600), "@FR6FX  •  Educational purposes only. Not financial advice.", font=f_disc, fill=(135, 145, 165, 255))
    canvas.convert("RGB").save(out_png_path, quality=95)
async def synthesize_human_voice(spoken_text, raw_mp3, clean_mp3):
    clean_text = re.sub(r"[^\w\s.,!?'-]", " ", str(spoken_text)).strip()
    if not clean_text:
        clean_text = "Gold live session analysis is now ready. Check the key levels on screen."

    voices = ["en-US-GuyNeural", "en-US-ChristopherNeural", "en-GB-RyanNeural"]
    edge_success = False

    for v in voices:
        try:
            tts = edge_tts.Communicate(clean_text, voice=v, rate="+10%")
            await tts.save(raw_mp3)
            if os.path.exists(raw_mp3) and os.path.getsize(raw_mp3) > 1000:
                edge_success = True
                break
        except Exception as e:
            print(f"⚠️ Edge-TTS {v} skipped: {e}")

    if not edge_success:
        print("🔄 Switching to reliable gTTS fallback...")
        gtts_obj = gTTS(text=clean_text, lang="en", tld="com", slow=False)
        gtts_obj.save(raw_mp3)

    tempo_filter = (
        "silenceremove=stop_periods=-1:stop_duration=0.16:stop_threshold=-40dB"
        if edge_success
        else "atempo=1.12,silenceremove=stop_periods=-1:stop_duration=0.16:stop_threshold=-40dB"
    )

    subprocess.run([
        "ffmpeg", "-y", "-i", raw_mp3,
        "-af", tempo_filter,
        clean_mp3
    ], check=True)

def sec_to_ass(sec):
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int((sec - int(sec)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def build_pop_captions(audio_mp3, out_ass):
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_mp3, word_timestamps=True)

    words = []
    for seg in segments:
        for w in seg.words:
            words.append((w.start, w.end, w.word.strip()))

    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,64,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,2,60,60,410,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [ass_header]
    for i in range(0, len(words), 2):
        pair = words[i:i+2]
        t0 = sec_to_ass(pair[0][0])
        t1 = sec_to_ass(pair[-1][1] + 0.06)
        formatted = []
        for _, _, txt in pair:
            up = txt.upper()
            if re.search(r"\d", up):
                formatted.append(f"{{\\c&H00D7FF&}}{up}{{\\c&HFFFFFF&}}")
            else:
                formatted.append(up)
        events.append(f"Dialogue: 0,{t0},{t1},Default,,0,0,0,,{' '.join(formatted)}\n")

    with open(out_ass, "w") as f:
        f.writelines(events)

def compile_video(frame_1, frame_2, audio_mp3, ass_file, output_mp4):
    dur_str = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_mp3
    ]).decode().strip()
    dur = float(dur_str)
    half = dur / 2.0

    filter_graph = (
        f"[0:v]scale=1166:2074,zoompan=z='min(zoom+0.0007,1.06)':d={int(half*30)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30[v0];"
        f"[1:v]scale=1166:2074,zoompan=z='min(zoom+0.0007,1.06)':d={int((dur-half)*30)+15}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30[v1];"
        f"[v0][v1]concat=n=2:v=1:a=0[vcat];"
        f"[vcat]drawbox=x=0:y=1908:w='iw*(t/{dur})':h=12:color=0xF5B423:t=fill[vbar];"
        f"[vbar]ass={ass_file}[vout]"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(half), "-i", frame_1,
        "-loop", "1", "-t", str(dur - half + 0.5), "-i", frame_2,
        "-i", audio_mp3,
        "-filter_complex", filter_graph,
        "-map", "[vout]", "-map", "2:a",
        "-c:v", "libx264", "-profile:v", "main", "-level", "4.0", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", "-shortest",
        output_mp4
    ], check=True)

async def main():
    with open("assets/analysis_output.json") as f:
        data = json.load(f)

    smc = data["smc"]

    build_fr6fx_frame("assets/tv_15m.png", "assets/card_15m.png", data["session"], "15M CHART", data["hook_banner"], smc)
    build_fr6fx_frame("assets/tv_5m.png", "assets/card_5m.png", data["session"], "5M CHART", data["hook_banner"], smc)

    await synthesize_human_voice(data["spoken_script"], "assets/v_raw.mp3", "assets/v_clean.mp3")
    build_pop_captions("assets/v_clean.mp3", "assets/subs.ass")
    compile_video("assets/card_15m.png", "assets/card_5m.png", "assets/v_clean.mp3", "assets/subs.ass", "assets/final_reel.mp4")
    print("✅ Main Reel compiled: assets/final_reel.mp4")

    if data.get("recap_enabled") and data.get("recap_spoken_script"):
        with open("predictions.json") as f:
            hist = json.load(f)
        prev = hist[-2] if len(hist) >= 2 else None
        if prev and os.path.exists(prev.get("saved_5m_chart", "")):
            build_fr6fx_frame(prev["saved_5m_chart"], "assets/recap_1.png", "PREVIOUS SETUP", "BEFORE", "CALLED BEFORE THE MOVE ✅", smc, is_recap=True)
            build_fr6fx_frame("assets/tv_5m.png", "assets/recap_2.png", "LIVE RESULT", "AFTER", "LEVEL SMASHED TO THE DOLLAR ✅", smc, is_recap=True)

            await synthesize_human_voice(data["recap_spoken_script"], "assets/rv_raw.mp3", "assets/rv_clean.mp3")
            build_pop_captions("assets/rv_clean.mp3", "assets/rsubs.ass")
            compile_video("assets/recap_1.png", "assets/recap_2.png", "assets/rv_clean.mp3", "assets/rsubs.ass", "assets/recap_reel.mp4")
            print("✅ Bonus Recap Reel compiled: assets/recap_reel.mp4")

if __name__ == "__main__":
    asyncio.run(main())
