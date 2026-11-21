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

def draw_live_chart_zones(tv_img, smc):
    """Aligns Red Resistance, Gold 50% Equilibrium & Blue Support bands proportionally to live price."""
    overlay = Image.new("RGBA", tv_img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    cw, ch = tv_img.size  # 940 x 760
    plot_right = cw - 115
    f_zone = ImageFont.truetype(FONT_BOLD, 18)

    sh = float(smc["strong_high"])
    sl = float(smc["strong_low"])
    eq = float(smc["equilibrium"])
    lp = float(smc["live_price"])

    # Map price range into chart plot area (Y: 60 to 635)
    span = max(sh - sl, 1.0)
    def price_to_y(p):
        ratio = (sh - p) / span
        return int(max(55, min(635, 65 + ratio * 560)))

    y_res = price_to_y(sh)
    y_eq = price_to_y(eq)
    y_sup = price_to_y(sl)

    # 1. Red Resistance Zone
    odraw.rectangle([(10, y_res), (plot_right, y_res + 58)], fill=(239, 68, 68, 52))
    odraw.line([(10, y_res), (plot_right, y_res)], fill=(239, 68, 68, 230), width=2)
    odraw.rounded_rectangle([(18, y_res + 8), (305, y_res + 38)], radius=6, fill=(185, 28, 28, 230))
    odraw.text((28, y_res + 13), f"RESISTANCE  ${sh}", font=f_zone, fill=(255, 255, 255, 255))

    # 2. Gold 50% Equilibrium Dashed Line
    for x in range(10, plot_right, 22):
        odraw.line([(x, y_eq), (min(x + 12, plot_right), y_eq)], fill=(245, 180, 35, 235), width=3)
    odraw.rounded_rectangle([(18, y_eq - 36), (315, y_eq - 6)], radius=6, fill=(161, 98, 7, 235))
    odraw.text((28, y_eq - 31), f"50% EQ  ${eq}", font=f_zone, fill=(255, 255, 255, 255))

    # 3. Blue Support Zone
    odraw.rectangle([(10, y_sup - 58), (plot_right, y_sup)], fill=(59, 130, 246, 56))
    odraw.line([(10, y_sup), (plot_right, y_sup)], fill=(59, 130, 246, 230), width=2)
    odraw.rounded_rectangle([(18, y_sup - 38), (290, y_sup - 8)], radius=6, fill=(29, 78, 216, 230))
    odraw.text((28, y_sup - 33), f"SUPPORT  ${sl}", font=f_zone, fill=(255, 255, 255, 255))

    return Image.alpha_composite(tv_img, overlay)


def build_fr6fx_frame(tv_png_path, out_png_path, session_label, tf_badge, headline_text, smc, is_recap=False):
    """Builds a safe-margined 1080x1920 FR6 FX mobile frame with live chart zones & bias meter."""
    W, H = 1080, 1920
    canvas = Image.new("RGBA", (W, H), (9, 12, 18, 255))
    draw = ImageDraw.Draw(canvas)

    for x in range(0, W, 90):
        draw.line([(x, 0), (x, H)], fill=(18, 23, 34, 255), width=1)
    for y in range(0, H, 90):
        draw.line([(0, y), (W, y)], fill=(18, 23, 34, 255), width=1)

    f_brand = ImageFont.truetype(FONT_BOLD, 25)
    f_head = ImageFont.truetype(FONT_BOLD, 36)
    f_sub = ImageFont.truetype(FONT_BOLD, 21)
    f_pill_lbl = ImageFont.truetype(FONT_BOLD, 18)
    f_pill_val = ImageFont.truetype(FONT_BOLD, 25)
    f_disc = ImageFont.truetype(FONT_REG, 20)

    # Safe horizontal margins: X = 70 to 1010 (940px wide) so mobile UI never clips text
    accent = (16, 185, 129, 255) if is_recap else (245, 180, 35, 255)
    draw.rounded_rectangle([(70, 205), (1010, 265)], radius=12, fill=(18, 24, 36, 255), outline=accent, width=2)
    draw.ellipse([(92, 226), (110, 244)], fill=(239, 68, 68, 255))
    draw.text((124, 221), f"FR6 FX  •  {session_label}  [{tf_badge}]", font=f_brand, fill=accent)

    # Clean Institutional Headline (No cheesy questions)
    clean_head = headline_text.replace("?", "").strip()[:34]
    draw.text((70, 282), clean_head, font=f_head, fill=(255, 255, 255, 255))

    # Sentiment Bias & DXY Macro Bar (Y: 334..376)
    bias_lbl = smc.get("bias_label", "MARKET OUTLOOK")
    bias_col = (52, 211, 153, 255) if "BULLISH" in bias_lbl else ((248, 113, 113, 255) if "BEARISH" in bias_lbl else (252, 211, 77, 255))
    draw.rounded_rectangle([(70, 334), (1010, 376)], radius=8, fill=(20, 27, 40, 255))
    draw.text((86, 343), f"{bias_lbl}  |  DXY: {smc.get('dxy_now', '')}  |  GOLD: ${smc['live_price']}", font=f_sub, fill=bias_col)

    # Authentic TradingView Chart Window with Live Zones Drawn On Top (940x760 at Y=392..1152)
    tv_img = Image.open(tv_png_path).convert("RGBA").resize((940, 760), Image.Resampling.LANCZOS)
    if not is_recap:
        tv_img = draw_live_chart_zones(tv_img, smc)

    mask = Image.new("L", (940, 760), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (940, 760)], radius=18, fill=255)
    draw.rounded_rectangle([(68, 390), (1012, 1154)], radius=20, outline=(45, 55, 75, 255), width=3)
    canvas.paste(tv_img, (70, 392), mask)

    # 3 Equal-Width Level Cards Inside Safe Margins (X: 70..1010, Y: 1172..1262)
    if not is_recap:
        draw.rounded_rectangle([(70, 1172), (370, 1262)], radius=12, fill=(52, 18, 26, 255), outline=(239, 68, 68, 255), width=2)
        draw.text((88, 1184), "RESISTANCE CAP", font=f_pill_lbl, fill=(248, 113, 113, 255))
        draw.text((88, 1214), f"${smc['strong_high']}", font=f_pill_val, fill=(255, 255, 255, 255))

        draw.rounded_rectangle([(390, 1172), (690, 1262)], radius=12, fill=(48, 38, 16, 255), outline=(245, 180, 35, 255), width=2)
        draw.text((408, 1184), "50% EQUILIBRIUM", font=f_pill_lbl, fill=(252, 211, 77, 255))
        draw.text((408, 1214), f"${smc['equilibrium']}", font=f_pill_val, fill=(255, 255, 255, 255))

        draw.rounded_rectangle([(710, 1172), (1010, 1262)], radius=12, fill=(16, 36, 58, 255), outline=(59, 130, 246, 255), width=2)
        draw.text((728, 1184), "SUPPORT FLOOR", font=f_pill_lbl, fill=(96, 165, 250, 255))
        draw.text((728, 1214), f"${smc['strong_low']}", font=f_pill_val, fill=(255, 255, 255, 255))
    else:
        draw.rounded_rectangle([(70, 1172), (1010, 1262)], radius=12, fill=(14, 48, 38, 255), outline=(16, 185, 129, 255), width=3)
        draw.text((260, 1202), "PREVIOUS LEVEL PLAYED OUT ✅", font=f_brand, fill=(52, 211, 153, 255))

    draw.text((210, 1620), "@FR6FX  •  Educational purposes only. Not financial advice.", font=f_disc, fill=(135, 145, 165, 255))
    canvas.convert("RGB").save(out_png_path, quality=95)
async def synthesize_human_voice(spoken_text, raw_mp3, clean_mp3):
    clean_text = re.sub(r"[^\w\s.,!?'-]", " ", str(spoken_text)).strip()
    if not clean_text:
        clean_text = "Gold live session analysis is now ready. Check the key levels on screen."

    voices = ["en-US-AndrewNeural", "en-US-GuyNeural", "en-GB-RyanNeural"]
    edge_success = False

    for v in voices:
        try:
            # Calm, natural human speed (+2% instead of rushed +11%)
            tts = edge_tts.Communicate(clean_text, voice=v, rate="+2%")
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

    # Keep natural pacing (1.03x for gTTS) and trim only long pauses > 0.25s
    tempo_filter = (
        "silenceremove=stop_periods=-1:stop_duration=0.25:stop_threshold=-40dB"
        if edge_success
        else "atempo=1.03,silenceremove=stop_periods=-1:stop_duration=0.25:stop_threshold=-40dB"
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

    # Merge split decimal tokens (e.g., "3621" + ".9") into clean single words
    raw_words = []
    for seg in segments:
        for w in seg.words:
            txt = w.word.strip()
            if not txt:
                continue
            if raw_words and (txt.startswith(".") or txt.startswith(",")):
                prev_s, _, prev_t = raw_words[-1]
                raw_words[-1] = (prev_s, w.end, prev_t + txt)
            else:
                raw_words.append((w.start, w.end, txt))

    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,54,&H00FFFFFF,&H00000000,&H99090C12,-1,0,0,0,100,100,0,0,3,14,0,2,80,80,450,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [ass_header]
    for i in range(0, len(raw_words), 3):
        chunk = raw_words[i:i+3]
        t0 = sec_to_ass(chunk[0][0])
        t1 = sec_to_ass(chunk[-1][1] + 0.08)
        formatted = []
        for _, _, txt in chunk:
            clean = re.sub(r"[,;!?]+$", "", txt).upper()
            if re.search(r"\d", clean):
                formatted.append(f"{{\\c&H00D7FF&}}{clean}{{\\c&HFFFFFF&}}")
            else:
                formatted.append(clean)
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

    # Gentle 1.02x zoom keeps all 70px left/right margins 100% visible inside Reels/Shorts UI
    filter_graph = (
        f"[0:v]scale=1102:1958,zoompan=z='min(zoom+0.0003,1.02)':d={int(half*30)}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30[v0];"
        f"[1:v]scale=1102:1958,zoompan=z='min(zoom+0.0003,1.02)':d={int((dur-half)*30)+15}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30[v1];"
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
    headline = data.get("headline", f"XAUUSD {data['session']} OUTLOOK")

    build_fr6fx_frame("assets/tv_15m.png", "assets/card_15m.png", data["session"], "15M CHART", headline, smc)
    build_fr6fx_frame("assets/tv_5m.png", "assets/card_5m.png", data["session"], "5M CHART", headline, smc)

    await synthesize_human_voice(data["spoken_script"], "assets/v_raw.mp3", "assets/v_clean.mp3")
    build_pop_captions("assets/v_clean.mp3", "assets/subs.ass")
    compile_video("assets/card_15m.png", "assets/card_5m.png", "assets/v_clean.mp3", "assets/subs.ass", "assets/final_reel.mp4")
    print("✅ Upgraded Main Reel compiled: assets/final_reel.mp4")

    if data.get("recap_enabled") and data.get("recap_spoken_script"):
        with open("predictions.json") as f:
            hist = json.load(f)
        prev = hist[-2] if len(hist) >= 2 else None
        if prev and os.path.exists(prev.get("saved_5m_chart", "")):
            build_fr6fx_frame(prev["saved_5m_chart"], "assets/recap_1.png", "PREVIOUS SETUP", "BEFORE", "CALLED BEFORE THE MOVE ✅", smc, is_recap=True)
            build_fr6fx_frame("assets/tv_5m.png", "assets/recap_2.png", "LIVE RESULT", "AFTER", "LEVEL PLAYED OUT ✅", smc, is_recap=True)

            await synthesize_human_voice(data["recap_spoken_script"], "assets/rv_raw.mp3", "assets/rv_clean.mp3")
            build_pop_captions("assets/rv_clean.mp3", "assets/rsubs.ass")
            compile_video("assets/recap_1.png", "assets/recap_2.png", "assets/rv_clean.mp3", "assets/rsubs.ass", "assets/recap_reel.mp4")
            print("✅ Bonus Recap Reel compiled: assets/recap_reel.mp4")

if __name__ == "__main__":
    asyncio.run(main())
