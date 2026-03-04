# trading/signals.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd


# =========================
# Config
# =========================
@dataclass
class EntryConfig:
    """
    إعدادات الدخول + إدارة المخاطر (Day Trading H1 / Swing …)
    rr            : Risk/Reward (مثلا 2.0 أو 2.5)
    sl_atr_mult   : وقف الخسارة = ATR * multiplier
    risk_per_trade: نسبة المخاطرة من رأس المال في الصفقة (0.01 = 1%)
    """

    rr: float = 2.0
    sl_atr_mult: float = 1.0
    risk_per_trade: float = 0.01

    # فلترات (تنجم تبدّلهم حسب استراتيجيتك)
    rsi_buy_min: float = 55.0
    rsi_sell_max: float = 45.0

    # سوبرترند (إذا تحب تعتمد عليه)
    use_supertrend: bool = True
    supertrend_buy_dir: int = 1   # +1 bullish
    supertrend_sell_dir: int = -1 # -1 bearish


# =========================
# Helpers
# =========================
def safe_get(row: pd.Series, col: str, default=np.nan):
    try:
        return row[col]
    except Exception:
        return default


def _is_valid_number(x) -> bool:
    return x is not None and not (isinstance(x, float) and np.isnan(x))


def _calc_levels(side: str, entry: float, atr: float, cfg: EntryConfig) -> Tuple[Optional[float], Optional[float]]:
    if not (_is_valid_number(entry) and _is_valid_number(atr) and atr > 0):
        return None, None

    sl_dist = atr * cfg.sl_atr_mult
    if side == "BUY":
        sl = entry - sl_dist
        tp = entry + sl_dist * cfg.rr
    else:  # SELL
        sl = entry + sl_dist
        tp = entry - sl_dist * cfg.rr
    return sl, tp


def position_size(account_balance: float, entry: float, sl: float, risk_per_trade: float) -> float:
    """
    حساب حجم الصفقة (وحدات) على أساس:
    risk_amount = balance * risk_per_trade_toggle
    size = risk_amount / abs(entry - sl)

    ملاحظة: هذا حساب "عام" (1$ حركة = 1$). في الفوركس لازم تضيف pip_value/contract_size.
    """
    if not (_is_valid_number(account_balance) and _is_valid_number(entry) and _is_valid_number(sl)):
        return 0.0
    dist = abs(entry - sl)
    if dist <= 0:
        return 0.0
    risk_amount = account_balance * float(risk_per_trade)
    return float(risk_amount / dist)


# =========================
# Core signal logic
# =========================
def generate_signal(
    row: pd.Series,
    cfg: EntryConfig,
    mtf_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    تولّد إشارة على شمعة واحدة (no look-ahead).
    ترجع dict فيه signal + تفاصيل الدخول/SL/TP + debug flags.

    mtf_context (optional)
    ----------------------
    When provided, adds M15 confirmation gate on top of the existing H1 filter.
    Expected keys (all optional; missing/NaN values skip that sub-filter):
      rsi_m15            : float — M15 RSI-14
      supertrend_dir_m15 : int   — M15 SuperTrend direction (+1 / -1)

    Backward compatible: pass mtf_context=None (default) for the original behavior.
    """

    time = safe_get(row, "time", safe_get(row, "timestamp", ""))
    close = safe_get(row, "close", np.nan)

    ema_200 = safe_get(row, "ema_200", np.nan)
    rsi_14 = safe_get(row, "rsi_14", np.nan)
    macd = safe_get(row, "macd", np.nan)
    macd_signal = safe_get(row, "macd_signal", np.nan)
    atr_14 = safe_get(row, "atr_14", np.nan)

    trend_up_h1 = bool(row.get("trend_up_h1", False))
    trend_down_h1 = bool(row.get("trend_down_h1", False))

    supertrend_dir = safe_get(row, "supertrend_dir", None)  # غالبًا +1 / -1

    # derived
    price_above_ema200 = _is_valid_number(close) and _is_valid_number(ema_200) and close > ema_200
    price_below_ema200 = _is_valid_number(close) and _is_valid_number(ema_200) and close < ema_200

    # Momentum (متطابقة تقريبًا مع اللي بان في صورك)
    momentum_buy_ok = (
        _is_valid_number(rsi_14) and _is_valid_number(macd) and _is_valid_number(macd_signal)
        and (rsi_14 >= cfg.rsi_buy_min)
        and (macd > macd_signal)
    )
    momentum_sell_ok = (
        _is_valid_number(rsi_14) and _is_valid_number(macd) and _is_valid_number(macd_signal)
        and (rsi_14 <= cfg.rsi_sell_max)
        and (macd < macd_signal)
    )

    # SuperTrend filter
    supertrend_buy_ok = True
    supertrend_sell_ok = True
    if cfg.use_supertrend:
        supertrend_buy_ok = (supertrend_dir == cfg.supertrend_buy_dir)
        supertrend_sell_ok = (supertrend_dir == cfg.supertrend_sell_dir)

    # M15 confirmation gate (only active when mtf_context is provided)
    mtf_m15_ok: Optional[bool] = None
    if mtf_context is not None:
        rsi_m15    = mtf_context.get("rsi_m15")
        st_dir_m15 = mtf_context.get("supertrend_dir_m15")

        rsi_ok_buy  = (rsi_m15 is not None and _is_valid_number(rsi_m15) and rsi_m15 > 50)
        rsi_ok_sell = (rsi_m15 is not None and _is_valid_number(rsi_m15) and rsi_m15 < 50)
        st_ok_buy   = (st_dir_m15 is not None and st_dir_m15 == 1)
        st_ok_sell  = (st_dir_m15 is not None and st_dir_m15 == -1)

        # If no M15 data at all, skip filter (don't block on missing data)
        has_m15_data = (rsi_m15 is not None and _is_valid_number(rsi_m15)) or st_dir_m15 is not None
        mtf_buy_ok  = (rsi_ok_buy  or st_ok_buy)  if has_m15_data else True
        mtf_sell_ok = (rsi_ok_sell or st_ok_sell) if has_m15_data else True
    else:
        mtf_buy_ok  = True
        mtf_sell_ok = True

    # قواعد الدخول (Day Trading H1) + optional M15 gate
    buy_ok  = trend_up_h1   and price_above_ema200 and momentum_buy_ok  and supertrend_buy_ok  and mtf_buy_ok
    sell_ok = trend_down_h1 and price_below_ema200 and momentum_sell_ok and supertrend_sell_ok and mtf_sell_ok

    signal = "NO_TRADE"
    side = None

    if buy_ok and not sell_ok:
        signal = "BUY"
        side = "BUY"
        if mtf_context is not None:
            mtf_m15_ok = mtf_buy_ok
    elif sell_ok and not buy_ok:
        signal = "SELL"
        side = "SELL"
        if mtf_context is not None:
            mtf_m15_ok = mtf_sell_ok

    entry = float(close) if _is_valid_number(close) else None
    sl, tp = (None, None)
    if side is not None and entry is not None:
        sl, tp = _calc_levels(side, entry, atr_14, cfg)

    return {
        "time": time,
        "close": close,
        "ema_200": ema_200,
        "rsi_14": rsi_14,
        "macd": macd,
        "macd_signal": macd_signal,
        "atr_14": atr_14,
        "trend_up_h1": trend_up_h1,
        "trend_down_h1": trend_down_h1,
        "price_above_ema200": price_above_ema200,
        "price_below_ema200": price_below_ema200,
        "supertrend_dir": supertrend_dir,
        "supertrend_buy_ok": supertrend_buy_ok,
        "supertrend_sell_ok": supertrend_sell_ok,
        "momentum_buy_ok": momentum_buy_ok,
        "momentum_sell_ok": momentum_sell_ok,
        "mtf_m15_ok": mtf_m15_ok,
        "BUY_OK": buy_ok,
        "SELL_OK": sell_ok,
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": cfg.rr,
        "sl_atr_mult": cfg.sl_atr_mult,
        "risk_per_trade": cfg.risk_per_trade,
    }


def explain_signal(df: pd.DataFrame, cfg: EntryConfig, row_index: Optional[int] = None) -> Dict[str, Any]:
    """
    Debug شرح الصفقة على Row معيّن.
    """
    if df is None or len(df) == 0:
        print("❌ df فارغ")
        return {}

    if row_index is None:
        row_index = len(df) - 1

    row_index = max(0, min(int(row_index), len(df) - 1))
    row = df.iloc[row_index]
    dbg = generate_signal(row, cfg)

    print("\n=== SIGNAL DEBUG (Day Trading H1) ===")
    print("time:", dbg.get("time"))
    print("close:", dbg.get("close"))
    print("ema_200:", dbg.get("ema_200"))
    print("rsi_14:", dbg.get("rsi_14"))
    print("macd:", dbg.get("macd"))
    print("macd_signal:", dbg.get("macd_signal"))
    print("atr_14:", dbg.get("atr_14"))
    print("trend_up_h1:", dbg.get("trend_up_h1"))
    print("trend_down_h1:", dbg.get("trend_down_h1"))
    print("price_above_ema200:", dbg.get("price_above_ema200"))
    print("price_below_ema200:", dbg.get("price_below_ema200"))
    print("supertrend_dir:", dbg.get("supertrend_dir"))
    print("momentum_buy_ok:", dbg.get("momentum_buy_ok"))
    print("momentum_sell_ok:", dbg.get("momentum_sell_ok"))
    print("BUY_OK:", dbg.get("BUY_OK"))
    print("SELL_OK:", dbg.get("SELL_OK"))
    print("✅ FINAL SIGNAL:", dbg.get("signal"))

    if dbg.get("signal") in ("BUY", "SELL"):
        print("entry:", dbg.get("entry"))
        print("sl:", dbg.get("sl"))
        print("tp:", dbg.get("tp"))
        print("rr:", dbg.get("rr"), "| sl_atr_mult:", dbg.get("sl_atr_mult"), "| risk_per_trade:", dbg.get("risk_per_trade"))

    return dbg


def build_signals_no_lookahead(df: pd.DataFrame, cfg: EntryConfig, warmup: int = 200) -> pd.DataFrame:
    """
    تبني signals على كامل df بدون look-ahead:
    كل صف يعتمد كان على المؤشرات الموجودة في نفس الصف.
    """
    if df is None or len(df) == 0:
        return df

    out = df.copy()
    n = len(out)
    warmup = int(warmup) if warmup is not None else 0
    warmup = max(0, min(warmup, n - 1))

    # أعمدة الإشارات
    out["signal"] = "NO_TRADE"
    out["entry"] = np.nan
    out["sl"] = np.nan
    out["tp"] = np.nan
    out["rr"] = float(cfg.rr)
    out["sl_atr_mult"] = float(cfg.sl_atr_mult)
    out["risk_per_trade"] = float(cfg.risk_per_trade)

    # Debug booleans (اختياري)
    out["BUY_OK"] = False
    out["SELL_OK"] = False
    out["momentum_buy_ok"] = False
    out["momentum_sell_ok"] = False

    for i in range(warmup, n):
        row = out.iloc[i]
        sig = generate_signal(row, cfg)

        out.at[out.index[i], "signal"] = sig["signal"]
        out.at[out.index[i], "BUY_OK"] = bool(sig["BUY_OK"])
        out.at[out.index[i], "SELL_OK"] = bool(sig["SELL_OK"])
        out.at[out.index[i], "momentum_buy_ok"] = bool(sig["momentum_buy_ok"])
        out.at[out.index[i], "momentum_sell_ok"] = bool(sig["momentum_sell_ok"])

        if sig["signal"] in ("BUY", "SELL"):
            out.at[out.index[i], "entry"] = sig["entry"] if sig["entry"] is not None else np.nan
            out.at[out.index[i], "sl"] = sig["sl"] if sig["sl"] is not None else np.nan
            out.at[out.index[i], "tp"] = sig["tp"] if sig["tp"] is not None else np.nan

    return out