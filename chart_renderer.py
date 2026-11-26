import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from PIL import Image, ImageDraw, ImageFont

MT5_DATA_PATH = os.path.join("data", "mt5_data.json")
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def load_mt5_candles(tf_key, bars=38):
    with open(MT5_DATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    df = pd.DataFrame(raw[tf_key])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.set_index("time", inplace=True)
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    return df.tail(bars).copy()


def detect_swing_badges(df):
    highs = df["high"].values
    lows = df["low"].values
    badges = []
    prev_h, prev_l = None, None
    for i in range(3, len(df) - 3):
        cur_h, cur_l = float(highs[i]), float(lows[i])
        if cur_h == np.max(highs[i - 3 : i + 4]):
            lbl = "HH" if (prev_h and cur_h > prev_h) else ("LH" if prev_h else "SH")
            badges.append((i, cur_h, lbl, True))
            prev_h = cur_h
        elif cur_l == np.min(lows[i - 3 : i + 4]):
            lbl = "HL" if (prev_l and cur_l > prev_l) else ("LL" if prev_l else "SL")
            badges.append((i, cur_l, lbl, False))
            prev_l = cur_l
    return badges[-4:]
def render_tv_stage_chart(df, tf_label, smc, stage, out_png_path):
    fig, ax = plt.subplots(figsize=(8.64, 8.32), dpi=125)
    bg_color = "#0d121d"
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    opens, highs, lows, closes = (
        df["open"].values,
        df["high"].values,
        df["low"].values,
        df["close"].values,
    )
    n_total = len(df)

    sup_high = float(smc["supply_high"])
    sup_low = float(smc["supply_low"])
    dem_low = float(smc["demand_low"])
    dem_high = float(smc["demand_high"])
    wz_low = float(smc["watch_low"])
    wz_high = float(smc["watch_high"])
    inv_lvl = float(smc["invalidation"])
    live_p = float(smc["live_price"])
    is_bull = "BULLISH" in str(smc.get("bias_label", ""))

    c_low = min(float(df["low"].min()), dem_low, inv_lvl)
    c_high = max(float(df["high"].max()), sup_high, inv_lvl)
    c_span = max(c_high - c_low, 8.0)
    y_min = c_low - c_span * 0.10
    y_max = c_high + c_span * 0.11

    # Chunky Mobile-Optimized Candlesticks
    for i in range(n_total):
        c_val, o_val, h_val, l_val = float(closes[i]), float(opens[i]), float(highs[i]), float(lows[i])
        col = "#10b981" if c_val >= o_val else "#ef4444"
        ax.plot((i, i), (l_val, h_val), color=col, linewidth=2.1, zorder=3)
        b_bot = min(o_val, c_val)
        b_h = max(abs(c_val - o_val), c_span * 0.013)
        ax.bar(i, b_h, bottom=b_bot, width=0.72, color=col, edgecolor=col, linewidth=0.9, zorder=4)

    # Large Swing Structure Badges (HH/HL/LH/LL)
    for idx_b, price_b, lbl_b, is_high_b in detect_swing_badges(df):
        y_off = c_span * 0.032 if is_high_b else -c_span * 0.038
        b_col = "#38bdf8" if lbl_b in ("HH", "HL") else "#f59e0b"
        ax.text(
            idx_b, price_b + y_off, f" {lbl_b} ",
            color="#ffffff", fontsize=10.0, fontweight="bold", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#1e293b", edgecolor=b_col, linewidth=1.4),
            zorder=6
        )

    # Stage 2+: Resistance / Supply Zone Pill
    if stage >= 2:
        sup_h_box = max(sup_high - sup_low, c_span * 0.035)
        ax.add_patch(patches.Rectangle(
            (-1, sup_low), n_total + 8, sup_h_box,
            linewidth=1.4, edgecolor="#ef4444", facecolor="#ef4444", alpha=0.22, zorder=2
        ))
        ax.axhline(sup_high, color="#ef4444", linestyle="--", linewidth=2.0, zorder=5)
        ax.text(
            0.8, sup_high + c_span * 0.018,
            f" RESISTANCE  ${int(round(sup_high))} ",
            color="#ffffff", fontsize=10.5, fontweight="bold", va="bottom",
            bbox=dict(boxstyle="round,pad=0.28", facecolor="#dc2626", edgecolor="none"),
            zorder=8
        )

    # Stage 3+: Support / Demand Zone Pill
    if stage >= 3:
        dem_h_box = max(dem_high - dem_low, c_span * 0.035)
        ax.add_patch(patches.Rectangle(
            (-1, dem_low), n_total + 8, dem_h_box,
            linewidth=1.4, edgecolor="#06b6d4", facecolor="#06b6d4", alpha=0.22, zorder=2
        ))
        ax.axhline(dem_low, color="#06b6d4", linestyle="--", linewidth=2.0, zorder=5)
        ax.text(
            0.8, dem_low - c_span * 0.018,
            f" SUPPORT  ${int(round(dem_low))} ",
            color="#0f172a", fontsize=10.5, fontweight="bold", va="top",
            bbox=dict(boxstyle="round,pad=0.28", facecolor="#22d3ee", edgecolor="none"),
            zorder=8
        )

    # Stage 4+: Glowing Watch Zone
    if stage >= 4:
        wz_h = max(wz_high - wz_low, c_span * 0.045)
        ax.add_patch(patches.Rectangle(
            (max(n_total - 22, 0), wz_low), 29, wz_h,
            linewidth=2.0, edgecolor="#facc15", facecolor="#facc15", alpha=0.30, zorder=3
        ))
        ax.text(
            n_total + 5.6, wz_low + wz_h * 0.5,
            " WATCH ZONE ",
            color="#0f172a", fontsize=10.0, fontweight="bold", ha="right", va="center",
            bbox=dict(boxstyle="round,pad=0.26", facecolor="#facc15", edgecolor="none"),
            zorder=9
        )

    # Stage 5: M5 Entry Path & Stop Loss Level
    if stage >= 5:
        ax.axhline(inv_lvl, color="#fb7185", linestyle=":", linewidth=1.8, zorder=5)
        ax.text(
            n_total * 0.48,
            inv_lvl - c_span * 0.016 if is_bull else inv_lvl + c_span * 0.016,
            f" INVALIDATION  ${int(round(inv_lvl))} ",
            color="#ffffff", fontsize=9.8, fontweight="bold",
            va="top" if is_bull else "bottom",
            bbox=dict(boxstyle="round,pad=0.24", facecolor="#be123c", edgecolor="none"),
            zorder=8
        )
        wz_mid = (wz_low + wz_high) * 0.5
        target_p = sup_low if is_bull else dem_high
        ax.plot((n_total - 1, n_total + 1.8), (live_p, wz_mid), color="#facc15", linestyle="--", linewidth=2.5, zorder=8)
        ax.annotate(
            "", xy=(n_total + 5.0, target_p), xytext=(n_total + 1.8, wz_mid),
            arrowprops=dict(arrowstyle="->", color="#facc15", lw=3.0, ls="--"),
            zorder=9
        )

    # Large Live Price Tag on Right Axis
    ax.plot((n_total - 1, n_total + 5.8), (live_p, live_p), color="#94a3b8", linestyle=":", linewidth=1.3, zorder=4)
    ax.text(
        n_total + 6.0, live_p, f" {live_p:.2f} ",
        color="#ffffff", fontsize=11.0, fontweight="bold", va="center",
        bbox=dict(boxstyle="round,pad=0.28", facecolor="#10b981" if is_bull else "#ef4444", edgecolor="none"),
        zorder=10
    )

    ax.yaxis.tick_right()
    ax.tick_params(axis="y", colors="#cbd5e1", labelsize=11.5, length=0)
    ax.tick_params(axis="x", colors="#64748b", labelsize=9.5, length=0)
    ax.grid(True, color="#1e293b", linestyle="-", linewidth=0.8, alpha=0.85)

    tick_idxs = list(range(0, n_total, max(n_total // 4, 1)))
    ax.set_xticks(tick_idxs)
    ax.set_xticklabels([df.index[i].strftime("%H:%M") for i in tick_idxs])

    for spine in ("top", "left", "bottom", "right"):
        ax.spines[spine].set_visible(False)

    ax.set_ylim(y_min, y_max)
    ax.set_xlim(-1.2, n_total + 8.6)

    plt.subplots_adjust(left=0.04, right=0.81, top=0.985, bottom=0.05)
    plt.savefig(out_png_path, facecolor=bg_color, dpi=125)
    plt.close(fig)

    img = Image.open(out_png_path).convert("RGB").resize((1080, 1040), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        f_top = ImageFont.truetype(FONT_BOLD, 24)
    except Exception:
        f_top = ImageFont.load_default()

    draw.text((44, 18), f"XAUUSDm  •  {tf_label}  •  FR6 FX", fill=(203, 213, 225, 255), font=f_top)
    draw.ellipse((44, 54, 60, 70), fill=(239, 68, 68, 255))
    draw.text((68, 49), "LIVE", fill=(239, 68, 68, 255), font=f_top)
    img.save(out_png_path)


def build_progressive_chart_stages(smc):
    os.makedirs("assets", exist_ok=True)
    df_15 = load_mt5_candles("xau_m15", bars=38)
    df_5 = load_mt5_candles("xau_m5", bars=38)

    render_tv_stage_chart(df_15, "M15", smc, stage=1, out_png_path="assets/stage_1.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=2, out_png_path="assets/stage_2.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=3, out_png_path="assets/stage_3.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=4, out_png_path="assets/stage_4.png")
    render_tv_stage_chart(df_5, "M5", smc, stage=5, out_png_path="assets/stage_5.png")
