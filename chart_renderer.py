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


def load_font_safe(path, size):
    for candidate in (path, "C:/Windows/Fonts/arialbd.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()

def load_mt5_candles(tf_key, bars=38):
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
        return min(asia_idxs), max(asia_idxs)
    return None, None


def draw_tv_risk_reward_box(ax, n_total, setup, c_span):
    """Draws an authentic TradingView Long/Short Risk-Reward position tool on the right of price."""
    direction = setup.get("direction", "SHORT")
    entry = float(setup["entry"])
    sl = float(setup["sl"])
    tp = float(setup["tp"])
    rr = setup.get("rr", 2.0)

    box_x = n_total - 4.5
    box_w = 5.4

    # Profit Zone (TradingView Teal/Green)
    tp_low, tp_high = min(entry, tp), max(entry, tp)
    ax.add_patch(patches.Rectangle(
        (box_x, tp_low), box_w, max(tp_high - tp_low, c_span * 0.02),
        linewidth=1.2, edgecolor="#089981", facecolor="#089981", alpha=0.26, zorder=6
    ))

    # Stop Loss Zone (TradingView Coral/Red)
    sl_low, sl_high = min(entry, sl), max(entry, sl)
    ax.add_patch(patches.Rectangle(
        (box_x, sl_low), box_w, max(sl_high - sl_low, c_span * 0.015),
        linewidth=1.2, edgecolor="#f23645", facecolor="#f23645", alpha=0.26, zorder=6
    ))

    # Entry Line + Center Position Pill
    ax.plot((box_x, box_x + box_w), (entry, entry), color="#e2e8f0", linewidth=1.6, zorder=7)
    lbl_text = f"{direction} SETUP • 1:{rr} R:R"
    ax.text(
        box_x + box_w * 0.5, entry, lbl_text,
        color="#ffffff", fontsize=8.5, fontweight="bold", ha="center", va="center",
        bbox=dict(boxstyle="round,pad=0.24", facecolor="#1e293b", edgecolor="#38bdf8", lw=1.2),
        zorder=10
    )
def render_tv_stage_chart(df, tf_label, smc, stage, out_png_path, live_pulse_offset=0.0):
    fig, ax = plt.subplots(figsize=(8.64, 9.12), dpi=125)
    bg_color = "#131722"  # Exact TradingView Dark Theme Canvas
    fig.patch.set_facecolor(bg_color)
    ax.set_facecolor(bg_color)

    opens = df["open"].values.copy()
    highs = df["high"].values.copy()
    lows = df["low"].values.copy()
    closes = df["close"].values.copy()
    n_total = len(df)

    # Simulate live price ticking on the active candle
    live_p = round(float(smc["live_price"]) + live_pulse_offset, 2)
    closes[-1] = live_p
    highs[-1] = max(highs[-1], live_p)
    lows[-1] = min(lows[-1], live_p)

    sup_high = float(smc["supply_high"])
    sup_low = float(smc["supply_low"])
    dem_low = float(smc["demand_low"])
    dem_high = float(smc["demand_high"])
    wz_low = float(smc["watch_low"])
    wz_high = float(smc["watch_high"])
    inv_lvl = float(smc["invalidation"])
    atr = float(smc.get("atr_m15", 6.0))
    is_bull = "BULLISH" in str(smc.get("bias_label", ""))

    bull_tp = round(sup_high + max(atr * 1.1, 6.0), 1)
    bear_tp = round(dem_low - max(atr * 1.1, 6.0), 1)

    c_low = min(float(np.min(lows)), dem_low, inv_lvl if stage >= 5 else dem_low)
    c_high = max(float(np.max(highs)), sup_high, inv_lvl if stage >= 5 else sup_high)
    if stage >= 2:
        c_high = max(c_high, bull_tp)
    if stage >= 3:
        c_low = min(c_low, bear_tp)

    c_span = max(c_high - c_low, 10.0)
    y_min = c_low - c_span * 0.08
    y_max = c_high + c_span * 0.11

    # Subtle Asia Range Box
    a_start, a_end = get_asia_span(df)
    if a_start is not None and tf_label == "15m":
        a_low, a_high = float(smc["asia_low"]), float(smc["asia_high"])
        ax.add_patch(patches.Rectangle(
            (a_start - 0.4, a_low), (a_end - a_start) + 0.8, max(a_high - a_low, 1.5),
            linewidth=1.0, edgecolor="#6366f1", facecolor="#6366f1", alpha=0.11, linestyle="--", zorder=1
        ))
        ax.text(
            a_start + 0.3, a_high + c_span * 0.008, "ASIA LIQUIDITY",
            color="#818cf8", fontsize=8.2, fontweight="bold", va="bottom", zorder=4
        )

    # Authentic TradingView Candlesticks (#089981 Teal & #F23645 Red)
    for i in range(n_total):
        c_val, o_val, h_val, l_val = float(closes[i]), float(opens[i]), float(highs[i]), float(lows[i])
        col = "#089981" if c_val >= o_val else "#f23645"
        ax.plot((i, i), (l_val, h_val), color=col, linewidth=2.0, zorder=3)
        b_bot = min(o_val, c_val)
        b_h = max(abs(c_val - o_val), c_span * 0.011)
        ax.bar(i, b_h, bottom=b_bot, width=0.72, color=col, edgecolor=col, linewidth=0.8, zorder=4)

    x_axis_badge = n_total + 1.8

    # Stage 2+: Supply Zone + Breakout Target
    if stage >= 2:
        sup_h_box = max(sup_high - sup_low, c_span * 0.038)
        ax.add_patch(patches.Rectangle(
            (-0.6, sup_low), n_total + 2.2, sup_h_box,
            linewidth=0, facecolor="#f23645", alpha=0.20, zorder=2
        ))
        ax.axhline(sup_high, color="#f23645", linestyle="--", linewidth=1.4, zorder=5)
        ax.text(1.0, sup_high + c_span * 0.007, "BUY-SIDE LIQUIDITY / SUPPLY", color="#f87171", fontsize=8.4, fontweight="bold", zorder=6)
        ax.text(
            x_axis_badge, sup_high, f" {sup_high:.2f} ",
            color="#ffffff", fontsize=9.2, fontweight="bold", va="center",
            bbox=dict(boxstyle="round,pad=0.20", facecolor="#f23645", edgecolor="none"), zorder=9
        )
        ax.axhline(bull_tp, color="#a855f7", linestyle=":", linewidth=1.2, zorder=5)
        ax.text(1.0, bull_tp + c_span * 0.007, "EXPANSION TARGET", color="#c084fc", fontsize=8.0, fontweight="bold", zorder=6)

    # Stage 3+: Demand Zone + Breakdown Target
    if stage >= 3:
        dem_h_box = max(dem_high - dem_low, c_span * 0.038)
        ax.add_patch(patches.Rectangle(
            (-0.6, dem_low), n_total + 2.2, dem_h_box,
            linewidth=0, facecolor="#089981", alpha=0.20, zorder=2
        ))
        ax.axhline(dem_low, color="#089981", linestyle="--", linewidth=1.4, zorder=5)
        ax.text(1.0, dem_low - c_span * 0.007, "SELL-SIDE LIQUIDITY / DEMAND", color="#34d399", fontsize=8.4, fontweight="bold", va="top", zorder=6)
        ax.text(
            x_axis_badge, dem_low, f" {dem_low:.2f} ",
            color="#ffffff", fontsize=9.2, fontweight="bold", va="center",
            bbox=dict(boxstyle="round,pad=0.20", facecolor="#089981", edgecolor="none"), zorder=9
        )
        ax.axhline(bear_tp, color="#f97316", linestyle=":", linewidth=1.2, zorder=5)
        ax.text(1.0, bear_tp - c_span * 0.007, "DOWNSIDE TARGET", color="#fb923c", fontsize=8.0, fontweight="bold", va="top", zorder=6)

    # Stage 4+: Highlighted Watch Zone + Crosshair Focus
    if stage >= 4:
        wz_h = max(wz_high - wz_low, c_span * 0.042)
        wz_x = max(n_total - 20, 0)
        ax.add_patch(patches.Rectangle(
            (wz_x, wz_low), 21.6, wz_h,
            linewidth=1.6, edgecolor="#facc15", facecolor="#facc15", alpha=0.24, zorder=3
        ))
        ax.text(
            wz_x + 0.6, wz_low + wz_h * 0.5, "KEY WATCH ZONE",
            color="#facc15", fontsize=8.6, fontweight="bold", ha="left", va="center", zorder=8
        )


    # Stage 5: TradingView Risk/Reward Position Tool + Projected Path
    if stage >= 5 and "trade_setup" in smc:
        draw_tv_risk_reward_box(ax, n_total, smc["trade_setup"], c_span)
        wz_mid = (wz_low + wz_high) * 0.5
        target_p = float(smc["trade_setup"]["tp"])
        ax.plot((n_total - 1, n_total + 0.2), (live_p, wz_mid), color="#facc15", linestyle="--", linewidth=2.0, zorder=8)
        ax.annotate(
            "", xy=(n_total + 1.4, target_p), xytext=(n_total + 0.2, wz_mid),
            arrowprops=dict(arrowstyle="->", color="#facc15", lw=2.6, ls="--"), zorder=9
        )

    # Live Price Line & Right-Axis Price Ticker Pill
    live_col = "#089981" if closes[-1] >= opens[-1] else "#f23645"
    ax.axhline(live_p, color=live_col, linestyle=":", linewidth=1.2, alpha=0.85, zorder=5)
    ax.text(
        x_axis_badge, live_p, f" {live_p:.2f} ",
        color="#ffffff", fontsize=9.8, fontweight="bold", va="center",
        bbox=dict(boxstyle="round,pad=0.24", facecolor=live_col, edgecolor="none"),
        zorder=11
    )

    # TradingView Subtle Grid & Right Price Axis
    ax.yaxis.tick_right()
    ax.tick_params(axis="y", colors="#787b86", labelsize=9.6, length=0)
    ax.tick_params(axis="x", colors="#787b86", labelsize=8.6, length=0)
    ax.grid(True, color="#1e222d", linestyle="-", linewidth=0.8, alpha=0.95)

    tick_idxs = list(range(0, n_total, max(n_total // 4, 1)))
    ax.set_xticks(tick_idxs)
    ax.set_xticklabels([df.index[i].strftime("%H:%M") for i in tick_idxs])

    for spine in ("top", "left", "bottom"):
        ax.spines[spine].set_visible(False)
    ax.spines["right"].set_color("#2a2e39")
    ax.spines["right"].set_linewidth(1.0)

    ax.set_ylim(y_min, y_max)
    ax.set_xlim(-0.8, n_total + 5.2)

    plt.subplots_adjust(left=0.015, right=0.855, top=0.945, bottom=0.045)
    plt.savefig(out_png_path, facecolor=bg_color, dpi=125)
    plt.close(fig)

    # Overlay Authentic TradingView Top OHLC Header & Bottom-Left TV Watermark
    img = Image.open(out_png_path).convert("RGB").resize((1040, 1100), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img, "RGBA")
    f_hdr = load_font_safe(FONT_BOLD, 20)
    f_ohlc = load_font_safe(FONT_BOLD, 17)
    f_tv = load_font_safe(FONT_BOLD, 24)

    # Top TradingView Header Strip
    draw.rectangle((0, 0, 1040, 52), fill=(19, 23, 34, 245))
    draw.ellipse((20, 18, 34, 32), fill=(250, 204, 21, 255))
    draw.text((44, 15), f"XAUUSD · {tf_label} · EXNESS", fill=(209, 212, 220, 255), font=f_hdr)

    o_last, h_last, l_last, c_last = opens[-1], highs[-1], lows[-1], closes[-1]
    ohlc_col = (8, 153, 129, 255) if c_last >= o_last else (242, 54, 69, 255)
    ohlc_txt = f"O{o_last:.1f}  H{h_last:.1f}  L{l_last:.1f}  C{c_last:.1f}"
    draw.text((430, 17), ohlc_txt, fill=ohlc_col, font=f_ohlc)

    # Bottom-Left TradingView-style Watermark Badge
    draw.rounded_rectangle((22, 1005, 86, 1045), radius=8, fill=(30, 34, 45, 220))
    draw.text((34, 1012), "TV", fill=(209, 212, 220, 230), font=f_tv)
    img.save(out_png_path)


def build_progressive_chart_stages(smc):
    os.makedirs("assets", exist_ok=True)
    df_15 = load_mt5_candles("xau_m15", bars=38)
    df_5 = load_mt5_candles("xau_m5", bars=38)

    render_tv_stage_chart(df_15, "15m", smc, stage=1, out_png_path="assets/stage_1.png")
    render_tv_stage_chart(df_15, "15m", smc, stage=2, out_png_path="assets/stage_2.png")
    render_tv_stage_chart(df_15, "15m", smc, stage=3, out_png_path="assets/stage_3.png")
    render_tv_stage_chart(df_15, "15m", smc, stage=4, out_png_path="assets/stage_4.png")
    render_tv_stage_chart(df_5, "5m", smc, stage=5, out_png_path="assets/stage_5.png", live_pulse_offset=0.0)
    # Extra live-tick variant for Stage 5 animated pulse
    render_tv_stage_chart(df_5, "5m", smc, stage=5, out_png_path="assets/stage_5b.png", live_pulse_offset=-0.65)
