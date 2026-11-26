import os
import sys
import time
import json
import subprocess
from datetime import datetime, timezone
import requests
import MetaTrader5 as mt5

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
MT5_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
GOLD_SYMBOL = "XAUUSDm"
DXY_SYMBOL = "DXYm"
OUT_FILE = os.path.join(REPO_DIR, "data", "mt5_data.json")
N8N_WEBHOOK_URL = os.environ.get("N8N_MT5_WEBHOOK", "http://localhost:5678/webhook/mt5-push")
MAX_CANDLE_AGE_MINUTES = 25


def wait_for_broker_connection(timeout_sec=25):
    """Wait until MT5 terminal is connected to the broker after PC wake-up."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        info = mt5.terminal_info()
        if info is not None and info.connected:
            return True
        time.sleep(1.5)
    return False


def activate_symbol(symbol):
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"Symbol {symbol} not found in MT5. Check exact spelling in Market Watch.")
    time.sleep(1.0)


def fetch_rates(symbol, timeframe, count):
    for attempt in range(3):
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is not None and len(rates) > 0:
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
        time.sleep(1.5)
    raise RuntimeError(f"No candle data returned for {symbol} after 3 attempts.")


def validate_freshness(xau_m5, force=False):
    """Ensure latest M5 candle is live and market is open."""
    last_bar_dt = datetime.strptime(xau_m5[-1]["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    age_minutes = (datetime.now(timezone.utc) - last_bar_dt).total_seconds() / 60.0
    if age_minutes > MAX_CANDLE_AGE_MINUTES and not force:
        raise RuntimeError(
            f"Stale MT5 data detected: latest M5 candle is {age_minutes:.1f} mins old ({xau_m5[-1]['time']} UTC). "
            f"Market may be closed or MT5 disconnected. Use --force to override."
        )
    return round(age_minutes, 1)


def notify_local_n8n(payload, status="OK", error_msg=""):
    """Non-blocking heartbeat & volatility ping to local n8n Supervisor."""
    try:
        m5 = payload.get("xau_m5", [])
        h1_move = round(m5[-1]["close"] - m5[-12]["open"], 2) if len(m5) >= 12 else 0.0
        event = {
            "status": status,
            "error": error_msg,
            "exported_utc": payload.get("exported_utc"),
            "gold_bid": payload.get("gold_bid"),
            "dxy_bid": payload.get("dxy_bid"),
            "m5_1h_delta": h1_move,
        }
        requests.post(N8N_WEBHOOK_URL, json=event, timeout=2)
    except Exception:
        # Never block Git push if local n8n is offline
        pass


def git_sync_and_push(commit_msg):
    os.chdir(REPO_DIR)
    subprocess.run(["git", "add", "data/mt5_data.json"], check=True)

    diff = subprocess.run(["git", "diff", "--staged", "--quiet"])
    if diff.returncode == 0:
        print("ℹ️ No new candle changes detected.")
        return False

    subprocess.run(["git", "commit", "-m", commit_msg], check=True)

    for attempt in range(3):
        pull = subprocess.run(["git", "pull", "--rebase", "--autostash"], capture_output=True, text=True)
        if pull.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], stderr=subprocess.DEVNULL)
            raise RuntimeError(f"Git pull --rebase failed: {pull.stderr.strip()}")

        push = subprocess.run(["git", "push"], capture_output=True, text=True)
        if push.returncode == 0:
            return True
        print(f"⚠️ Git push retry {attempt + 1}/3: {push.stderr.strip()}")
        time.sleep(3)

    raise RuntimeError("Git push failed after 3 attempts.")


def main():
    force_push = "--force" in sys.argv
    if not mt5.initialize(path=MT5_PATH):
        err = f"MT5 initialize() failed: {mt5.last_error()}"
        notify_local_n8n({}, status="ERROR", error_msg=err)
        raise RuntimeError(err)

    try:
        if not wait_for_broker_connection(timeout_sec=25):
            raise RuntimeError("MT5 terminal opened, but broker connection timed out after 25s.")

        activate_symbol(GOLD_SYMBOL)
        activate_symbol(DXY_SYMBOL)

        xau_h1 = fetch_rates(GOLD_SYMBOL, mt5.TIMEFRAME_H1, 100)
        xau_m15 = fetch_rates(GOLD_SYMBOL, mt5.TIMEFRAME_M15, 220)
        xau_m5 = fetch_rates(GOLD_SYMBOL, mt5.TIMEFRAME_M5, 120)
        dxy_m15 = fetch_rates(DXY_SYMBOL, mt5.TIMEFRAME_M15, 96)

        age_mins = validate_freshness(xau_m5, force=force_push)

        gold_tick = mt5.symbol_info_tick(GOLD_SYMBOL)
        dxy_tick = mt5.symbol_info_tick(DXY_SYMBOL)

        gold_bid = round(float(gold_tick.bid), 2) if (gold_tick and gold_tick.bid > 0) else round(xau_m5[-1]["close"], 2)
        gold_ask = round(float(gold_tick.ask), 2) if (gold_tick and gold_tick.ask > 0) else gold_bid
        dxy_bid = round(float(dxy_tick.bid), 3) if (dxy_tick and dxy_tick.bid > 0) else round(dxy_m15[-1]["close"], 3)

        payload = {
            "exported_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "candle_age_mins": age_mins,
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

        pushed = git_sync_and_push(f"MT5 {GOLD_SYMBOL} data ({payload['exported_utc']} UTC)")
        if pushed:
            print(f"✅ Pushed {GOLD_SYMBOL} ({gold_bid}) & {DXY_SYMBOL} ({dxy_bid}) | Freshness: {age_mins}m")
        notify_local_n8n(payload, status="OK" if pushed else "NO_CHANGE")

    except Exception as e:
        notify_local_n8n({}, status="ERROR", error_msg=str(e))
        raise
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
