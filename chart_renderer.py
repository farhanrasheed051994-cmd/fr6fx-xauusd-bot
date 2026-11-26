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


def load_mt5_candles(tf_key, bars=36):
    with open(MT5_DATA_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    df = pd.DataFrame(raw[tf_key])
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.set_index("time", inplace=True)
    for col in ("open", "high", "low", "close"):
        df[col] = df[col].astype(float)
    return df.tail(bars).copy()


def get_asia_span(df):
    asia_idxs = [i for i, ts in enumerate(df.index) if 0 <= ts.hour < 7]
    if len(asia_idxs) >= 2:
        return asia_idxs.__getitem__(0), asia_idxs[-1]
    return None, None
def render_tv_stage_chart(df, tf_label, smc, stage, out_png_path):
    fig, ax = plt.subplots(figsize=(8.64, 9.12), dpi=125)
    bg_color = "#0b111e"
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
    atr = float(smc.get("atr_m15", 6.0))
    is_bull = "BULLISH" in str(smc.get("bias_label", ""))

    # Realistic intraday expansion levels (never squish the Y-axis!)
    bull_tp = round(sup_high + max(atr * 1.1, 6.0), 1)
    bear_tp = round(dem_low - max(atr * 1.1, 6.0), 1)

    c_low = min(float(df["low"].min()), dem_low, inv_lvl if stage >= 5 else dem_low)
    c_high = max(float(df["high"].max()), sup_high, inv_lvl if stage >= 5 else sup_high)
    if stage >= 2:
        c_high = max(c_high, bull_tp)
    if stage >= 3:
        c_low = min(c_low, bear_tp)

    c_span = max(c_high - c_low, 10.0)
    y_min = c_low - c_span * 0.08
    y_max = c_high + c_span * 0.10

    # Subtle Session Watermark + Asia Range Box
    a_start, a_end = get_asia_span(df)
    if a_start is not None and tf_label == "M15":
        a_low, a_high = float(smc["asia_low"]), float(smc["asia_high"])
        ax.add_patch(patches.Rectangle(
            (a_start - 0.4, a_low), (a_end - a_start) + 0.8, max(a_high - a_low, 1.5),
            linewidth=1.0, edgecolor="#6366f1", facecolor="#6366f1", alpha=0.12, linestyle="--", zorder=1
        ))
        ax.text(
            a_start + 0.3, a_high + c_span * 0.008,
            "ASIA RANGE",
            color="#818cf8", fontsize=8.5, fontweight="bold", va="bottom", zorder=4
        )

    # Tall, Bold TradingView Candlesticks (never squished)
    for i in range(n_total):
        c_val, o_val, h_val, l_val = float(closes[i]), float(opens[i]), float(highs[i]), float(lows[i])
        col = "#089981" if c_val >= o_val else "#f23645"
        ax.plot((i, i), (l_val, h_val), color=col, linewidth=2.2, zorder=3)
        b_bot = min(o_val, c_val)
        b_h = max(abs(c_val - o_val), c_span * 0.012)
        ax.bar(i, b_h, bottom=b_bot, width=0.74, color=col, edgecolor=col, linewidth=0.8, zorder=4)

    x_axis_badge = n_total + 1.8

    # Stage 2+: Supply Zone + Right-Axis Badge + Breakout Target
    if stage >= 2:
        sup_h_box = max(sup_high - sup_low, c_span * 0.04)
        ax.add_patch(patches.Rectangle(
            (-0.6, sup_low), n_total + 2.2, sup_h_box,
            linewidth=0, facecolor="#f23645", alpha=0.22, zorder=2
        ))
        ax.axhline(sup_high, color="#f23645", linestyle="--", linewidth=1.6, zorder=5)
        ax.text(1.0, sup_high + c_span * 0.008, "SUPPLY ZONE", color="#f87171", fontsize=8.8, fontweight="bold", zorder=6)
        ax.text(
            x_axis_badge, sup_high, f" {sup_high:.1f} ",
            color="#ffffff", fontsize=9.8, fontweight="bold", va="center",
            bbox=dict(boxstyle="round,pad=0.22", facecolor="#f23645", edgecolor="none"), zorder=9
        )
        ax.axhline(bull_tp, color="#a855f7", linestyle=":", linewidth=1.4, zorder=5)
        ax.text(1.0, bull_tp + c_span * 0.008, f"IF BROKEN -> NEXT TARGET", color="#c084fc", fontsize=8.4, fontweight="bold", zorder=6)
        ax.text(
            x_axis_badge, bull_tp, f" {bull_tp:.1f} ",
            color="#ffffff", fontsize=9.5, fontweight="bold", va="center",
            bbox=dict(boxstyle="round,pad=0.20", facecolor="#7e22ce", edgecolor="none"), zorder=9
        )

    # Stage 3+: Demand Zone + Right-Axis Badge + Breakdown Target
    if stage >= 3:
        dem_h_box = max(dem_high - dem_low, c_span * 0.04)
        ax.add_patch(patches.Rectangle(
            (-0.6, dem_low), n_total + 2.2, dem_h_box,
            linewidth=0, facecolor="#06b6d4", alpha=0.22, zorder=2
        ))
        ax.axhline(dem_low, color="#06b6d4", linestyle="--", linewidth=1.6, zorder=5)
        ax.text(1.0, dem_low - c_span * 0.008, "DEMAND ZONE", color="#22d3ee", fontsize=8.8, fontweight="bold", va="top", zorder=6)
        ax.text(
            x_axis_badge, dem_low, f" {dem_low:.1f} ",
            color="#0f172a", fontsize=9.8, fontweight="bold", va="center",
            bbox=dict(boxstyle="round,pad=0.22", facecolor="#22d3ee", edgecolor="none"), zorder=9
        )
        ax.axhline(bear_tp, color="#f97316", linestyle=":", linewidth=1.4, zorder=5)
        ax.text(1.0, bear_tp - c_span * 0.008, f"IF BROKEN -> NEXT TARGET", color="#fb923c", fontsize=8.4, fontweight="bold", va="top", zorder=6)
        ax.text(
            x_axis_badge, bear_tp, f" {bear_tp:.1f} ",
            color="#ffffff", fontsize=9.5, fontweight="bold", va="center",
            bbox=dict(boxstyle="round,pad=0.20", facecolor="#c2410c", edgecolor="none"), zorder=9
        )

    # Stage 4+: Glowing Watch Zone
    if stage >= 4:
        wz_h = max(wz_high - wz_low, c_span * 0.045)
        ax.add_patch(patches.Rectangle(
            (max(n_total - 20, 0), wz_low), 21.6, wz_h,
            linewidth=1.8, edgecolor="#facc15", facecolor="#facc15", alpha=0.28, zorder=3
        ))
        ax.text(
            n_total - 1.0, wz_low + wz_h * 0.5,
            "WATCH ZONE",
            color="#facc15", fontsize=9.2, fontweight="bold", ha="right", va="center", zorder=8
        )

    # Stage 5: Clean M5 Confirmation Path & Stop Loss Badge
    if stage >= 5:
        ax.axhline(inv_lvl, color="#fb7185", linestyle=":", linewidth=1.5, zorder=5)
        ax.text(
            x_axis_badge, inv_lvl, f" SL {inv_lvl:.0f} ",
            color="#ffffff", fontsize=9.2, fontweight="bold", va="center",
            bbox=dict(boxstyle="round,pad=0.20", facecolor="#be123c", edgecolor="none"), zorder=9
        )
        wz_mid = (wz_low + wz_high) * 0.5
        target_p = sup_low if is_bull else dem_high
        ax.plot((n_total - 1, n_total + 0.4), (live_p, wz_mid), color="#facc15", linestyle="--", linewidth=2.4, zorder=8)
        ax.annotate(
            "", xy=(n_total + 1.5, target_p), xytext=(n_total + 0.4, wz_mid),
            arrowprops=dict(arrowstyle="->", color="#facc15", lw=3.0, ls="--"), zorder=9
        )

    # Live Price Pill on Right Axis
    ax.plot((n_total - 1, x_axis_badge - 0.1), (live_p, live_p), color="#94a3b8", linestyle=":", linewidth=1.2, zorder=4)
    ax.text(
        x_axis_badge, live_p, f" {live_p:.2f} ",
        color="#ffffff", fontsize=10.2, fontweight="bold", va="center",
        bbox=dict(boxstyle="round,pad=0.24", facecolor="#089981" if is_bull else "#f23645", edgecolor="none"),
        zorder=10
    )

    ax.yaxis.tick_right()
    ax.tick_params(axis="y", colors="#94a3b8", labelsize=10.2, length=0)
    ax.tick_params(axis="x", colors="#64748b", labelsize=8.8, length=0)
    ax.grid(True, color="#162033", linestyle="-", linewidth=0.7, alpha=0.9)

    tick_idxs = list(range(0, n_total, max(n_total // 4, 1)))
    ax.set_xticks(tick_idxs)
    ax.set_xticklabels([df.index[i].strftime("%H:%M") for i in tick_idxs])

    for spine in ("top", "left", "bottom", "right"):
        ax.spines[spine].set_visible(False)

    ax.set_ylim(y_min, y_max)
    ax.set_xlim(-0.8, n_total + 4.8)

    plt.subplots_adjust(left=0.02, right=0.86, top=0.985, bottom=0.045)
    plt.savefig(out_png_path, facecolor=bg_color, dpi=125)
    plt.close(fig)

    img = Image.open(out_png_path).convert("RGB").resize((1040, 1100), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img, "RGBA")
    try:
        f_top = ImageFont.truetype(FONT_BOLD, 22)
    except Exception:
        f_top = ImageFont.load_default()

    draw.text((28, 14), f"XAUUSDm • {tf_label} • FR6 FX", fill=(203, 213, 225, 255), font=f_top)
    draw.ellipse((28, 46, 42, 60), fill=(242, 54, 69, 255))
    draw.text((50, 41), "MT5 LIVE", fill=(242, 54, 69, 255), font=f_top)
    img.save(out_png_path)


def build_progressive_chart_stages(smc):
    os.makedirs("assets", exist_ok=True)
    df_15 = load_mt5_candles("xau_m15", bars=36)
    df_5 = load_mt5_candles("xau_m5", bars=36)

    render_tv_stage_chart(df_15, "M15", smc, stage=1, out_png_path="assets/stage_1.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=2, out_png_path="assets/stage_2.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=3, out_png_path="assets/stage_3.png")
    render_tv_stage_chart(df_15, "M15", smc, stage=4, out_png_path="assets/stage_4.png")
    render_tv_stage_chart(df_5, "M5", smc, stage=5, out_png_path="assets/stage_5.png")
