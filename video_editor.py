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

def calc_zone_y(smc):
    """Calculates Y positions strictly inside the main candlestick pane (above RSI)."""
    sh = float(smc["strong_high"])
    sl = float(smc["strong_low"])
    eq = float(smc["equilibrium"])
    span = max(sh - sl, 1.0)

    def price_to_y(p):
        ratio = (sh - p) / span
        return int(max(55, min(480, 60 + ratio * 415)))

    return price_to_y(sh), price_to_y(eq), price_to_y(sl)

def create_zone_layer_pngs(smc):
    """Generates individual 940x800 transparent RGBA overlays for animated live drawing."""
    W, H = 940, 800
    plot_right = W - 115
    f_zone = ImageFont.truetype(FONT_BOLD, 18)
    y_res, y_eq, y_sup = calc_zone_y(smc)

    # 1. Red Supply Zone PNG
    img_sup = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d1 = ImageDraw.Draw(img_sup)
    d1.rectangle([(10, y_res), (plot_right, y_res + 44)], fill=(239, 68, 68, 56))
    d1.line([(10, y_res), (plot_right, y_res)], fill=(239, 68, 68, 235), width=2)
    d1.rounded_rectangle([(18, y_res + 6), (315, y_res + 36)], radius=6, fill=(185, 28, 28, 235))
    d1.text((28, y_res + 11), f"SUPPLY CAP  ${smc['strong_high']}", font=f_zone, fill=(255, 255, 255, 255))
    img_sup.save("assets/layer_supply.png")

    # 2. Gold 50% Equilibrium Line PNG
    img_eq = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d2 = ImageDraw.Draw(img_eq)
    for x in range(10, plot_right, 22):
        d2.line([(x, y_eq), (min(x + 12, plot_right), y_eq)], fill=(245, 180, 35, 240), width=3)
    d2.rounded_rectangle([(18, y_eq - 36), (315, y_eq - 6)], radius=6, fill=(161, 98, 7, 240))
    d2.text((28, y_eq - 31), f"50% EQ  ${smc['equilibrium']}", font=f_zone, fill=(255, 255, 255, 255))
    img_eq.save("assets/layer_eq.png")

    # 3. Blue Demand Zone PNG
    img_dem = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d3 = ImageDraw.Draw(img_dem)
    d3.rectangle([(10, y_sup - 44), (plot_right, y_sup)], fill=(59, 130, 246, 60))
    d3.line([(10, y_sup), (plot_right, y_sup)], fill=(59, 130, 246, 235), width=2)
    d3.rounded_rectangle([(18, y_sup - 37), (320, y_sup - 7)], radius=6, fill=(29, 78, 216, 235))
    d3.text((28, y_sup - 32), f"DEMAND FLOOR  ${smc['strong_low']}", font=f_zone, fill=(255, 255, 255, 255))
    img_dem.save("assets/layer_demand.png")

def export_telegram_chart(tv_png_path, out_png_path, session_label, smc):
    """Creates the high-res annotated chart graphic for the FR6 FX Telegram Channel."""
    base = Image.open(tv_png_path).convert("RGBA").resize((940, 800), Image.Resampling.LANCZOS)
    for layer_path in ("assets/layer_supply.png", "assets/layer_eq.png", "assets/layer_demand.png"):
        base = Image.alpha_composite(base, Image.open(layer_path).convert("RGBA"))
    annotated = base.resize((1080, 920), Image.Resampling.LANCZOS)

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

def build_background_frame(out_png_path, session_label, smc, is_recap=False):
    """Builds the 1080x1920 FR6 FX outer frame with a cutout window at (70, 356, 940x800) for the live video."""
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

    accent = (16, 185, 129, 255) if is_recap else (245, 180, 35, 255)
    draw.rounded_rectangle([(70, 215), (1010, 278)], radius=12, fill=(18, 24, 36, 255), outline=accent, width=2)
    draw.ellipse([(92, 237), (110, 255)], fill=(239, 68, 68, 255))
    draw.text((124, 231), f"FR6 FX  •  {session_label}  [LIVE CHART]", font=f_brand, fill=accent)

    bias_lbl = smc.get("bias_label", "MARKET OUTLOOK")
    bias_col = (52, 211, 153, 255) if "BULLISH" in bias_lbl else ((248, 113, 113, 255) if "BEARISH" in bias_lbl else (252, 211, 77, 255))
    draw.rounded_rectangle([(70, 294), (1010, 340)], radius=8, fill=(20, 27, 40, 255))
    draw.text((86, 304), f"{bias_lbl}  |  DXY: {smc.get('dxy_now', '')}  |  GOLD: ${smc['live_price']}", font=f_sub, fill=bias_col)

    # Border around live chart video slot (70, 356, 940x800)
    draw.rounded_rectangle([(67, 353), (1013, 1159)], radius=18, outline=(45, 55, 75, 255), width=3)

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

def build_pop_captions_and_cues(audio_mp3, out_ass):
    """Builds clean captions AND detects exact voiceover timestamps to draw Supply, EQ & Demand zones live."""
    model = WhisperModel("tiny", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_mp3, word_timestamps=True)

    raw_words = []
    t_supply = None
    t_eq = None
    t_demand = None

    for seg in segments:
        for w in seg.words:
            txt = w.word.strip()
            if not txt:
                continue
            low = txt.lower()
            if t_supply is None and any(k in low for k in ("supply", "resistance", "cap")):
                t_supply = round(max(w.start - 0.15, 1.5), 2)
            if t_eq is None and any(k in low for k in ("equilibrium", "fifty", "pivot", "mid")):
                t_eq = round(max(w.start - 0.15, 3.0), 2)
            if t_demand is None and any(k in low for k in ("demand", "support", "floor")):
                t_demand = round(max(w.start - 0.15, 4.5), 2)

            if raw_words and (txt.startswith(".") or txt.startswith(",")):
                raw_words[-1]["end"] = w.end
                raw_words[-1]["text"] += txt
            else:
                raw_words.append({"start": w.start, "end": w.end, "text": txt})

    # Fallback cue timestamps if any keyword wasn't caught verbatim
    t_supply = t_supply if t_supply is not None else 6.0
    t_eq = t_eq if t_eq is not None else 11.0
    t_demand = t_demand if t_demand is not None else 16.0

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

    return t_supply, t_eq, t_demand

def compile_live_video(bg_png, vid_15m, vid_5m, audio_mp3, ass_file, cues, output_mp4):
    """Composites live moving 15M->5M TradingView video + voice-synced animated zone wipes."""
    dur_str = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_mp3
    ]).decode().strip()
    dur = float(dur_str)
    half = dur / 2.0
    t_sup, t_eq, t_dem = cues

    # Smooth 0.7s left-to-right wipe expression for each zone layer at (X=70, Y=356)
    wipe_sup = f"if(lt(t,{t_sup}),-940,min(70,-940+((t-{t_sup})/0.7)*1010))"
    wipe_eq = f"if(lt(t,{t_eq}),-940,min(70,-940+((t-{t_eq})/0.7)*1010))"
    wipe_dem = f"if(lt(t,{t_dem}),-940,min(70,-940+((t-{t_dem})/0.7)*1010))"

    filter_graph = (
        f"[0:v]scale=1080:1920,fps=30,format=rgba[bg];"
        f"[1:v]scale=940:800,fps=30,trim=duration={half},setpts=PTS-STARTPTS[c15];"
        f"[2:v]scale=940:800,fps=30,trim=duration={dur - half + 0.5},setpts=PTS-STARTPTS[c5];"
        f"[c15][c5]concat=n=2:v=1:a=0,format=rgba[chart];"
        f"[bg][chart]overlay=x=70:y=356:shortest=1[v_chart];"
        f"[3:v]format=rgba[lsup];"
        f"[4:v]format=rgba[leq];"
        f"[5:v]format=rgba[ldem];"
        f"[v_chart][lsup]overlay=x='{wipe_sup}':y=356:enable='gte(t,{t_sup})'[v_z1];"
        f"[v_z1][leq]overlay=x='{wipe_eq}':y=356:enable='gte(t,{t_eq})'[v_z2];"
        f"[v_z2][ldem]overlay=x='{wipe_dem}':y=356:enable='gte(t,{t_dem})'[v_z3];"
        f"[v_z3]drawbox=x=0:y=1908:w='iw*(t/{dur})':h=12:color=0xF5B423:t=fill[vbar];"
        f"[vbar]ass={ass_file}[vout]"
    )

    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1", "-t", str(dur + 1.0), "-i", bg_png,
        "-stream_loop", "-1", "-i", vid_15m,
        "-stream_loop", "-1", "-i", vid_5m,
        "-loop", "1", "-t", str(dur + 1.0), "-i", "assets/layer_supply.png",
        "-loop", "1", "-t", str(dur + 1.0), "-i", "assets/layer_eq.png",
        "-loop", "1", "-t", str(dur + 1.0), "-i", "assets/layer_demand.png",
        "-i", audio_mp3,
        "-filter_complex", filter_graph,
        "-map", "[vout]", "-map", "6:a",
        "-c:v", "libx264", "-profile:v", "main", "-level", "4.0", "-preset", "fast", "-crf", "22", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart", "-shortest",
        output_mp4
    ], check=True)

async def main():
    with open("assets/analysis_output.json") as f:
        data = json.load(f)

    smc = data["smc"]

    create_zone_layer_pngs(smc)
    export_telegram_chart("assets/tv_15m.png", "assets/telegram_chart.png", data["session"], smc)
    build_background_frame("assets/frame_bg.png", data["session"], smc)

    await synthesize_human_voice(data["spoken_script"], "assets/v_raw.mp3", "assets/v_clean.mp3")
    cues = build_pop_captions_and_cues("assets/v_clean.mp3", "assets/subs.ass")
    compile_live_video("assets/frame_bg.png", "assets/tv_15m.webm", "assets/tv_5m.webm", "assets/v_clean.mp3", "assets/subs.ass", cues, "assets/final_reel.mp4")
    print(f"✅ Live Moving Chart & Voice-Synced Zone Reel compiled! Cues: {cues}")

    if data.get("recap_enabled") and data.get("recap_spoken_script"):
        build_background_frame("assets/recap_bg.png", "TARGET PLAYED OUT ✅", smc, is_recap=True)
        await synthesize_human_voice(data["recap_spoken_script"], "assets/rv_raw.mp3", "assets/rv_clean.mp3")
        rcues = build_pop_captions_and_cues("assets/rv_clean.mp3", "assets/rsubs.ass")
        compile_live_video("assets/recap_bg.png", "assets/tv_15m.webm", "assets/tv_5m.webm", "assets/rv_clean.mp3", "assets/rsubs.ass", rcues, "assets/recap_reel.mp4")
        print("✅ Bonus Recap Reel compiled.")

if __name__ == "__main__":
    asyncio.run(main())
