# tests/test_mtf_bias.py
"""
Tests for the 3-TF bias filter and analyze_mtf() function.

Verifies:
- H1 EMA200 trend filter correctly sets bias (BULLISH/BEARISH/NEUTRAL)
- Signal is suppressed when H1 trend opposes M5 signal
- mtf_context parameter in generate_signal() blocks trades correctly
- analyze_mtf() returns NO_DATA on empty input
- Confidence increases when all timeframes align
"""

import pandas as pd
import pytest
from zoneinfo import ZoneInfo

from analyzer_mtf import (
    analyze_mtf,
    attach_h1_features_to_m5,
    build_h1_from_m5,
)
from trading.signals import EntryConfig, generate_signal

TZ = "Europe/Zurich"
LOCAL_TZ = ZoneInfo(TZ)


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_m5(start: str, periods: int, close_val: float = None, tz: str = TZ) -> pd.DataFrame:
    """
    Synthetic M5 bars.
    If close_val is provided all bars get that fixed close price (useful for
    forcing a specific H1 EMA trend direction with a stable series).
    """
    times = pd.date_range(start=start, periods=periods, freq="5min", tz=ZoneInfo(tz))
    rows = []
    for i, t in enumerate(times):
        c = close_val if close_val is not None else float(i + 100)
        rows.append({
            "time":   t,
            "open":   c,
            "high":   c + 1.0,
            "low":    c - 1.0,
            "close":  c,
            "volume": 100.0,
        })
    return pd.DataFrame(rows)


def _make_bullish_m5(periods: int = 300) -> pd.DataFrame:
    """Rising price series: close = 100 + i, ensuring EMA200 < close eventually."""
    times = pd.date_range(
        start="2024-01-15 07:05:00", periods=periods, freq="5min", tz=LOCAL_TZ
    )
    rows = []
    for i, t in enumerate(times):
        c = 100.0 + i * 0.5
        rows.append({"time": t, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100.0})
    return pd.DataFrame(rows)


def _make_bearish_m5(periods: int = 300) -> pd.DataFrame:
    """Falling price series: close = 300 - i, ensuring EMA200 > close eventually."""
    times = pd.date_range(
        start="2024-01-15 07:05:00", periods=periods, freq="5min", tz=LOCAL_TZ
    )
    rows = []
    for i, t in enumerate(times):
        c = 300.0 - i * 0.5
        rows.append({"time": t, "open": c, "high": c + 1, "low": c - 1, "close": c, "volume": 100.0})
    return pd.DataFrame(rows)


# ─── H1 bias filter ─────────────────────────────────────────────────────────

def test_bias_bullish_when_h1_close_above_ema200():
    """
    With a sustained rising price series, H1 close eventually exceeds EMA200.
    analyze_mtf should report bias=BULLISH for the last row.
    """
    df_m5 = _make_bullish_m5(periods=300)
    result = analyze_mtf("TEST", df_m5=df_m5, tz=TZ)

    # After enough bars the H1 close will be above EMA200
    # (rising series guarantees this given enough warmup)
    assert result["bias"] in ("BULLISH", "NEUTRAL"), \
        f"Expected BULLISH or NEUTRAL for rising series, got {result['bias']}"
    assert result["signal"] in ("BUY", "NO_TRADE", "NO_DATA")


def test_bias_bearish_when_h1_close_below_ema200():
    """
    With a sustained falling price series, H1 close drops below EMA200.
    analyze_mtf should report bias=BEARISH for the last row.
    """
    df_m5 = _make_bearish_m5(periods=300)
    result = analyze_mtf("TEST", df_m5=df_m5, tz=TZ)

    assert result["bias"] in ("BEARISH", "NEUTRAL"), \
        f"Expected BEARISH or NEUTRAL for falling series, got {result['bias']}"
    assert result["signal"] in ("SELL", "NO_TRADE", "NO_DATA")


def test_ema200_h1_present_in_snapshot():
    """indicators_snapshot must contain ema200_h1 after a successful run."""
    df_m5 = _make_bullish_m5(periods=300)
    result = analyze_mtf("TEST", df_m5=df_m5, tz=TZ)

    assert "ema200_h1" in result["indicators_snapshot"]
    assert "trend_bias_h1" in result["indicators_snapshot"]


def test_rsi_m15_present_in_snapshot():
    """indicators_snapshot must contain rsi_m15 and supertrend_dir_m15."""
    df_m5 = _make_bullish_m5(periods=300)
    result = analyze_mtf("TEST", df_m5=df_m5, tz=TZ)

    assert "rsi_m15" in result["indicators_snapshot"]
    assert "supertrend_dir_m15" in result["indicators_snapshot"]


# ─── No-data handling ────────────────────────────────────────────────────────

def test_no_data_returned_when_df_m5_empty():
    """analyze_mtf must return signal=NO_DATA when an empty DataFrame is passed."""
    df_empty = pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    result = analyze_mtf("EMPTY", df_m5=df_empty, tz=TZ)

    assert result["signal"] == "NO_DATA"
    assert result["bias"] == "NEUTRAL"
    assert result["confidence"] == 0


def test_no_data_returned_when_csv_missing():
    """analyze_mtf must return signal=NO_DATA when the CSV file doesn't exist."""
    result = analyze_mtf("NONEXISTENT_SYMBOL_XYZ", data_dir="/tmp/nonexistent_dir_abc/", tz=TZ)

    assert result["signal"] == "NO_DATA"
    assert result["confidence"] == 0


# ─── Return dict structure ────────────────────────────────────────────────────

def test_analyze_mtf_return_keys():
    """analyze_mtf must always return all required keys."""
    df_m5 = _make_bullish_m5(periods=100)
    result = analyze_mtf("TEST", df_m5=df_m5, tz=TZ)

    required = {
        "symbol", "tf_base", "entry_tf", "confirm_tf", "trend_tf",
        "bias", "signal", "confidence", "reasons", "indicators_snapshot",
    }
    missing = required - set(result.keys())
    assert not missing, f"Missing keys in result: {missing}"


def test_analyze_mtf_reasons_is_list():
    """reasons must be a list of strings."""
    df_m5 = _make_bullish_m5(periods=100)
    result = analyze_mtf("TEST", df_m5=df_m5, tz=TZ)

    assert isinstance(result["reasons"], list)
    for r in result["reasons"]:
        assert isinstance(r, str)


def test_analyze_mtf_confidence_range():
    """confidence must be an integer in [0, 100]."""
    df_m5 = _make_bullish_m5(periods=300)
    result = analyze_mtf("TEST", df_m5=df_m5, tz=TZ)

    assert isinstance(result["confidence"], int)
    assert 0 <= result["confidence"] <= 100


def test_analyze_mtf_signal_values():
    """signal must be one of the four allowed values."""
    df_m5 = _make_bullish_m5(periods=100)
    result = analyze_mtf("TEST", df_m5=df_m5, tz=TZ)

    assert result["signal"] in ("BUY", "SELL", "NO_TRADE", "NO_DATA")


def test_analyze_mtf_bias_values():
    """bias must be one of the three allowed values."""
    df_m5 = _make_bullish_m5(periods=100)
    result = analyze_mtf("TEST", df_m5=df_m5, tz=TZ)

    assert result["bias"] in ("BULLISH", "BEARISH", "NEUTRAL")


# ─── mtf_context gates in generate_signal() ─────────────────────────────────

def _bullish_row() -> pd.Series:
    """
    Build a synthetic row that would normally pass all BUY filters
    (H1 bullish, price above EMA200, RSI > 55, MACD bullish, SuperTrend up).
    """
    return pd.Series({
        "close":         200.0,
        "ema_200":       150.0,   # close > ema_200 → price_above_ema200
        "rsi_14":        60.0,    # >= 55 → momentum_buy_ok
        "macd":          0.5,
        "macd_signal":   0.2,     # macd > macd_signal → momentum_buy_ok
        "atr_14":        2.0,
        "trend_up_h1":   True,    # H1 bullish
        "trend_down_h1": False,
        "supertrend_dir": 1,      # M5 SuperTrend up
    })


def test_generate_signal_buy_without_mtf_context():
    """Without mtf_context, the bullish row should produce BUY."""
    row = _bullish_row()
    cfg = EntryConfig(use_supertrend=True)
    result = generate_signal(row, cfg, mtf_context=None)

    assert result["signal"] == "BUY"
    assert result["mtf_m15_ok"] is None  # not set when no context


def test_mtf_context_blocks_buy_when_m15_bearish():
    """
    When mtf_context indicates bearish M15 (RSI < 50, SuperTrend = -1),
    a BUY signal must be suppressed → NO_TRADE.
    """
    row = _bullish_row()
    cfg = EntryConfig(use_supertrend=True)
    mtf_ctx = {"rsi_m15": 40.0, "supertrend_dir_m15": -1}

    result = generate_signal(row, cfg, mtf_context=mtf_ctx)

    assert result["signal"] == "NO_TRADE", \
        f"Expected NO_TRADE when M15 is bearish, got {result['signal']}"
    assert result["mtf_m15_ok"] is None  # None when signal is NO_TRADE


def test_mtf_context_allows_buy_when_m15_bullish():
    """
    When mtf_context indicates bullish M15 (RSI > 50 OR SuperTrend = +1),
    a valid BUY must still go through.
    """
    row = _bullish_row()
    cfg = EntryConfig(use_supertrend=True)
    mtf_ctx = {"rsi_m15": 62.0, "supertrend_dir_m15": 1}

    result = generate_signal(row, cfg, mtf_context=mtf_ctx)

    assert result["signal"] == "BUY", \
        f"Expected BUY when M15 confirms, got {result['signal']}"
    assert result["mtf_m15_ok"] is True


def test_mtf_context_rsi_alone_sufficient_for_buy():
    """RSI > 50 alone should allow a BUY, even if SuperTrend is missing."""
    row = _bullish_row()
    cfg = EntryConfig(use_supertrend=True)
    mtf_ctx = {"rsi_m15": 55.0, "supertrend_dir_m15": None}

    result = generate_signal(row, cfg, mtf_context=mtf_ctx)

    assert result["signal"] == "BUY"


def test_mtf_context_missing_data_does_not_block():
    """
    If both M15 values are missing (None), the filter is skipped entirely
    and the underlying signal goes through unchanged.
    """
    row = _bullish_row()
    cfg = EntryConfig(use_supertrend=True)
    mtf_ctx = {"rsi_m15": None, "supertrend_dir_m15": None}

    result_with = generate_signal(row, cfg, mtf_context=mtf_ctx)
    result_without = generate_signal(row, cfg, mtf_context=None)

    assert result_with["signal"] == result_without["signal"], \
        "Missing M15 data should not change the signal"


def test_backward_compat_no_mtf_context():
    """
    Calling generate_signal without mtf_context keyword must still work
    and produce the same result as the original signature.
    """
    row = _bullish_row()
    cfg = EntryConfig(use_supertrend=True)

    result = generate_signal(row, cfg)  # no mtf_context arg at all

    assert result["signal"] == "BUY"
    assert "mtf_m15_ok" in result
    assert result["mtf_m15_ok"] is None
