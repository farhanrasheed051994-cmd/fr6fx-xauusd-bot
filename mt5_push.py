import os
import time
import json
import subprocess
from datetime import datetime, timezone
import MetaTrader5 as mt5

REPO_DIR = r"C:\Projects\FR6_XAUUSD_Automation"
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
GOLD_SYMBOL = "XAUUSDm"
DXY_SYMBOL = "DXYm"
OUT_FILE = os.path.join(REPO_DIR, "data", "mt5_data.json")


def activate_symbol(symbol):
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Symbol {symbol} not found in MT5. Check exact spelling in Market Watch.")
    time.sleep(0.3)


def fetch_rates(symbol, timeframe, count):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No candle data returned for {symbol}.")
    return [
        {
            "time": datetime.fromtimestamp(int(r["time"]), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "open": round(float(r["open"]), 3),
            "high": round(float(r["high"]), 3),
            "low": round(float(r["low"]), 3),
            "close": round(float(r["close"]), 3),
            "volume": int(r["tick_volume"]),
        }
        for r in rates
    ]


def main():
    if not mt5.initialize(path=MT5_PATH):
        raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")

    try:
        activate_symbol(GOLD_SYMBOL)
        activate_symbol(DXY_SYMBOL)

        xau_h1 = fetch_rates(GOLD_SYMBOL, mt5.TIMEFRAME_H1, 100)
        xau_m15 = fetch_rates(GOLD_SYMBOL, mt5.TIMEFRAME_M15, 220)
        xau_m5 = fetch_rates(GOLD_SYMBOL, mt5.TIMEFRAME_M5, 120)
        dxy_m15 = fetch_rates(DXY_SYMBOL, mt5.TIMEFRAME_M15, 96)

        gold_tick = mt5.symbol_info_tick(GOLD_SYMBOL)
        dxy_tick = mt5.symbol_info_tick(DXY_SYMBOL)

        gold_bid = round(float(gold_tick.bid), 2) if (gold_tick and gold_tick.bid > 0) else round(xau_m5[-1]["close"], 2)
        gold_ask = round(float(gold_tick.ask), 2) if (gold_tick and gold_tick.ask > 0) else gold_bid
        dxy_bid = round(float(dxy_tick.bid), 3) if (dxy_tick and dxy_tick.bid > 0) else round(dxy_m15[-1]["close"], 3)

        payload = {
            "exported_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "gold_symbol": GOLD_SYMBOL,
            "dxy_symbol": DXY_SYMBOL,
            "gold_bid": gold_bid,
            "gold_ask": gold_ask,
            "dxy_bid": dxy_bid,
            "xau_h1": xau_h1,
            "xau_m15": xau_m15,
            "xau_m5": xau_m5,
            "dxy_m15": dxy_m15,
        }

        os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
        with open(OUT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

        os.chdir(REPO_DIR)
        subprocess.run(["git", "pull", "--rebase"], check=True)
        subprocess.run(["git", "add", "data/mt5_data.json"], check=True)

        diff = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff.returncode != 0:
            msg = f"MT5 {GOLD_SYMBOL} data ({payload['exported_utc']} UTC)"
            subprocess.run(["git", "commit", "-m", msg], check=True)
            subprocess.run(["git", "push"], check=True)
            print(f"✅ Pushed {GOLD_SYMBOL} ({gold_bid}) & {DXY_SYMBOL} ({dxy_bid}) to GitHub.")
        else:
            print("ℹ️ No new candle changes detected.")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
