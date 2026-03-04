# analyzer_mtf.py
"""
Multi-timeframe helpers.

Convention
----------
df_m5['time'] is the bar CLOSE time (TradingView/exchange default).
  M5 bar closing at 09:05 covers 09:00–09:05.

Resampling: closed='right', label='right'
  H1 bar labeled 10:00 captures M5 bars whose close time is in (09:00, 10:00].
  → H1 bar at 10:00 represents the 09:00–10:00 candle.  No lookahead: EMA/RSI etc. on row T use only rows 0..T.

  M15 bar labeled 09:15 captures M5 bars whose close time is in (09:00, 09:15].
  → M15 bar at 09:15 represents the 09:00–09:15 candle.
"""

import logging
import os
from typing import Optional

import pandas as pd
from zoneinfo import ZoneInfo

from indicators.indicators import add_indicators

logger = logging.getLogger(__name__)

_OHLCV_COLS = ["open", "high", "low", "close", "volume"]


# ═══════════════════════════════════════════════════════════════════════════════
# H1 helpers (unchanged)
# ═══════════════════════════════════════════════════════════════════════════════

def attach_h1_features_to_m5(df_m5: pd.DataFrame, df_h1: pd.DataFrame) -> pd.DataFrame:
    """
    Attach H1 indicator features to each M5 bar, using the last CLOSED H1 bar.

    Mapping rule (no lookahead)
    ---------------------------
    df_h1 is right-labeled: the bar at 10:00 is the 09:00–10:00 candle.
    merge_asof(direction='backward') finds the latest H1 bar whose close
    time <= M5 bar time, which gives:

      M5 at 10:00 → H1 10:00  (the 09:00-10:00 bar just closed — safe to use)
      M5 at 10:05 → H1 10:00
      M5 at 10:59 → H1 10:00
      M5 at 11:00 → H1 11:00

    M5 bars that precede all H1 bars get NaN for the H1 columns.

    Parameters
    ----------
    df_m5 : DataFrame with a 'time' column (tz-aware).
    df_h1 : DataFrame indexed by H1 bar close time (output of build_h1_from_m5).

    Returns
    -------
    df_m5 enriched with three new columns:
      ema200_h1  : float  — H1 EMA-200 value at the last closed H1 bar
      trend_h1   : bool   — True if H1 close > H1 EMA-200
      trend_bias : int    — +1 (bullish) or -1 (bearish)
    """
    # Build a lean H1 feature table with time as a plain column
    h1 = df_h1[["close", "ema_200"]].copy()
    h1["ema200_h1"]  = h1["ema_200"]
    h1["trend_h1"]   = h1["close"] > h1["ema_200"]
    h1["trend_bias"] = h1["trend_h1"].map({True: 1, False: -1}).astype(int)
    h1 = (
        h1[["ema200_h1", "trend_h1", "trend_bias"]]
        .reset_index()          # index 'time' → column
        .sort_values("time")
        .reset_index(drop=True)
    )

    left = df_m5.copy().sort_values("time").reset_index(drop=True)

    # merge_asof requires identical datetime dtypes (same tz object).
    # Convert H1 time to match M5's tz so named-tz and fixed-offset tzs don't clash.
    m5_tz = left["time"].dt.tz
    if m5_tz is not None:
        h1["time"] = h1["time"].dt.tz_convert(m5_tz)
    else:
        h1["time"] = h1["time"].dt.tz_localize(None)

    # For each M5 row, find the latest H1 row where h1.time <= m5.time
    merged = pd.merge_asof(left, h1, on="time", direction="backward")
    return merged


def build_h1_from_m5(df_m5: pd.DataFrame, tz: str = "Europe/Zurich") -> pd.DataFrame:
    """
    Resample M5 OHLCV bars into H1 bars and attach H1 indicators.

    Parameters
    ----------
    df_m5 : DataFrame
        Required columns: time, open, high, low, close, volume.
        'time' may be tz-naive (treated as *tz*) or tz-aware (converted to *tz*).
    tz : str
        IANA timezone name for the output index.

    Returns
    -------
    df_h1 : DataFrame
        Index  : H1 bar close time, tz-aware in *tz*.
        Columns: open, high, low, close, volume (if present),
                 + all columns produced by add_indicators()
                 (ema_50, ema_200, rsi_14, atr_14, macd, …).
    """
    local_tz = ZoneInfo(tz)

    df = df_m5.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    # ── 1. Normalise 'time' to tz-aware ─────────────────────────────────────
    df["time"] = pd.to_datetime(df["time"])
    if df["time"].dt.tz is None:
        df["time"] = df["time"].dt.tz_localize(local_tz)
    else:
        df["time"] = df["time"].dt.tz_convert(local_tz)

    df = df.sort_values("time").reset_index(drop=True)

    # ── 2. Resample in UTC to avoid DST gaps/duplicates ──────────────────────
    df_utc = df.set_index(df["time"].dt.tz_convert("UTC")).drop(columns=["time"])

    has_volume = "volume" in df_utc.columns
    agg_rules: dict = {
        "open":  ("open",  "first"),
        "high":  ("high",  "max"),
        "low":   ("low",   "min"),
        "close": ("close", "last"),
    }
    if has_volume:
        agg_rules["volume"] = ("volume", "sum")

    # closed='right': bar boundary is the right edge (bar close time included)
    # label='right' : bar is labeled with its right (close) edge
    # → H1 bar at 10:00 UTC = M5 bars whose UTC close ∈ (09:00, 10:00]
    df_h1 = (
        df_utc
        .resample("1h", closed="right", label="right")
        .agg(**agg_rules)
        .dropna(subset=["open", "close"])   # drop empty slots with no M5 data
    )

    # ── 3. Convert index back to local tz ────────────────────────────────────
    df_h1.index = df_h1.index.tz_convert(local_tz)
    df_h1.index.name = "time"

    # ── 4. Compute indicators (chronological order → no lookahead) ───────────
    df_h1 = add_indicators(df_h1.reset_index()).set_index("time")

    return df_h1


# ═══════════════════════════════════════════════════════════════════════════════
# M15 helpers (new)
# ═══════════════════════════════════════════════════════════════════════════════

def build_m15_from_m5(df_m5: pd.DataFrame, tz: str = "Europe/Zurich") -> pd.DataFrame:
    """
    Resample M5 OHLCV bars into M15 bars and attach M15 indicators.

    Same DST-safe UTC pattern as build_h1_from_m5.
    closed='right', label='right' → M15 bar at 09:15 captures M5 bars in (09:00, 09:15].

    Parameters
    ----------
    df_m5 : DataFrame with columns time, open, high, low, close, volume.
    tz    : IANA timezone name for the output index.

    Returns
    -------
    df_m15 : DataFrame
        Index  : M15 bar close time, tz-aware in *tz*.
        Columns: open, high, low, close, volume (if present),
                 + all columns produced by add_indicators().
    """
    local_tz = ZoneInfo(tz)

    df = df_m5.copy()
    df.columns = [str(c).lower().strip() for c in df.columns]

    # ── 1. Normalise 'time' to tz-aware ─────────────────────────────────────
    df["time"] = pd.to_datetime(df["time"])
    if df["time"].dt.tz is None:
        df["time"] = df["time"].dt.tz_localize(local_tz)
    else:
        df["time"] = df["time"].dt.tz_convert(local_tz)

    df = df.sort_values("time").reset_index(drop=True)

    # ── 2. Resample in UTC to avoid DST gaps/duplicates ──────────────────────
    df_utc = df.set_index(df["time"].dt.tz_convert("UTC")).drop(columns=["time"])

    has_volume = "volume" in df_utc.columns
    agg_rules: dict = {
        "open":  ("open",  "first"),
        "high":  ("high",  "max"),
        "low":   ("low",   "min"),
        "close": ("close", "last"),
    }
    if has_volume:
        agg_rules["volume"] = ("volume", "sum")

    df_m15 = (
        df_utc
        .resample("15min", closed="right", label="right")
        .agg(**agg_rules)
        .dropna(subset=["open", "close"])
    )

    # ── 3. Convert index back to local tz ────────────────────────────────────
    df_m15.index = df_m15.index.tz_convert(local_tz)
    df_m15.index.name = "time"

    # ── 4. Compute indicators ────────────────────────────────────────────────
    df_m15 = add_indicators(df_m15.reset_index()).set_index("time")

    return df_m15


def attach_m15_features_to_m5(df_m5: pd.DataFrame, df_m15: pd.DataFrame) -> pd.DataFrame:
    """
    Attach M15 indicator features to each M5 bar, using the last CLOSED M15 bar.

    Mapping rule (no lookahead)
    ---------------------------
      M5 at 09:15 → M15 09:15  (the 09:00-09:15 bar just closed — safe to use)
      M5 at 09:20 → M15 09:15
      M5 at 09:29 → M15 09:15
      M5 at 09:30 → M15 09:30

    M5 bars that precede all M15 bars get NaN for the M15 columns.

    Parameters
    ----------
    df_m5  : DataFrame with a 'time' column (tz-aware).
    df_m15 : DataFrame indexed by M15 bar close time (output of build_m15_from_m5).

    Returns
    -------
    df_m5 enriched with four new columns:
      rsi_14_m15         : float — M15 RSI-14
      supertrend_dir_m15 : int   — M15 SuperTrend direction (+1 up, -1 down)
      ema200_m15         : float — M15 EMA-200
      trend_bias_m15     : int   — +1 (bullish) or -1 (bearish) from M15 close vs EMA-200
    """
    m15 = df_m15[["close", "ema_200", "rsi_14", "supertrend_dir"]].copy()
    m15["ema200_m15"]         = m15["ema_200"]
    m15["rsi_14_m15"]         = m15["rsi_14"]
    m15["supertrend_dir_m15"] = m15["supertrend_dir"]
    m15["trend_bias_m15"]     = (m15["close"] > m15["ema_200"]).map({True: 1, False: -1}).astype(int)
    m15 = (
        m15[["ema200_m15", "rsi_14_m15", "supertrend_dir_m15", "trend_bias_m15"]]
        .reset_index()
        .sort_values("time")
        .reset_index(drop=True)
    )

    left = df_m5.copy().sort_values("time").reset_index(drop=True)

    # Align tz types for merge_asof
    m5_tz = left["time"].dt.tz
    if m5_tz is not None:
        m15["time"] = m15["time"].dt.tz_convert(m5_tz)
    else:
        m15["time"] = m15["time"].dt.tz_localize(None)

    merged = pd.merge_asof(left, m15, on="time", direction="backward")
    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# 3-Timeframe Analyzer
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_mtf(
    symbol: str,
    tf_base: str = "5m",
    *,
    df_m5: Optional[pd.DataFrame] = None,
    cfg=None,
    data_dir: Optional[str] = None,
    tz: str = "Europe/Zurich",
) -> dict:
    """
    Run a 3-timeframe analysis: M5 entry signals, M15 confirmation, H1 trend filter.

    Parameters
    ----------
    symbol   : Instrument symbol, e.g. "XAUUSD".
    tf_base  : Base timeframe string (default "5m"). Used for CSV lookup when df_m5 is None.
    df_m5    : Optional DataFrame with M5 OHLCV data. If None, tries to load from
               {data_dir}/{symbol.lower()}_{tf_base}.csv
    cfg      : Optional EntryConfig. Defaults to EntryConfig().
    data_dir : Directory to search for CSV files. Defaults to env MTF_DATA_DIR or "data/".
    tz       : IANA timezone for resampling (default "Europe/Zurich").

    Returns
    -------
    dict with keys:
      symbol, tf_base, entry_tf, confirm_tf, trend_tf,
      bias (BULLISH/BEARISH/NEUTRAL),
      signal (BUY/SELL/NO_TRADE/NO_DATA),
      confidence (0-100),
      reasons (list[str]),
      indicators_snapshot (dict)
    """
    from trading.signals import EntryConfig, generate_signal

    if cfg is None:
        cfg = EntryConfig()

    _no_data: dict = {
        "symbol": symbol,
        "tf_base": tf_base,
        "entry_tf": "M5",
        "confirm_tf": "M15",
        "trend_tf": "H1",
        "bias": "NEUTRAL",
        "signal": "NO_DATA",
        "confidence": 0,
        "reasons": ["No M5 data available"],
        "indicators_snapshot": {},
    }

    # ── 1. Load data if not provided ─────────────────────────────────────────
    if df_m5 is None:
        if data_dir is None:
            data_dir = os.getenv("MTF_DATA_DIR", "data/").strip()
        csv_path = os.path.join(data_dir, f"{symbol.lower()}_{tf_base}.csv")
        if not os.path.exists(csv_path):
            logger.warning("analyze_mtf: CSV not found at %s", csv_path)
            return _no_data
        try:
            df_m5 = pd.read_csv(csv_path)
            df_m5.columns = [str(c).lower().strip() for c in df_m5.columns]
            df_m5["time"] = pd.to_datetime(df_m5["time"])
            df_m5 = df_m5.sort_values("time").reset_index(drop=True)
        except Exception:
            logger.exception("analyze_mtf: failed to load CSV %s", csv_path)
            return _no_data

    if df_m5 is None or len(df_m5) == 0:
        return _no_data

    # ── 2. Build higher timeframes ────────────────────────────────────────────
    try:
        df_h1  = build_h1_from_m5(df_m5, tz=tz)
        df_m15 = build_m15_from_m5(df_m5, tz=tz)
    except Exception:
        logger.exception("analyze_mtf: failed to build H1/M15")
        return {**_no_data, "reasons": ["Failed to build higher timeframes"]}

    # ── 3. Add M5 indicators and attach higher-TF features ───────────────────
    try:
        df = add_indicators(df_m5.copy())
        df = attach_h1_features_to_m5(df, df_h1)   # → ema200_h1, trend_h1, trend_bias
        df = attach_m15_features_to_m5(df, df_m15)  # → rsi_14_m15, supertrend_dir_m15, trend_bias_m15
    except Exception:
        logger.exception("analyze_mtf: failed to attach MTF features")
        return {**_no_data, "reasons": ["Failed to attach MTF features"]}

    # Bridge column names that generate_signal() expects
    df["trend_up_h1"]   = df["trend_bias"] == 1
    df["trend_down_h1"] = df["trend_bias"] == -1

    # ── 4. Get last M5 row ────────────────────────────────────────────────────
    last_row = df.iloc[-1]

    import numpy as np

    def _safe(val, default=None):
        if val is None:
            return default
        try:
            if isinstance(val, float) and np.isnan(val):
                return default
            return val
        except Exception:
            return default

    rsi_m5         = _safe(last_row.get("rsi_14"))
    macd_m5        = _safe(last_row.get("macd"))
    st_dir_m5      = _safe(last_row.get("supertrend_dir"))
    ema200_h1      = _safe(last_row.get("ema200_h1"))
    trend_bias_h1  = _safe(last_row.get("trend_bias"), 0)
    rsi_m15        = _safe(last_row.get("rsi_14_m15"))
    st_dir_m15     = _safe(last_row.get("supertrend_dir_m15"))

    # ── 5. Build mtf_context and generate signal ──────────────────────────────
    mtf_context = {
        "rsi_m15":            rsi_m15,
        "supertrend_dir_m15": st_dir_m15,
    }

    try:
        sig = generate_signal(last_row, cfg, mtf_context=mtf_context)
    except Exception:
        logger.exception("analyze_mtf: generate_signal failed")
        sig = {"signal": "NO_TRADE"}

    signal = sig.get("signal", "NO_TRADE")

    # ── 6. Determine bias from H1 ─────────────────────────────────────────────
    if trend_bias_h1 == 1:
        bias = "BULLISH"
    elif trend_bias_h1 == -1:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    # ── 7. Build reasons and confidence ──────────────────────────────────────
    reasons = []
    points = 0
    max_points = 4

    # H1 trend
    if trend_bias_h1 == 1:
        ema_str = f"{ema200_h1:.2f}" if ema200_h1 is not None else "n/a"
        reasons.append(f"H1 bullish (EMA200={ema_str})")
        if signal == "BUY":
            points += 1
    elif trend_bias_h1 == -1:
        ema_str = f"{ema200_h1:.2f}" if ema200_h1 is not None else "n/a"
        reasons.append(f"H1 bearish (EMA200={ema_str})")
        if signal == "SELL":
            points += 1
    else:
        reasons.append("H1 trend neutral (insufficient data)")

    # M15 RSI confirmation
    if rsi_m15 is not None:
        if signal == "BUY" and rsi_m15 > 50:
            reasons.append(f"M15 RSI {rsi_m15:.1f} > 50 (confirms BUY)")
            points += 1
        elif signal == "SELL" and rsi_m15 < 50:
            reasons.append(f"M15 RSI {rsi_m15:.1f} < 50 (confirms SELL)")
            points += 1
        elif signal in ("BUY", "SELL"):
            reasons.append(f"M15 RSI {rsi_m15:.1f} does not confirm {signal}")
    else:
        reasons.append("M15 RSI not available")

    # M15 SuperTrend confirmation
    if st_dir_m15 is not None:
        if signal == "BUY" and st_dir_m15 == 1:
            reasons.append("M15 SuperTrend bullish (confirms BUY)")
            points += 1
        elif signal == "SELL" and st_dir_m15 == -1:
            reasons.append("M15 SuperTrend bearish (confirms SELL)")
            points += 1
        elif signal in ("BUY", "SELL"):
            reasons.append(f"M15 SuperTrend dir={st_dir_m15} does not confirm {signal}")
    else:
        reasons.append("M15 SuperTrend not available")

    # M5 SuperTrend
    if st_dir_m5 is not None:
        if signal == "BUY" and st_dir_m5 == 1:
            reasons.append("M5 SuperTrend bullish")
            points += 1
        elif signal == "SELL" and st_dir_m5 == -1:
            reasons.append("M5 SuperTrend bearish")
            points += 1
        elif signal in ("BUY", "SELL"):
            reasons.append(f"M5 SuperTrend dir={st_dir_m5} does not confirm {signal}")

    if signal == "NO_TRADE":
        reasons.append("M5 entry conditions not met")

    confidence = int(round(points / max_points * 100)) if signal in ("BUY", "SELL") else 0

    logger.info(
        "analyze_mtf: symbol=%s signal=%s bias=%s confidence=%d",
        symbol, signal, bias, confidence,
    )

    return {
        "symbol": symbol,
        "tf_base": tf_base,
        "entry_tf": "M5",
        "confirm_tf": "M15",
        "trend_tf": "H1",
        "bias": bias,
        "signal": signal,
        "confidence": confidence,
        "reasons": reasons,
        "indicators_snapshot": {
            "rsi_m5":             rsi_m5,
            "macd_m5":            macd_m5,
            "supertrend_dir_m5":  st_dir_m5,
            "ema200_h1":          ema200_h1,
            "trend_bias_h1":      trend_bias_h1,
            "rsi_m15":            rsi_m15,
            "supertrend_dir_m15": st_dir_m15,
        },
    }
