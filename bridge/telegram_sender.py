# bridge/telegram_sender.py
import os
import requests
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo((os.getenv("LOCAL_TZ") or "Europe/Zurich").strip())

def _env(name: str, required: bool = True) -> str:
    v = os.getenv(name, "").strip()
    if required and not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

def _norm(v: Any) -> str:
    return "" if v is None else str(v).strip()

def _parse_dt_any(s: Any) -> Optional[datetime]:
    s = _norm(s)
    if not s:
        return None
    s2 = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s2)
    except Exception:
        try:
            dt = datetime.strptime(s2, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(LOCAL_TZ)

def _fmt_full(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def send_telegram(payload: dict) -> dict:
    token = _env("TG_TOKEN")
    chat_id = _env("TG_CHAT_ID")
    disable_preview = os.getenv("TG_DISABLE_PREVIEW", "1").strip() == "1"

    signal = _norm(payload.get("signal")).upper()
    event = _norm(payload.get("event")).upper()
    symbol = _norm(payload.get("symbol"))
    tf = _norm(payload.get("tf"))
    rr = _norm(payload.get("rr"))

    entry = _norm(payload.get("entry"))
    sl = _norm(payload.get("sl"))
    tp1 = _norm(payload.get("tp1"))
    tp2 = _norm(payload.get("tp2"))
    tp3 = _norm(payload.get("tp3"))

    server_dt = _parse_dt_any(payload.get("server_time")) or _parse_dt_any(payload.get("time"))
    time_str = _fmt_full(server_dt) if server_dt else _norm(payload.get("server_time") or payload.get("time") or "")

    top_emoji = "📈" if signal == "SELL" else "📉" if signal == "BUY" else "📌"

    lines = []
    lines.append(f"{top_emoji} {signal}".strip())
    lines.append("")
    lines.append(f"⚱️ {symbol}".strip())
    lines.append(f"⏱️ {tf}".strip())
    lines.append("")
    lines.append(f"✅ Event: {event}".strip())
    lines.append("")
    if entry:
        lines.append(f"🎯 Entry: {entry}")
    if sl:
        lines.append(f"💸 SL: {sl}")
    lines.append("")
    if tp1:
        lines.append(f"🥉TP1: {tp1}")
    if tp2:
        lines.append(f"🥈TP2: {tp2}")
    if tp3:
        lines.append(f"🥇TP3: {tp3}")
    lines.append("")
    if rr:
        lines.append(f"🧩ARR: {rr}")
    if time_str:
        lines.append(f"⏰Time: {time_str}")

    text = "\n".join([x for x in lines if x is not None]).strip()

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": disable_preview,
        },
        timeout=20,
    )
    if not r.ok:
        raise RuntimeError(f"Telegram error: {r.status_code} {r.text}")
    return {"ok": True}