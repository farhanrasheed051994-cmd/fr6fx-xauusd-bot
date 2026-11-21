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
    """Aligns Red Supply, Gold 50% Equilibrium & Blue Demand bands strictly inside the main candle pane (above RSI)."""
    overlay = Image.new("RGBA", tv_img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    cw, ch = tv_img.size
    plot_right = cw - 115
    f_zone = ImageFont.truetype(FONT_BOLD, 18)

    sh = float(smc["strong_high"])
    sl = float(smc["strong_low"])
    eq = float(smc["equilibrium"])

    # Keep all zones strictly inside main candlestick pane (Y: 55 to 480, safely above RSI sub-pane)
    span = max(sh - sl, 1.0)
    def price_to_y(p):
        ratio = (sh - p) / span
        return int(max(55, min(480, 60 + ratio * 415)))

    y_res = price_to_y(sh)
    y_eq = price_to_y(eq)
    y_sup = price_to_y(sl)

    # 1. Red Supply / Resistance Zone
    odraw.rectangle([(10, y_res), (plot_right, y_res + 44)], fill=(239, 68, 68, 52))
    odraw.line([(10, y_res), (plot_right, y_res)], fill=(239, 68, 68, 230), width=2)
    odraw.rounded_rectangle([(18, y_res + 6), (315, y_res + 36)], radius=6, fill=(185, 28, 28, 230))
    odraw.text((28, y_res + 11), f"SUPPLY CAP  ${sh}", font=f_zone, fill=(255, 255, 255, 255))

    # 2. Gold 50% Equilibrium Dashed Line
    for x in range(10, plot_right, 22):
        odraw.line([(x, y_eq), (min(x + 12, plot_right), y_eq)], fill=(245, 180, 35, 235), width=3)
    odraw.rounded_rectangle([(18, y_eq - 36), (315, y_eq - 6)], radius=6, fill=(161, 98, 7, 235))
    odraw.text((28, y_eq - 31), f"50% EQ  ${eq}", font=f_zone, fill=(255, 255, 255, 255))

    # 3. Blue Demand / Support Zone (Strictly above RSI divider line)
    odraw.rectangle([(10, y_sup - 44), (plot_right, y_sup)], fill=(59, 130, 246, 56))
    odraw.line([(10, y_sup), (plot_right, y_sup)], fill=(59, 130, 246, 230), width=2)
    odraw.rounded_rectangle([(18, y_sup - 37), (320, y_sup - 7)], radius=6, fill=(29, 78, 216, 230))
    odraw.text((28, y_sup - 32), f"DEMAND FLOOR  ${sl}", font=f_zone, fill=(255, 255, 255, 255))

    return Image.alpha_composite(tv_img, overlay)

def export_telegram_chart(tv_png_path, out_png_path, session_label, smc):
    """Creates a wide, ultra-crisp annotated chart graphic specifically for the FR6 FX Telegram Channel."""
    base = Image.open(tv_png_path).convert("RGBA").resize((1080, 920), Image.Resampling.LANCZOS)
    annotated = draw_live_chart_zones(base, smc)

    canvas = Image.new("RGBA", (1080, 1140), (10, 14, 22, 255))
    draw = ImageDraw.Draw(canvas)

    f_head = ImageFont.truetype(FONT_BOLD, 28)
    f_sub = ImageFont.truetype(FONT_BOLD, 21)
    f_stat = ImageFont.truetype(FONT_BOLD, 20)

    draw.rectangle([(0, 0), (1080, 110)], fill=(16, 22, 34, 255))
    draw.text((35, 22), f"FR6 FX  •  XAUUSD {session_label} MARKUP", font=f_head, fill=(245, 180, 35, 255))
    draw.text((35, 64), f"SPOT: ${smc['live_price']}  |  {smc['bias_label']}  |  DXY: {smc['dxy_now']}  |  PDH: ${smc['pdh']} / PDL: ${smc['pdl']}", font=f_sub, fill=(215, 225, 240, 255))

    canvas.paste(annotated, (0, 110))

    draw.rectangle([(0, 1030), (1080, 1140)], fill=(16, 22, 34, 255))
    draw.text((35, 1048), f"SUPPLY: {smc['supply_zone']}   |   50% EQ: ${smc['equilibrium']}   |   DEMAND: {smc['demand_zone']}", font=f_stat, fill=(255, 255, 255, 255))
    draw.text((35, 1086), f"ASIA: ${smc['asia_low']}-${smc['asia_high']}   |   LONDON: ${smc['london_low']}-${smc['london_high']}   |   @FR6FX", font=f_stat, fill=(148, 163, 184, 255))

    canvas.convert("RGB").save(out_png_path, quality=95)

def build_fr6fx_frame(tv_png_path, out_png_path, session_label, tf_badge, smc, is_recap=False):
    """Builds a locked-scale 1080x1920 FR6 FX mobile layout with zero initial shrinking."""
    W, H = 1080, 1920
    canvas = Image.new("RGBA", (W, H), (9, 12, 18, 255))
    draw = ImageDraw.Draw(canvas)

    for x in range(0, W, 90):
        draw.line([(x, 0), (x, H)], fill=(18, 23, 34, 255), width=1)
    for y in range(0, H, 90):
        draw.line([(0, y), (W, y)], fill=(18, 23, 34, 255), width=1)

    f_brand = ImageFont.truetype(FONT_BOLD, 27)
    f_sub = ImageFont.truetype(FONT_BOLD, 22)
    f_pill_lbl = ImageFont.truetype(FONT_BOLD, 18)
    f_pill_val = ImageFont.truetype(FONT_BOLD, 25)
    f_tg = ImageFont.truetype(FONT_BOLD, 21)
    f_disc = ImageFont.truetype(FONT_REG, 19)

    # 1. Single Clean Session Header Pill (No redundant 2nd line)
    accent = (16, 185, 129, 255) if is_recap else (245, 180, 35, 255)
    draw.rounded_rectangle([(70, 215), (1010, 278)], radius=12, fill=(18, 24, 36, 255), outline=accent, width=2)
    draw.ellipse([(92, 237), (110, 255)], fill=(239, 68, 68, 255))
    draw.text((124, 231), f"FR6 FX  •  {session_label}  [{tf_badge}]", font=f_brand, fill=accent)

    # 2. Sentiment Bias & DXY Macro Bar (Y: 294..340)
    bias_lbl = smc.get("bias_label", "MARKET OUTLOOK")
    bias_col = (52, 211, 153, 255) if "BULLISH" in bias_lbl else ((248, 113, 113, 255) if "BEARISH" in bias_lbl else (252, 211, 77, 255))
    draw.rounded_rectangle([(70, 294), (1010, 340)], radius=8, fill=(20, 27, 40, 255))
    draw.text((86, 304), f"{bias_lbl}  |  DXY: {smc.get('dxy_now', '')}  |  GOLD: ${smc['live_price']}", font=f_sub, fill=bias_col)

    # 3. Authentic TradingView Chart Window (940x800 at Y=356..1156)
    tv_img = Image.open(tv_png_path).convert("RGBA").resize((940, 800), Image.Resampling.LANCZOS)
    if not is_recap:
        tv_img = draw_live_chart_zones(tv_img, smc)

    mask = Image.new("L", (940, 800), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(0, 0), (940, 800)], radius=18, fill=255)
    draw.rounded_rectangle([(68, 354), (1012, 1158)], radius=20, outline=(45, 55, 75, 255), width=3)
    canvas.paste(tv_img, (70, 356), mask)

    # 4. 3 Equal-Width Level Cards (Y: 1176..1266)
    if not is_recap:
        draw.rounded_rectangle([(70, 1176), (370, 1266)], radius=12, fill=(52, 18, 26, 255), outline=(239, 68, 68, 255), width=2)
        draw.text((88, 1188), "SUPPLY CAP", font=f_pill_lbl, fill=(248, 113, 113, 255))
        draw.text((88, 1218), f"${smc['strong_high']}", font=f_pill_val, fill=(255, 255, 255, 255))

        draw.rounded_rectangle([(390, 1176), (690, 1266)], radius=12, fill=(48, 38, 16, 255), outline=(245, 180, 35, 255), width=2)
        draw.text((408, 1188), "50% EQUILIBRIUM", font=f_pill_lbl, fill=(252, 211, 77, 255))
        draw.text((408, 1218), f"${smc['equilibrium']}", font=f_pill_val, fill=(255, 255, 255, 255))

        draw.rounded_rectangle([(710, 1176), (1010, 1266)], radius=12, fill=(16, 36, 58, 255), outline=(59, 130, 246, 255), width=2)
        draw.text((728, 1188), "DEMAND FLOOR", font=f_pill_lbl, fill=(96, 165, 250, 255))
        draw.text((728, 1218), f"${smc['strong_low']}", font=f_pill_val, fill=(255, 255, 255, 255))
    else:
        draw.rounded_rectangle([(70, 1176), (1010, 1266)], radius=12, fill=(14, 48, 38, 255), outline=(16, 185, 129, 255), width=3)
        draw.text((260, 1206), "PREVIOUS LEVEL PLAYED OUT ✅", font=f_brand, fill=(52, 211, 153, 255))

    # 5. Free Telegram Channel Banner & Disclaimer
    tg_link = os.environ.get("TELEGRAM_LINK", "t.me/fr6fx_official").strip()
    draw.rounded_rectangle([(190, 1485), (890, 1532)], radius=10, fill=(16, 38, 56, 255), outline=(56, 189, 248, 255), width=2)
    draw.text((225, 1496), f"FREE TELEGRAM CHARTS & NEWS: {tg_link}", font=f_tg, fill=(125, 211, 252, 255))
    draw.text((215, 1550), "@FR6FX  •  Educational purposes only. Not financial advice.", font=f_disc, fill=(135, 145, 165, 255))

    canvas.convert("RGB").save(out_png_path, quality=95)
async def synthesize_human_voice(spoken_text, raw_mp3, clean_mp3):
    clean_text = re.sub(r"[^\w\s.,!?'-]", " ", str(spoken_text)).strip()
    if not clean_text:
        clean_text = "Gold live session analysis is now ready. Check the key levels on screen."

    voices = ["en-US-AndrewNeural", "en-US-GuyNeural", "en-GB-RyanNeural"]
    edge_success = False

    for v in voices:
        try:
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

    raw_words = []
    for seg in segments:
        for w in seg.words:
            txt = w.word.strip()
            if not txt:
                continue
            if raw_words and (txt.startswith(".") or txt.startswith(",")):
                raw_words[-1]["end"] = w.end
                raw_words[-1]["text"] += txt
            else:
                raw_words.append({"start": w.start, "end": w.end, "text": txt})

    ass_header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,54,&H00FFFFFF,&H00000000,&H99090C12,-1,0,0,0,100,100,0,0,3,14,0,2,80,80,455,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [ass_header]
    for i in range(0, len(raw_words), 3):
        chunk = raw_words[i:i+3]
        first_word = next(iter(chunk))
        last_word = chunk[-1]
        t0 = sec_to_ass(first_word.get("start", 0.0))
        t1 = sec_to_ass(last_word.get("end", 0.0) + 0.08)
        formatted = []
        for item in chunk:
            clean = re.sub(r"[,;!?]+$", "", item.get("text", "")).upper()
            if re.search(r"\d", clean):
                formatted.append(f"{{\\c&H00D7FF&}}{clean}{{\\c&HFFFFFF&}}")
            else:
                formatted.append(clean)
        events.append(f"Dialogue: 0,{t0},{t1},Default,,0,0,0,,{' '.join(formatted)}\n")

    with open(out_ass, "w") as f:
        f.writelines(events)


def compile_video(frame_1, frame_2, audio_mp3, ass_file, output_mp4):
    """Locked 1080x1920 scale with smooth 0.4s crossfade (zero initial chart shrinking)."""
    dur_str = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_mp3
    ]).decode().strip()
    dur = float(dur_str)
    half = dur / 2.0
    fade_offset = max(half - 0.4, 1.0)

    filter_graph = (
        f"[0:v]scale=1080:1920,fps=30,format=yuv420p[v0];"
        f"[1:v]scale=1080:1920,fps=30,format=yuv420p[v1];"
        f"[v0][v1]xfade=transition=fade:duration=0.4:offset={fade_offset}[vcat];"
        f"[vcat]drawbox=x=0:y=1908:w='iw*(t/{dur})':h=12:color=0xF5B423:t=fill[vbar];"
        f"[vbar]ass={ass_file}[vout]"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(half + 0.2), "-i", frame_1,
        "-loop", "1", "-t", str(dur - half + 0.8), "-i", frame_2,
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

    # Export wide annotated chart image for Telegram Channel
    export_telegram_chart("assets/tv_15m.png", "assets/telegram_chart.png", data["session"], smc)

    # Build locked-scale vertical Reel cards
    build_fr6fx_frame("assets/tv_15m.png", "assets/card_15m.png", data["session"], "15M CHART", smc)
    build_fr6fx_frame("assets/tv_5m.png", "assets/card_5m.png", data["session"], "5M CHART", smc)

    await synthesize_human_voice(data["spoken_script"], "assets/v_raw.mp3", "assets/v_clean.mp3")
    build_pop_captions("assets/v_clean.mp3", "assets/subs.ass")
    compile_video("assets/card_15m.png", "assets/card_5m.png", "assets/v_clean.mp3", "assets/subs.ass", "assets/final_reel.mp4")
    print("✅ Locked-scale Reel & Telegram chart compiled.")

    if data.get("recap_enabled") and data.get("recap_spoken_script"):
        with open("predictions.json") as f:
            hist = json.load(f)
        prev = hist[-2] if len(hist) >= 2 else None
        if prev and os.path.exists(prev.get("saved_5m_chart", "")):
            build_fr6fx_frame(prev["saved_5m_chart"], "assets/recap_1.png", "PREVIOUS SETUP", "BEFORE", smc, is_recap=True)
            build_fr6fx_frame("assets/tv_5m.png", "assets/recap_2.png", "LIVE RESULT", "AFTER", smc, is_recap=True)

            await synthesize_human_voice(data["recap_spoken_script"], "assets/rv_raw.mp3", "assets/rv_clean.mp3")
            build_pop_captions("assets/rv_clean.mp3", "assets/rsubs.ass")
            compile_video("assets/recap_1.png", "assets/recap_2.png", "assets/rv_clean.mp3", "assets/rsubs.ass", "assets/recap_reel.mp4")
            print("✅ Bonus Recap Reel compiled.")

if __name__ == "__main__":
    asyncio.run(main())
