import pandas as pd
import numpy as np

# =========================
# Helpers
# =========================
def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    return atr

def _macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    macd = ema_fast - ema_slow
    macd_signal = _ema(macd, signal)
    hist = macd - macd_signal
    return macd, macd_signal, hist

def _supertrend(df: pd.DataFrame, atr_period: int = 10, multiplier: float = 3.0):
    high = df["high"]
    low = df["low"]
    close = df["close"]

    atr = _atr(df, atr_period)
    hl2 = (high + low) / 2.0

    basic_ub = hl2 + multiplier * atr
    basic_lb = hl2 - multiplier * atr

    final_ub = basic_ub.copy()
    final_lb = basic_lb.copy()

    for i in range(1, len(df)):
        final_ub.iloc[i] = (
            basic_ub.iloc[i]
            if (basic_ub.iloc[i] < final_ub.iloc[i-1]) or (close.iloc[i-1] > final_ub.iloc[i-1])
            else final_ub.iloc[i-1]
        )
        final_lb.iloc[i] = (
            basic_lb.iloc[i]
            if (basic_lb.iloc[i] > final_lb.iloc[i-1]) or (close.iloc[i-1] < final_lb.iloc[i-1])
            else final_lb.iloc[i-1]
        )

    st = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)  # +1 up, -1 down

    st.iloc[0] = final_ub.iloc[0]
    direction.iloc[0] = -1

    for i in range(1, len(df)):
        if st.iloc[i-1] == final_ub.iloc[i-1]:
            if close.iloc[i] <= final_ub.iloc[i]:
                st.iloc[i] = final_ub.iloc[i]
                direction.iloc[i] = -1
            else:
                st.iloc[i] = final_lb.iloc[i]
                direction.iloc[i] = +1
        else:
            if close.iloc[i] >= final_lb.iloc[i]:
                st.iloc[i] = final_lb.iloc[i]
                direction.iloc[i] = +1
            else:
                st.iloc[i] = final_ub.iloc[i]
                direction.iloc[i] = -1

    return st, direction

# =========================
# Candlestick Patterns
# =========================
def _add_candles(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    o = out["open"]
    h = out["high"]
    l = out["low"]
    c = out["close"]

    prev_o = o.shift(1)
    prev_c = c.shift(1)

    body = (c - o).abs()
    rng = (h - l).replace(0, np.nan)

    upper_wick = h - np.maximum(o, c)
    lower_wick = np.minimum(o, c) - l

    # Engulfing
    prev_bear = prev_c < prev_o
    prev_bull = prev_c > prev_o
    curr_bull = c > o
    curr_bear = c < o

    out["bull_engulf"] = (prev_bear & curr_bull & (o < prev_c) & (c > prev_o)).fillna(False)
    out["bear_engulf"] = (prev_bull & curr_bear & (o > prev_c) & (c < prev_o)).fillna(False)

    # Pin bars (simple rules)
    # Bull pin: long lower wick, small body, close near top
    out["bull_pin"] = (
        (lower_wick >= 2.0 * body) &
        (upper_wick <= 0.5 * body) &
        (body / rng <= 0.35)
    ).fillna(False)

    # Bear pin: long upper wick, small body, close near bottom
    out["bear_pin"] = (
        (upper_wick >= 2.0 * body) &
        (lower_wick <= 0.5 * body) &
        (body / rng <= 0.35)
    ).fillna(False)

    return out

# =========================
# Public API
# =========================
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Expected columns: time, open, high, low, close, volume (volume optional)
    Adds:
      ema_50, ema_200, rsi_14, atr_14, macd, macd_signal, macd_hist
      supertrend, supertrend_dir
      bull_engulf, bear_engulf, bull_pin, bear_pin
    """
    out = df.copy()

    # normalize column names just in case
    out.columns = [str(c).lower().strip() for c in out.columns]

    # indicators
    out["ema_50"] = _ema(out["close"], 50)
    out["ema_200"] = _ema(out["close"], 200)
    out["rsi_14"] = _rsi(out["close"], 14)
    out["atr_14"] = _atr(out, 14)

    macd, macd_signal, macd_hist = _macd(out["close"], 12, 26, 9)
    out["macd"] = macd
    out["macd_signal"] = macd_signal
    out["macd_hist"] = macd_hist

    st, st_dir = _supertrend(out, atr_period=10, multiplier=3.0)
    out["supertrend"] = st
    out["supertrend_dir"] = st_dir

    # candles
    out = _add_candles(out)

    return out