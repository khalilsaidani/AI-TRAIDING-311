# bridge/write_signal.py
import json
import os
from datetime import datetime

import pandas as pd

from indicators.indicators import add_indicators
from trading.h1_trend import build_h1_trend_from_m5
from trading.signals import EntryConfig, explain_signal
from bridge.telegram_sender import send_signal


CSV_PATH = "data/xauusd_m5.csv"
OUT_PATH = "data/signal.json"


def _safe_float(x, fallback=None):
    try:
        if x is None:
            return fallback
        return float(x)
    except Exception:
        return fallback


def save_signal_to_file(signal: str, sl, tp, entry, timeframe: str = "M5", path: str = OUT_PATH):
    payload = {
        "time_utc": datetime.utcnow().isoformat(),
        "timeframe": timeframe,
        "signal": signal,
        "entry": _safe_float(entry),
        "sl": _safe_float(sl),
        "tp": _safe_float(tp),
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"✅ Saved: {path}")
    print(payload)


def build_message(symbol: str, tf: str, signal: str, entry, sl, tp) -> str:
    def fmt(v):
        return "-" if v is None else f"{float(v):.2f}"

    emoji = "🟢" if signal == "BUY" else ("🔴" if signal == "SELL" else "⚪️")
    return (
        f"<b>{emoji} {symbol} ({tf})</b>\n\n"
        f"<b>Signal:</b> {signal}\n"
        f"<b>Entry:</b> {fmt(entry)}\n"
        f"<b>SL:</b> {fmt(sl)}\n"
        f"<b>TP:</b> {fmt(tp)}\n\n"
        f"🤖 AI-Trading Bot"
    )


def main():
    df = pd.read_csv(CSV_PATH)
    df.columns = [c.lower().strip() for c in df.columns]

    needed = {"time", "open", "high", "low", "close"}
    if not needed.issubset(set(df.columns)):
        raise ValueError(f"CSV missing columns. Need: {sorted(list(needed))}")

    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)

    # 1) مؤشرات M5
    df = add_indicators(df)

    # 2) ترند H1 مبني من M5
    df = build_h1_trend_from_m5(df)

    # 3) إعدادات الدخول
    cfg = EntryConfig(
        rr=2.0,
        sl_atr_mult=1.0,
        risk_per_trade=0.01,
        rsi_buy_min=55.0,
        rsi_sell_max=45.0,
        use_supertrend=True,
        supertrend_buy_dir=1,
        supertrend_sell_dir=-1,
    )

    # 4) استخراج السيغنال
    exp = explain_signal(df, cfg=cfg)
    signal = exp.get("signal", "NO_TRADE")
    entry = exp.get("entry", df.iloc[-1]["close"])
    sl = exp.get("sl", None)
    tp = exp.get("tp", None)

    # لو NO_TRADE خلّي SL/TP None
    if signal == "NO_TRADE":
        sl, tp = None, None

    # 5) اكتب JSON
    save_signal_to_file(signal, sl, tp, entry, timeframe="M5")

    # 6) ابعث تيليغرام
    msg = build_message("GOLD-XAUUSD", "H1", signal, entry, sl, tp)
    send_signal(msg)
    print("✅ Telegram sent")


if __name__ == "__main__":
    main()