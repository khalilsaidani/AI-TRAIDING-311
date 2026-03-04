# webhook_server.py
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import logging

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG_MODE", "0").strip() == "1" else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
# Silence noisy third-party loggers
for _noisy in ("urllib3", "google", "googleapiclient", "gspread"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

# ✅ استدعاء الموديولات متاعك
from bridge.sheets_writer import upsert_trade
from bridge.telegram_sender import send_telegram

load_dotenv()

app = FastAPI()

MAX_BODY_BYTES = 50 * 1024          # 50 KB hard limit on incoming payload
RATE_LIMIT_RPM = 30                 # max requests per minute per IP
_rate_buckets: dict = defaultdict(deque)

def _check_rate(ip: str) -> bool:
    now = time.monotonic()
    dq = _rate_buckets[ip]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= RATE_LIMIT_RPM:
        return False
    dq.append(now)
    return True

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
    client_ip = request.client.host if request.client else "unknown"

    if not _check_rate(client_ip):
        logger.warning("tv_webhook: rate limit exceeded ip=%s", client_ip)
        return JSONResponse(status_code=429, content={"ok": False, "error": "rate_limited"})

    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"ok": False, "error": "payload_too_large"})

    try:
        import json as _json
        payload = _json.loads(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Server misconfigured: WEBHOOK_SECRET missing")

    secret = _get_secret(payload, request)
    logger.debug(
        "tv_webhook: secret check — provided=%s len_provided=%d len_expected=%d",
        bool(secret), len(secret), len(WEBHOOK_SECRET),
    )
    if secret != WEBHOOK_SECRET:
        return JSONResponse(status_code=401, content={"ok": False, "error": "bad secret"})

    VALID_EVENTS = {"ENTRY", "TP1", "TP2", "TP3", "SL"}

    event = _norm(payload.get("event")).upper()
    trade_id = _norm(payload.get("trade_id"))

    if not event:
        raise HTTPException(status_code=400, detail="Missing event")
    if event not in VALID_EVENTS:
        raise HTTPException(status_code=400, detail=f"Invalid event '{event}'. Must be one of: {sorted(VALID_EVENTS)}")
    if not trade_id:
        raise HTTPException(status_code=400, detail="Missing trade_id")
    if event == "ENTRY" and not _norm(payload.get("symbol")):
        raise HTTPException(status_code=400, detail="ENTRY event requires 'symbol'")

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
        logger.debug("tv_webhook: calling upsert_trade event=%s trade_id=%s", event, trade_id)
        sheets_res = upsert_trade(cleaned)
        sheets_ok = True
        logger.debug("tv_webhook: upsert_trade OK res=%s", sheets_res)
    except Exception as e:
        logger.exception("tv_webhook: upsert_trade FAILED event=%s trade_id=%s error=%s", event, trade_id, e)
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