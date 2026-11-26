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


def load_mt5_candles(tf_key, bars=48):
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
    n = len(df)
    badges = []
    prev_h = None
    prev_l = None
    for i in range(3, n - 3):
        win_h = np.max(highs[i - 3 : i + 4])
        win_l = np.min(lows[i - 3 : i + 4])
        cur_h = float(highs[i])
        cur_l = float(lows[i])
        if cur_h == win_h:
            lbl = "HH" if (prev_h is not None and cur_h > prev_h) else ("LH" if prev_h is not None else "H")
            badges.append((i, cur_h, lbl, True))
            prev_h = cur_h
        elif cur_l == win_l:
            lbl = "HL" if (prev_l is not None and cur_l > prev_l) else ("LL" if prev_l is not None else "L")
            badges.append((i, cur_l, lbl, False))
            prev_l = cur_l
    return badges[-5:]
def render_tv_stage_chart(df, tf_label, smc, stage, out_png_path):
    fig, ax = plt.subplots(figsize=(8.64, 7.6), dpi=125)
    bg_color = "#0f141f"
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    n_total = len(df)
    x = np.arange(n_total)

    sup_high = float(smc["supply_high"])
    sup_low = float(smc["supply_low"])
    dem_low = float(smc["demand_low"])
    dem_high = float(smc["demand_high"])
    eq_lvl = float(smc["equilibrium"])
    wz_low = float(smc["watch_low"])
    wz_high = float(smc["watch_high"])
    inv_lvl = float(smc["invalidation"])
    is_bull = "BULLISH" in str(smc.get("bias_label", ""))

    live_p = float(smc["live_price"])
    c_low = min(float(df["low"].min()), dem_low, inv_lvl)
    c_high = max(float(df["high"].max()), sup_high, inv_lvl)
    c_span = max(c_high - c_low, 10.0)
    y_min = c_low - c_span * 0.09
    y_max = c_high + c_span * 0.10

    # Candlesticks
    for i in range(n_total):
        c_val, o_val, h_val, l_val = float(closes[i]), float(opens[i]), float(highs[i]), float(lows[i])
        is_up = c_val >= o_val
        col = "#10b981" if is_up else "#ef4444"
        ax.plot((i, i), (l_val, h_val), color=col, linewidth=1.6, zorder=3)
        b_bot = min(o_val, c_val)
        b_h = max(abs(c_val - o_val), c_span * 0.011)
        ax.bar(i, b_h, bottom=b_bot, width=0.66, color=col, edgecolor=col, linewidth=0.7, zorder=4)

    # Swing structure badges (HH/HL/LH/LL)
    for idx_b, price_b, lbl_b, is_high_b in detect_swing_badges(df):
        y_off = c_span * 0.026 if is_high_b else -c_span * 0.032
        b_col = "#38bdf8" if lbl_b in ("HH", "HL") else "#f59e0b"
        ax.text(
            idx_b, price_b + y_off, f" {lbl_b} ",
            color=b_col, fontsize=8.2, fontweight="bold", ha="center", va="center",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="#1e293b", edgecolor=b_col, linewidth=1.0),
            zorder=6
        )

    # 50% Equilibrium subtle reference
    ax.axhline(eq_lvl, color="#64748b", linestyle=":", linewidth=1.0, alpha=0.65, zorder=2)
    ax.text(1.0, eq_lvl + c_span * 0.006, f"EQ 50%  {eq_lvl:.1f}", color="#94a3b8", fontsize=8.0, zorder=5)

    # Stage 2+: Institutional Supply OB
    if stage >= 2:
        sup_h_box = max(sup_high - sup_low, c_span * 0.03)
        ax.add_patch(patches.Rectangle(
            (0, sup_low), n_total + 7, sup_h_box,
            linewidth=1.1, edgecolor="#ef4444", facecolor="#ef4444", alpha=0.16, zorder=2
        ))
        ax.axhline(sup_high, color="#ef4444", linestyle="--", linewidth=1.6, zorder=5)
        ax.text(
            1.2, sup_high + c_span * 0.01,
            f"SUPPLY / RESISTANCE  {int(round(sup_high))}",
            color="#f87171", fontsize=9.6, fontweight="bold", va="bottom", zorder=7
        )

    # Stage 3+: Institutional Demand OB
    if stage >= 3:
        dem_h_box = max(dem_high - dem_low, c_span * 0.03)
        ax.add_patch(patches.Rectangle(
            (0, dem_low), n_total + 7, dem_h_box,
            linewidth=1.1, edgecolor="#06b6d4", facecolor="#06b6d4", alpha=0.16, zorder=2
        ))
        ax.axhline(dem_low, color="#06b6d4", linestyle="--", linewidth=1.6, zorder=5)
        ax.text(
            1.2, dem_low - c_span * 0.01,
            f"DEMAND / SUPPORT  {int(round(dem_low))}",
            color="#22d3ee", fontsize=9.6, fontweight="bold", va="top", zorder=7
        )

    # Stage 4+: Highlighted Primary Watch Zone + Unmitigated FVG
    if stage >= 4:
        wz_h = max(wz_high - wz_low, c_span * 0.04)
        ax.add_patch(patches.Rectangle(
            (max(n_total - 26, 0), wz_low), 34, wz_h,
            linewidth=1.6, edgecolor="#f59e0b", facecolor="#f59e0b", alpha=0.26, zorder=3
        ))
        ax.text(
            n_total + 6.5, wz_low + wz_h * 0.5,
            "WATCH ZONE",
            color="#fbbf24", fontsize=9.2, fontweight="bold", ha="right", va="center", zorder=8
        )

    # Stage 5: M5 Confirmation Entry Path & Invalidation
    if stage >= 5:
        ax.axhline(inv_lvl, color="#fb7185", linestyle=":", linewidth=1.5, zorder=5)
        ax.text(
            n_total * 0.42, inv_lvl - c_span * 0.012 if is_bull else inv_lvl + c_span * 0.012,
            f"INVALIDATION {'<' if is_bull else '>'} {int(round(inv_lvl))}",
            color="#fb7185", fontsize=9.0, fontweight="bold",
            va="top" if is_bull else "bottom", zorder=7
        )

        x_start = n_total - 1
        x_mid = n_total + 2.0
        x_end = n_total + 5.6
        wz_mid = (wz_low + wz_high) * 0.5
        target_p = sup_low if is_bull else dem_high

        ax.plot((x_start, x_mid), (live_p, wz_mid), color="#fbbf24", linestyle="--", linewidth=2.1, zorder=8)
        ax.annotate(
            "", xy=(x_end, target_p), xytext=(x_mid, wz_mid),
            arrowprops=dict(arrowstyle="->", color="#fbbf24", lw=2.5, ls="--"),
            zorder=8
        )

    # Live price tag
    ax.plot((n_total - 1, n_total + 6.8), (live_p, live_p), color="#94a3b8", linestyle=":", linewidth=1.1, zorder=4)
    ax.text(
        n_total + 7.0, live_p, f" {live_p:.2f} ",
        color="#ffffff", fontsize=9.0, fontweight="bold", va="center",
        bbox=dict(boxstyle="round,pad=0.24", facecolor="#10b981" if is_bull else "#ef4444", edgecolor="none"),
        zorder=9
    )

    ax.yaxis.tick_right()
    ax.tick_params(axis="y", colors="#94a3b8", labelsize=9.5, length=0)
    ax.tick_params(axis="x", colors="#64748b", labelsize=8.0, length=0)
    ax.grid(True, color="#1e293b", linestyle="-", linewidth=0.7, alpha=0.85)

    tick_step = max(n_total // 5, 1)
    tick_idxs = list(range(0, n_total, tick_step))
    ax.set_xticks(tick_idxs)
    ax.set_xticklabels([df.index[i].strftime("%H:%M") for i in tick_idxs])

    for spine in ("top", "left", "bottom", "right"):
        ax.spines[spine].set_visible(False)

    ax.set_ylim(y_min, y_max)
    ax.set_xlim(-1.5, n_total + 9.8)

    plt.subplots_adjust(left=0.055, right=0.835, top=0.985, bottom=0.048)
    plt.savefig(out_png_path, facecolor=bg_color, dpi=125)
    plt.close(fig)

    img = Image.open(out_png_path).convert("RGB").resize((1080, 960), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        f_top = ImageFont.truetype(FONT_BOLD, 21)
    except Exception:
        f_top = ImageFont.load_default()

    draw.text((54, 16), f"XAUUSDm  •  {tf_label}  •  FR6 FX", fill=(148, 163, 184, 255), font=f_top)
    draw.ellipse((54, 48, 68, 62), fill=(239, 68, 68, 255))
    draw.text((76, 43), "MT5 LIVE", fill=(239, 68, 68, 255), font=f_top)
    img.save(out_png_path)


def build_progressive_chart_stages(smc):
    os.makedirs("assets", exist_ok=True)
    df_15 = load_mt5_candles("xau_m15", bars=48)
    df_5 = load_mt5_candles("xau_m5", bars=48)

    render_tv_stage_chart(df_15, "M15", smc, stage=1, out_png_path="assets/stage_1.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=2, out_png_path="assets/stage_2.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=3, out_png_path="assets/stage_3.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=4, out_png_path="assets/stage_4.png")
    render_tv_stage_chart(df_5, "M5", smc, stage=5, out_png_path="assets/stage_5.png")
    print("✅ 5 progressive MT5 institutional chart stages rendered.")
