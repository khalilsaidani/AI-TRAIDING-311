# bridge/sheets_writer.py
import os
from datetime import datetime, timezone
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials
from zoneinfo import ZoneInfo

EXPECTED_HEADERS = [
    "event","trade_id","symbol","tf","signal","entry","sl","tp1","tp2","tp3","rr",
    "strategy","server_time","tp1_hit_time","tp2_hit_time","tp3_hit_time","sl_hit_time","last_update"
]

LOCAL_TZ = ZoneInfo((os.getenv("LOCAL_TZ") or "Europe/Zurich").strip())

def _env(name: str, required=True) -> str:
    v = os.getenv(name, "").strip()
    if required and not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

def _parse_dt_any(s: object) -> Optional[datetime]:
    s = (str(s).strip() if s is not None else "")
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

def _fmt_hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")

def _get_client():
    creds_path = _env("GOOGLE_CREDS_FILE")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
    return gspread.authorize(creds)

def _get_ws():
    gc = _get_client()
    sid = _env("SPREADSHEET_ID")
    sheet_name = _env("SHEET_NAME")
    sh = gc.open_by_key(sid)
    return sh.worksheet(sheet_name)

def _ensure_headers(ws):
    row1 = ws.row_values(1)
    if not row1 or row1[:len(EXPECTED_HEADERS)] != EXPECTED_HEADERS:
        ws.update("A1", [EXPECTED_HEADERS])
        return EXPECTED_HEADERS
    return row1

def _col_map(headers):
    return {h: i+1 for i, h in enumerate(headers)}

def _find_row_by_trade_id(ws, trade_id: str, trade_col_idx: int):
    col_vals = ws.col_values(trade_col_idx)
    for r, val in enumerate(col_vals[1:], start=2):
        if str(val).strip() == str(trade_id).strip():
            return r
    return None

def _set_cells(ws, row_idx: int, updates: dict, cmap: dict):
    cells = []
    for h, v in updates.items():
        if h not in cmap:
            continue
        cells.append(gspread.Cell(row_idx, cmap[h], "" if v is None else str(v)))
    if cells:
        ws.update_cells(cells, value_input_option="RAW")

def upsert_trade(payload: dict):
    ws = _get_ws()
    headers = _ensure_headers(ws)
    cmap = _col_map(headers)

    trade_id = str(payload.get("trade_id", "")).strip()
    if not trade_id:
        raise RuntimeError("Missing trade_id in payload")

    event = str(payload.get("event", "")).strip().upper()

    server_dt = _parse_dt_any(payload.get("server_time")) or _parse_dt_any(payload.get("time")) or _now_local()
    server_time_full = _fmt_full(server_dt)
    hhmm = _fmt_hhmm(server_dt)

    row_idx = _find_row_by_trade_id(ws, trade_id, cmap["trade_id"])

    updates = {
        "event": event,
        "trade_id": trade_id,
        "server_time": server_time_full,
        "last_update": hhmm,
    }

    if event == "ENTRY":
        for k in ["symbol","tf","signal","entry","sl","tp1","tp2","tp3","rr","strategy"]:
            if k in payload:
                updates[k] = payload.get(k, "")

    if event in ("TP1","TP2","TP3","SL"):
        hit_col = {"TP1":"tp1_hit_time","TP2":"tp2_hit_time","TP3":"tp3_hit_time","SL":"sl_hit_time"}[event]
        updates[hit_col] = f"{event} {hhmm}"
        for k in ["rr","strategy"]:
            if payload.get(k) not in ("", None):
                updates[k] = payload.get(k)

    if row_idx is None:
        row = [""] * len(EXPECTED_HEADERS)
        for h, v in updates.items():
            if h in cmap:
                row[cmap[h]-1] = "" if v is None else str(v)
        ws.append_row(row, value_input_option="RAW")
        return {"ok": True, "action": "append", "trade_id": trade_id}

    _set_cells(ws, row_idx, updates, cmap)
    return {"ok": True, "action": "update", "trade_id": trade_id, "row": row_idx}