# webhook_server.py
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# ✅ استدعاء الموديولات متاعك
from bridge.sheets_writer import upsert_trade
from bridge.telegram_sender import send_telegram

load_dotenv()

app = FastAPI()

APP_NAME = os.getenv("APP_NAME", "ai-trading-311-webhook").strip()
DEBUG_MODE = os.getenv("DEBUG_MODE", "0").strip() == "1"

WEBHOOK_SECRET = (os.getenv("WEBHOOK_SECRET") or "").strip()
FORCE_DECIMALS = int((os.getenv("FORCE_DECIMALS") or "5").strip())

LOCAL_TZ_NAME = (os.getenv("LOCAL_TZ") or "Europe/Zurich").strip()
LOCAL_TZ = ZoneInfo(LOCAL_TZ_NAME)


# -----------------------------
# Helpers
# -----------------------------
def _norm(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _to_float(v: Any) -> Optional[float]:
    try:
        s = _norm(v)
        if not s:
            return None
        return float(s)
    except Exception:
        return None


def _round(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    return round(v, FORCE_DECIMALS)


def _calc_rr(entry: Optional[float], sl: Optional[float], tp1: Optional[float]) -> Optional[float]:
    if entry is None or sl is None or tp1 is None:
        return None
    risk = abs(entry - sl)
    if risk == 0:
        return None
    return abs(tp1 - entry) / risk


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


def _now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone(LOCAL_TZ).replace(microsecond=0)


def _fmt_full(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _get_secret(payload: Dict[str, Any], request: Request) -> str:
    # secret في JSON أو header
    s1 = _norm(payload.get("secret"))
    s2 = _norm(request.headers.get("x-webhook-secret"))
    return (s1 or s2).strip()


# -----------------------------
# Routes
# -----------------------------
@app.get("/health")
def health():
    return {
        "ok": True,
        "app": APP_NAME,
        "tz": LOCAL_TZ_NAME,
        "debug": DEBUG_MODE,
    }


@app.post("/tv-webhook")
async def tv_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Server misconfigured: WEBHOOK_SECRET missing")

    secret = _get_secret(payload, request)
    if secret != WEBHOOK_SECRET:
        return JSONResponse(status_code=401, content={"ok": False, "error": "bad secret"})

    event = _norm(payload.get("event")).upper()
    trade_id = _norm(payload.get("trade_id"))

    if not event:
        raise HTTPException(status_code=400, detail="Missing event")
    if not trade_id:
        raise HTTPException(status_code=400, detail="Missing trade_id")

    # --- time normalize ---
    server_dt = _parse_dt_any(payload.get("server_time")) or _parse_dt_any(payload.get("time")) or _now_local()
    server_time_full = _fmt_full(server_dt)

    # --- numeric normalize ---
    entry = _round(_to_float(payload.get("entry")))
    sl = _round(_to_float(payload.get("sl")))
    tp1 = _round(_to_float(payload.get("tp1")))
    tp2 = _round(_to_float(payload.get("tp2")))
    tp3 = _round(_to_float(payload.get("tp3")))

    rr_in = _to_float(payload.get("rr"))
    rr_calc = _calc_rr(entry, sl, tp1)
    rr = _round(rr_in if rr_in is not None else rr_calc)

    cleaned: Dict[str, Any] = {
        "event": event,
        "trade_id": trade_id,
        "symbol": _norm(payload.get("symbol")),
        "tf": _norm(payload.get("tf")),
        "signal": _norm(payload.get("signal")).upper(),
        "strategy": _norm(payload.get("strategy")),
        "server_time": server_time_full,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "rr": rr,
    }

    # ✅ اكتب في Sheets (إجباري)
    sheets_ok = False
    sheets_res: Any = None
    try:
        sheets_res = upsert_trade(cleaned)
        sheets_ok = True
    except Exception as e:
        # لو Sheets طاحت، نرجع error واضح
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": "sheets_failed",
                "detail": str(e),
                "event": event,
                "trade_id": trade_id,
            },
        )

    # ✅ ابعث Telegram (لو فشل، ما نطيّحش السيرفر… نرجع السبب)
    telegram_ok = False
    telegram_error = None
    try:
        send_telegram(cleaned)
        telegram_ok = True
    except Exception as e:
        telegram_error = str(e)

    return {
        "ok": True,
        "event": event,
        "trade_id": trade_id,
        "server_time": server_time_full,
        "sheets_ok": sheets_ok,
        "sheets_res": sheets_res,
        "telegram_ok": telegram_ok,
        "telegram_error": telegram_error,
    }