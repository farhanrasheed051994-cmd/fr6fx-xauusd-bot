import os
import re
import json
import shutil
import asyncio
import subprocess
from datetime import datetime, timezone
import edge_tts
from faster_whisper import WhisperModel
from PIL import Image, ImageDraw, ImageFont

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def load_font(path, size):
    for candidate in (path, "C:/Windows/Fonts/arialbd.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def get_audio_duration(audio_path):
    cmd = (
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    )
    return float(subprocess.check_output(cmd).decode().strip())


async def generate_voiceover(text, out_mp3):
    tts_text = (
        text.replace("FR6 FX", "F R 6 F X")
        .replace("FR6FX", "F R 6 F X")
        .replace("link in bio", "link in our profile")
    )
    voices = ("en-US-AndrewNeural", "en-US-ChristopherNeural", "en-GB-RyanNeural")
    for v in voices:
        try:
            communicate = edge_tts.Communicate(tts_text, voice=v, rate="+3%")
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
    import wave
    import numpy as np

    wav_path = "assets/voiceover_16k.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", "-f", "wav", wav_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    with wave.open(wav_path, "rb") as wf:
        audio_np = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

    model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_np, word_timestamps=True)
    raw_words = []
    for seg in segments:
        for w in (seg.words or ()):
            clean_w = w.word.strip().replace(",", "")
            clean_w = re.sub(r"^\.+|\.+$", "", clean_w)
            if clean_w:
                raw_words.append({"word": clean_w, "start": float(w.start), "end": float(w.end)})

    merged = []
    i = 0
    brand_tokens = {"F", "R", "6", "FX", "6FX", "FR6", "FR6FX", "OR"}
    while i < len(raw_words):
        cur = raw_words[i]["word"]
        cur_up = cur.upper()

        if cur_up == "F" and i + 1 < len(raw_words) and raw_words[i + 1]["word"].upper() in brand_tokens:
            end_t = raw_words[i + 1]["end"]
            j = i + 1
            while j < len(raw_words) and raw_words[j]["word"].upper() in brand_tokens:
                end_t = raw_words[j]["end"]
                j += 1
            merged.append({"word": "FR6 FX", "start": raw_words[i]["start"], "end": end_t})
            i = j
            continue

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

        merged.append({"word": cur, "start": raw_words[i]["start"], "end": raw_words[i]["end"]})
        i += 1
    return merged


def detect_stage_timestamps(words, total_dur):
    t2 = round(total_dur * 0.22, 2)
    t3 = round(total_dur * 0.44, 2)
    t4 = round(total_dur * 0.65, 2)
    t5 = round(total_dur * 0.80, 2)

    for i, w in enumerate(words):
        cur = w["word"].lower().strip(".,!?")
        nxt = words[i + 1]["word"].lower().strip(".,!?") if i + 1 < len(words) else ""
        st = float(w["start"])
        if "resist" in cur and 1.5 <= st <= total_dur * 0.45:
            t2 = round(st, 2)
        elif "support" in cur and t2 + 1.5 <= st <= total_dur * 0.65:
            t3 = round(st, 2)
        elif cur == "watch" and "zone" in nxt and t3 + 1.5 <= st <= total_dur * 0.85:
            t4 = round(st, 2)
        elif (cur in ("5", "five") and "minute" in nxt) or cur == "dropping":
            if t4 + 1.2 <= st <= total_dur - 1.8:
                t5 = round(st, 2)

    t2 = max(2.0, min(t2, total_dur - 6.0))
    t3 = max(t2 + 1.8, min(t3, total_dur - 4.5))
    t4 = max(t3 + 1.8, min(t4, total_dur - 3.0))
    t5 = max(t4 + 1.5, min(t5, total_dur - 1.8))
    return (t2, t3, t4, t5)
def render_caption_overlays(words, total_dur):
    os.makedirs("assets/caps", exist_ok=True)
    f_cap = load_font(FONT_BOLD, 46)
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

            pad_x, pad_y = 32, 14
            box_w = min(880, int(total_w + pad_x * 2))
            x_box = int(510 - box_w * 0.5)
            y_box = 1435

            draw.rounded_rectangle(
                (x_box, y_box, x_box + box_w, y_box + 82),
                radius=18, fill=(10, 14, 23, 242), outline=(250, 204, 21, 235), width=3
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
    canvas = Image.new("RGB", (1080, 1920), (11, 14, 20))
    draw = ImageDraw.Draw(canvas)

    f_hook = load_font(FONT_BOLD, 40)
    f_meta = load_font(FONT_BOLD, 22)

    hook_clean = str(hook_title).upper()[:22]
    hw = draw.textlength(hook_clean, font=f_hook)
    pill_w = int(hw + 64)
    px1 = int((1080 - pill_w) * 0.5)
    draw.rounded_rectangle((px1, 178, px1 + pill_w, 246), radius=18, fill=(24, 28, 39), outline=(250, 204, 21), width=2)
    draw.text(((1080 - hw) * 0.5, 191), hook_clean, fill=(250, 204, 21), font=f_hook)

    live_p = smc["live_price"]
    bias_l = str(smc["bias_label"])
    draw.text((28, 266), f"{session_name} • {bias_l}", fill=(148, 163, 184), font=f_meta)
    meta_right = f"XAUUSD ${live_p}"
    rw = draw.textlength(meta_right, font=f_meta)
    draw.text((955 - rw, 266), meta_right, fill=(56, 189, 248), font=f_meta)

    draw.rounded_rectangle((16, 298, 1064, 1406), radius=18, fill=(19, 23, 34), outline=(42, 46, 57), width=2)
    chart = Image.open(stage_png).convert("RGB").resize((1040, 1100), Image.Resampling.LANCZOS)
    canvas.paste(chart, (20, 302))

    draw.rectangle((20, 1412, 1060, 1420), fill=(30, 34, 45))
    bar_w = int(1040 * max(0.06, min(1.0, progress_pct)))
    draw.rectangle((20, 1412, 20 + bar_w, 1420), fill=(250, 204, 21))

    canvas.save(out_png)


def export_telegram_chart_graphic(smc, session_name, date_label, chart_png, out_png):
    canvas = Image.new("RGB", (1080, 1360), (11, 14, 20))
    draw = ImageDraw.Draw(canvas)
    f_title = load_font(FONT_BOLD, 25)
    f_sub = load_font(FONT_BOLD, 19)
    f_card_lbl = load_font(FONT_BOLD, 17)
    f_card_val = load_font(FONT_BOLD, 22)

    bias_l = str(smc.get("bias_label", "NEUTRAL"))
    is_bull = "BULLISH" in bias_l
    bias_col = (8, 153, 129) if is_bull else ((242, 54, 69) if "BEARISH" in bias_l else (245, 158, 11))

    draw.rounded_rectangle((28, 20, 1052, 118), radius=14, fill=(19, 23, 34), outline=(56, 189, 248), width=2)
    draw.text((48, 34), f"FR6 FX  |  XAUUSDm {session_name}", fill=(255, 255, 255), font=f_title)
    draw.text((48, 76), f"{date_label}  |  SPOT: ${smc['live_price']}  |  DXYm: {smc['dxy_now']}", fill=(250, 204, 21), font=f_sub)

    draw.rounded_rectangle((820, 34, 1032, 74), radius=8, fill=bias_col)
    draw.text((838, 43), bias_l, fill=(255, 255, 255), font=f_card_lbl)

    chart = Image.open(chart_png).convert("RGB").resize((1040, 1100), Image.Resampling.LANCZOS)
    canvas.paste(chart, (20, 132))

    cards = (
        (28, 356, "SUPPLY RESISTANCE", str(smc["supply_zone"]), (242, 54, 69), (254, 202, 202)),
        (376, 704, "PRIMARY WATCH ZONE", f"${smc['watch_low']} – ${smc['watch_high']}", (250, 204, 21), (253, 230, 138)),
        (724, 1052, "DEMAND SUPPORT", str(smc["demand_zone"]), (8, 153, 129), (167, 243, 208)),
    )
    for x1, x2, lbl, val, border_c, val_c in cards:
        draw.rounded_rectangle((x1, 1244, x2, 1344), radius=12, fill=(19, 23, 34), outline=border_c, width=2)
        draw.text((x1 + 16, 1258), lbl, fill=(148, 163, 184), font=f_card_lbl)
        draw.text((x1 + 16, 1294), val, fill=val_c, font=f_card_val)

    canvas.save(out_png)
def render_progressive_reel(smc, session_name, hook_title, spoken_script, out_mp4, prebuilt_audio=None):
    os.makedirs("assets", exist_ok=True)
    voice_mp3 = "assets/voiceover.mp3"

    if prebuilt_audio:
        voice_dur, words = prebuilt_audio
    else:
        asyncio.run(generate_voiceover(spoken_script, voice_mp3))
        voice_dur = get_audio_duration(voice_mp3)
        words = extract_word_captions(voice_mp3)

    total_dur = round(voice_dur + 0.4, 2)
    t2, t3, t4, t5 = detect_stage_timestamps(words, voice_dur)

    xf = 0.22
    stages_spec = (
        ("assets/stage_1.png", "assets/frame_1.png", round(t2 + xf, 2), 0.20),
        ("assets/stage_2.png", "assets/frame_2.png", round((t3 - t2) + xf, 2), 0.42),
        ("assets/stage_3.png", "assets/frame_3.png", round((t4 - t3) + xf, 2), 0.64),
        ("assets/stage_4.png", "assets/frame_4.png", round((t5 - t4) + xf, 2), 0.82),
        ("assets/stage_5.png", "assets/frame_5.png", round(total_dur - t5, 2), 1.00),
    )

    for st_png, fr_png, _, pct in stages_spec:
        build_composite_stage_frame(smc, session_name, hook_title, st_png, fr_png, progress_pct=pct)

    d1, d2, d3, d4, d5 = [s for s in stages_spec]
    off1, off2, off3, off4 = round(t2, 2), round(t3, 2), round(t4, 2), round(t5, 2)

    f1, f2, f3, f4, f5 = [max(int(d * 60) + 15, 60) for d in (d1, d2, d3, d4, d5)]
    filter_parts = (
        f"[0:v]scale=1140:2026,zoompan=z='min(zoom+0.0005,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={f1}:s=1080x1920:fps=60,trim=duration={d1},setpts=PTS-STARTPTS[v0];"
        f"[1:v]scale=1140:2026,zoompan=z='1.05-0.0004*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)-20':d={f2}:s=1080x1920:fps=60,trim=duration={d2},setpts=PTS-STARTPTS[v1];"
        f"[2:v]scale=1140:2026,zoompan=z='min(zoom+0.0004,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)+20':d={f3}:s=1080x1920:fps=60,trim=duration={d3},setpts=PTS-STARTPTS[v2];"
        f"[3:v]scale=1140:2026,zoompan=z='min(zoom+0.0006,1.06)':x='iw/2-(iw/zoom/2)+15':y='ih/2-(ih/zoom/2)':d={f4}:s=1080x1920:fps=60,trim=duration={d4},setpts=PTS-STARTPTS[v3];"
        f"[4:v]scale=1140:2026,zoompan=z='min(zoom+0.0007,1.07)':x='iw/2-(iw/zoom/2)+25':y='ih/2-(ih/zoom/2)':d={f5}:s=1080x1920:fps=60,trim=duration={d5},setpts=PTS-STARTPTS[v4];"
        f"[v0][v1]xfade=transition=smoothleft:duration={xf}:offset={off1}[x1];"
        f"[x1][v2]xfade=transition=smoothright:duration={xf}:offset={off2}[x2];"
        f"[x2][v3]xfade=transition=fade:duration={xf}:offset={off3}[x3];"
        f"[x3][v4]xfade=transition=zoomin:duration={xf}:offset={off4}[vbase];"
    )

    overlays = render_caption_overlays(words, total_dur)
    inputs = [
        "-loop", "1", "-i", "assets/frame_1.png",
        "-loop", "1", "-i", "assets/frame_2.png",
        "-loop", "1", "-i", "assets/frame_3.png",
        "-loop", "1", "-i", "assets/frame_4.png",
        "-loop", "1", "-i", "assets/frame_5.png",
        "-i", voice_mp3,
    ]

    last_v = "[vbase]"
    for idx, (cap_png, st_t, en_t) in enumerate(overlays):
        in_idx = 6 + idx
        inputs.extend(["-i", cap_png])
        next_v = f"[vc{idx}]"
        filter_parts += f"{last_v}[{in_idx}:v]overlay=0:0:enable='between(t,{st_t},{en_t})'{next_v};"
        last_v = next_v

    ms2, ms3, ms4, ms5 = [int(t * 1000) for t in (off1, off2, off3, off4)]
    filter_parts += (
        f"aevalsrc='0.06*sin(2*PI*520*t)*exp(-18*t)':s=44100:d=0.22[pop];"
        f"[pop]asplit=4[p1][p2][p3][p4];"
        f"[p1]adelay={ms2}|{ms2}[d1];"
        f"[p2]adelay={ms3}|{ms3}[d2];"
        f"[p3]adelay={ms4}|{ms4}[d3];"
        f"[p4]adelay={ms5}|{ms5}[d4];"
        f"[5:a]apad=whole_dur={total_dur}[va];"
        f"[va][d1][d2][d3][d4]amix=inputs=5:duration=first:normalize=0[aout]"
    )

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_parts,
        "-map", last_v, "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-r", "60", "-c:a", "aac", "-b:a", "192k", "-t", str(total_dur),
        out_mp4
    ]
    subprocess.run(cmd, check=True)
    print(f"🎬 60fps TradingView-Style Motion Reel exported: {out_mp4}")


def render_with_remotion_or_fallback(smc, session_name, hook_title, spoken_script, out_mp4):
    os.makedirs("assets", exist_ok=True)
    voice_mp3 = "assets/voiceover.mp3"
    asyncio.run(generate_voiceover(spoken_script, voice_mp3))
    voice_dur = get_audio_duration(voice_mp3)
    words = extract_word_captions(voice_mp3)
    total_dur = round(voice_dur + 0.4, 2)
    t2, t3, t4, t5 = detect_stage_timestamps(words, voice_dur)

    if os.path.exists("remotion/node_modules"):
        try:
            os.makedirs("remotion/public", exist_ok=True)
            shutil.copyfile(voice_mp3, "remotion/public/voiceover.mp3")
            with open("data/mt5_data.json", "r", encoding="utf-8") as f:
                mt5_raw = json.load(f)

            def to_tv_bars(bars):
                out = []
                for b in bars[-45:]:
                    ts = int(datetime.strptime(b["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
                    out.append({"time": ts, "open": b["open"], "high": b["high"], "low": b["low"], "close": b["close"]})
                return out

            props = {
                "session": session_name,
                "hookTitle": hook_title,
                "durationSec": total_dur,
                "stageTimes": [t2, t3, t4, t5],
                "smc": smc,
                "candles15m": to_tv_bars(mt5_raw.get("xau_m15", [])),
                "candles5m": to_tv_bars(mt5_raw.get("xau_m5", [])),
                "captions": words,
            }
            with open("assets/remotion_props.json", "w", encoding="utf-8") as pf:
                json.dump(props, pf)

            subprocess.run(
                [
                    "npx", "remotion", "render", "src/index.ts", "TradingViewReel",
                    os.path.abspath(out_mp4),
                    "--props", os.path.abspath("assets/remotion_props.json"),
                    "--fps=60", "--codec=h264"
                ],
                cwd="remotion",
                check=True,
            )
            print(f"🎬 60fps TradingView Lightweight Charts Reel rendered via Remotion: {out_mp4}")
            return
        except Exception as re_err:
            print(f"⚠️ Remotion fallback triggered ({re_err}); using FFmpeg motion renderer...")

    render_progressive_reel(
        smc, session_name, hook_title, spoken_script, out_mp4, prebuilt_audio=(voice_dur, words)
    )


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
    render_with_remotion_or_fallback(
        smc, session_name, hook_title, spoken_script, "assets/final_reel.mp4"
    )


if __name__ == "__main__":
    main()
