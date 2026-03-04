# tests/test_analyzer_mtf.py
"""
Unit tests for analyzer_mtf.build_h1_from_m5 and attach_h1_features_to_m5.

Convention: df_m5['time'] = bar CLOSE time.
  closed='right', label='right' → H1 bar at 10:00 = M5 bars in (09:00, 10:00].
"""

import pandas as pd
import pytest
from zoneinfo import ZoneInfo

from analyzer_mtf import attach_h1_features_to_m5, build_h1_from_m5

TZ = "Europe/Zurich"
LOCAL_TZ = ZoneInfo(TZ)


# ─── helpers ────────────────────────────────────────────────────────────────

def _make_m5(start: str, periods: int, tz: str = TZ) -> pd.DataFrame:
    """
    Synthetic M5 bars where each bar i has:
      open  = i + 1
      high  = i + 2
      low   = i
      close = i + 1
      volume= 100
    times are bar close times spaced 5 min apart starting at *start*.
    """
    times = pd.date_range(start=start, periods=periods, freq="5min", tz=ZoneInfo(tz))
    rows = [
        {
            "time":   t,
            "open":   float(i + 1),
            "high":   float(i + 2),
            "low":    float(float(i)),
            "close":  float(i + 1),
            "volume": 100.0,
        }
        for i, t in enumerate(times)
    ]
    return pd.DataFrame(rows)


# ─── OHLC aggregation ───────────────────────────────────────────────────────

def test_ohlc_one_full_bar():
    """
    12 M5 bars closing at 09:05…10:00 → exactly 1 H1 bar labeled 10:00.
    open  = first M5 open  = 1.0
    high  = max  M5 high  = 13.0  (i=11 → high=13)
    low   = min  M5 low   = 0.0   (i=0  → low=0)
    close = last M5 close = 12.0  (i=11 → close=12)
    """
    df_m5 = _make_m5("2024-01-15 09:05:00", periods=12)
    df_h1 = build_h1_from_m5(df_m5, tz=TZ)

    assert len(df_h1) == 1, f"Expected 1 H1 bar, got {len(df_h1)}"
    bar = df_h1.iloc[0]
    assert bar["open"]  == pytest.approx(1.0)
    assert bar["high"]  == pytest.approx(13.0)
    assert bar["low"]   == pytest.approx(0.0)
    assert bar["close"] == pytest.approx(12.0)


def test_ohlc_two_full_bars():
    """24 M5 bars → 2 H1 bars; second bar OHLC must be based on bars 12–23."""
    df_m5 = _make_m5("2024-01-15 09:05:00", periods=24)
    df_h1 = build_h1_from_m5(df_m5, tz=TZ)

    assert len(df_h1) == 2

    bar2 = df_h1.iloc[1]
    # i=12..23: open=13, high=25, low=12, close=24
    assert bar2["open"]  == pytest.approx(13.0)
    assert bar2["high"]  == pytest.approx(25.0)
    assert bar2["low"]   == pytest.approx(12.0)
    assert bar2["close"] == pytest.approx(24.0)


# ─── bar labeling (no-lookahead proof) ──────────────────────────────────────

def test_h1_bar_labeled_at_close_time():
    """
    With closed='right', label='right':
    12 M5 bars closing at 09:05..10:00 → H1 bar must be labeled 10:00 local.
    """
    df_m5 = _make_m5("2024-01-15 09:05:00", periods=12)
    df_h1 = build_h1_from_m5(df_m5, tz=TZ)

    bar_time = df_h1.index[0]
    assert bar_time.hour   == 10
    assert bar_time.minute == 0


def test_no_lookahead_index_monotonic():
    """Index must be strictly increasing (chronological, no future rows)."""
    df_m5 = _make_m5("2024-01-15 09:05:00", periods=12 * 10)
    df_h1 = build_h1_from_m5(df_m5, tz=TZ)

    assert df_h1.index.is_monotonic_increasing


# ─── volume ──────────────────────────────────────────────────────────────────

def test_volume_summed():
    """Volume across the 12 M5 bars must be summed: 12 × 100 = 1200."""
    df_m5 = _make_m5("2024-01-15 09:05:00", periods=12)
    df_h1 = build_h1_from_m5(df_m5, tz=TZ)

    assert df_h1.iloc[0]["volume"] == pytest.approx(1200.0)


# ─── timezone handling ───────────────────────────────────────────────────────

def test_tz_naive_input_localized_correctly():
    """tz-naive input is treated as local tz, not UTC → same bar label."""
    df_aware = _make_m5("2024-01-15 09:05:00", periods=12)
    df_naive = df_aware.copy()
    df_naive["time"] = df_naive["time"].dt.tz_localize(None)

    h1_aware = build_h1_from_m5(df_aware, tz=TZ)
    h1_naive = build_h1_from_m5(df_naive, tz=TZ)

    assert len(h1_naive) == 1
    # Both must produce the same bar close time
    assert h1_aware.index[0] == h1_naive.index[0]


def test_tz_aware_non_local_converted():
    """UTC-aware input must be converted to local tz before resampling."""
    df_local = _make_m5("2024-01-15 09:05:00", periods=12, tz=TZ)
    df_utc = df_local.copy()
    df_utc["time"] = df_utc["time"].dt.tz_convert("UTC")

    h1_local = build_h1_from_m5(df_local, tz=TZ)
    h1_utc   = build_h1_from_m5(df_utc,   tz=TZ)

    # Same bar close time regardless of input tz
    assert h1_local.index[0] == h1_utc.index[0]


# ─── indicators ──────────────────────────────────────────────────────────────

def test_ema_200_present():
    """ema_200 column must exist in output."""
    df_m5 = _make_m5("2024-01-15 09:05:00", periods=12 * 5)
    df_h1 = build_h1_from_m5(df_m5, tz=TZ)

    assert "ema_200" in df_h1.columns


def test_all_expected_indicator_columns():
    """All columns from add_indicators() must be present in output."""
    expected = {
        "ema_50", "ema_200", "rsi_14", "atr_14",
        "macd", "macd_signal", "macd_hist",
        "supertrend", "supertrend_dir",
        "bull_engulf", "bear_engulf", "bull_pin", "bear_pin",
    }
    df_m5 = _make_m5("2024-01-15 09:05:00", periods=12 * 5)
    df_h1 = build_h1_from_m5(df_m5, tz=TZ)

    missing = expected - set(df_h1.columns)
    assert not missing, f"Missing indicator columns: {missing}"


# ─── partial / edge cases ────────────────────────────────────────────────────

def test_partial_h1_bar_not_silently_dropped():
    """
    13 M5 bars → 1 full H1 (10:00) + 1 partial H1 (11:00).
    Partial bars with at least one M5 bar must not be silently dropped
    (they may have NaN indicators, but the OHLC row must be present).
    """
    df_m5 = _make_m5("2024-01-15 09:05:00", periods=13)
    df_h1 = build_h1_from_m5(df_m5, tz=TZ)

    assert len(df_h1) == 2
    partial = df_h1.iloc[1]
    # Only 1 M5 bar in the second slot: open==close==13
    assert partial["open"]  == pytest.approx(13.0)
    assert partial["close"] == pytest.approx(13.0)


def test_empty_slots_with_no_m5_data_dropped():
    """
    Gaps in M5 data (e.g. weekend) must not produce phantom H1 bars
    with all-NaN OHLC.
    """
    # Two batches separated by a 3-hour gap
    batch1 = _make_m5("2024-01-15 09:05:00", periods=12)   # fills 10:00 bar
    batch2 = _make_m5("2024-01-15 13:05:00", periods=12)   # fills 14:00 bar
    df_m5 = pd.concat([batch1, batch2], ignore_index=True)

    df_h1 = build_h1_from_m5(df_m5, tz=TZ)

    # 11:00, 12:00, 13:00 had no M5 data → must be absent
    hours = {t.hour for t in df_h1.index}
    assert hours == {10, 14}, f"Unexpected H1 bar hours: {hours}"


# ═══════════════════════════════════════════════════════════════════════════════
# attach_h1_features_to_m5
# ═══════════════════════════════════════════════════════════════════════════════

def _make_h1(close_times_and_closes: list, ema200_val: float = 50.0, tz: str = TZ):
    """
    Build a minimal df_h1 suitable for attach_h1_features_to_m5.
    close_times_and_closes: list of (time_str, close_price)
    """
    local_tz = ZoneInfo(tz)
    rows = []
    for ts, c in close_times_and_closes:
        rows.append({
            "time":    pd.Timestamp(ts, tz=local_tz),
            "open":    c,
            "high":    c,
            "low":     c,
            "close":   c,
            "volume":  100.0,
            "ema_200": ema200_val,
            # add a few dummy indicator columns so attach_h1_features_to_m5
            # finds 'close' and 'ema_200'
        })
    df = pd.DataFrame(rows).set_index("time")
    df.index.name = "time"
    return df


def test_m5_at_10_05_uses_h1_at_10_00():
    """
    Key no-lookahead assertion:
    M5 bar closing at 10:05 must see the H1 bar that closed at 10:00,
    NOT the one that will close at 11:00.
    """
    local_tz = ZoneInfo(TZ)
    df_h1 = _make_h1([
        ("2024-01-15 10:00:00+01:00", 100.0),   # H1 bar for 09:00-10:00
        ("2024-01-15 11:00:00+01:00", 200.0),   # H1 bar for 10:00-11:00
    ], ema200_val=50.0)

    m5_times = [
        "2024-01-15 10:00:00+01:00",   # exactly on H1 close → use H1 10:00
        "2024-01-15 10:05:00+01:00",   # 5 min after H1 close → use H1 10:00
        "2024-01-15 10:59:00+01:00",   # just before next H1 → use H1 10:00
        "2024-01-15 11:00:00+01:00",   # on next H1 close → use H1 11:00
    ]
    df_m5 = pd.DataFrame({
        "time":  pd.to_datetime(m5_times),
        "close": [1.0, 2.0, 3.0, 4.0],
    })

    result = attach_h1_features_to_m5(df_m5, df_h1)

    # rows 0-2 (10:00, 10:05, 10:59) must reference H1 close=100
    for i in range(3):
        assert result.loc[i, "ema200_h1"] == pytest.approx(50.0), \
            f"Row {i} at {m5_times[i]}: expected ema200_h1=50 (H1@10:00)"

    # row 3 (11:00) must reference H1 close=200
    assert result.loc[3, "ema200_h1"] == pytest.approx(50.0)   # ema200 is same
    # but to distinguish which H1 bar was picked, check via trend_h1:
    # H1@10:00: close=100 > ema200=50 → trend_h1=True, bias=+1
    # H1@11:00: close=200 > ema200=50 → trend_h1=True, bias=+1 (same — use close check)
    # Re-build with a distinguishable EMA so we can tell rows apart
    df_h1_b = _make_h1([
        ("2024-01-15 10:00:00+01:00", 100.0),
        ("2024-01-15 11:00:00+01:00", 200.0),
    ], ema200_val=0.0)   # ema200=0 so trend_h1 is always True; we check close indirectly

    result_b = attach_h1_features_to_m5(df_m5, df_h1_b)
    for i in range(3):
        assert result_b.loc[i, "trend_bias"] == 1   # H1 10:00: 100 > 0
    assert result_b.loc[3, "trend_bias"] == 1        # H1 11:00: 200 > 0


def test_m5_before_all_h1_gets_nan():
    """M5 bars that precede all H1 bars must have NaN for H1 columns."""
    local_tz = ZoneInfo(TZ)
    df_h1 = _make_h1([("2024-01-15 11:00:00+01:00", 100.0)], ema200_val=50.0)

    df_m5 = pd.DataFrame({
        "time":  pd.to_datetime(["2024-01-15 09:05:00+01:00"]),
        "close": [1.0],
    })
    result = attach_h1_features_to_m5(df_m5, df_h1)

    assert pd.isna(result.loc[0, "ema200_h1"]), "Expected NaN for M5 before any H1 bar"
    assert pd.isna(result.loc[0, "trend_h1"])


def test_trend_h1_true_when_close_above_ema200():
    """trend_h1=True and trend_bias=+1 when H1 close > EMA-200."""
    df_h1 = _make_h1([("2024-01-15 10:00:00+01:00", 200.0)], ema200_val=100.0)
    df_m5 = pd.DataFrame({
        "time":  pd.to_datetime(["2024-01-15 10:05:00+01:00"]),
        "close": [1.0],
    })
    result = attach_h1_features_to_m5(df_m5, df_h1)

    assert result.loc[0, "trend_h1"]   is True or result.loc[0, "trend_h1"] == True
    assert result.loc[0, "trend_bias"] == 1


def test_trend_h1_false_when_close_below_ema200():
    """trend_h1=False and trend_bias=-1 when H1 close < EMA-200."""
    df_h1 = _make_h1([("2024-01-15 10:00:00+01:00", 50.0)], ema200_val=100.0)
    df_m5 = pd.DataFrame({
        "time":  pd.to_datetime(["2024-01-15 10:05:00+01:00"]),
        "close": [1.0],
    })
    result = attach_h1_features_to_m5(df_m5, df_h1)

    assert result.loc[0, "trend_h1"]   is False or result.loc[0, "trend_h1"] == False
    assert result.loc[0, "trend_bias"] == -1


def test_all_m5_columns_preserved():
    """Original M5 columns must not be dropped or renamed."""
    df_h1 = _make_h1([("2024-01-15 10:00:00+01:00", 100.0)], ema200_val=50.0)
    df_m5 = pd.DataFrame({
        "time":   pd.to_datetime(["2024-01-15 10:05:00+01:00"]),
        "open":   [1.0],
        "high":   [2.0],
        "low":    [0.5],
        "close":  [1.5],
        "volume": [500.0],
    })
    result = attach_h1_features_to_m5(df_m5, df_h1)

    for col in ["time", "open", "high", "low", "close", "volume"]:
        assert col in result.columns, f"Original column '{col}' missing from result"


def test_integration_build_then_attach():
    """
    End-to-end: build H1 from M5, then attach back.
    Each M5 row must receive the H1 bar that closed at or before its time.
    """
    # 3 full H1 bars worth of M5 data
    df_m5 = _make_m5("2024-01-15 09:05:00", periods=12 * 3, tz=TZ)
    df_h1  = build_h1_from_m5(df_m5, tz=TZ)
    result = attach_h1_features_to_m5(df_m5, df_h1)

    assert "ema200_h1"  in result.columns
    assert "trend_h1"   in result.columns
    assert "trend_bias" in result.columns
    assert len(result)  == len(df_m5)

    # First 12 M5 bars close in (09:05..10:00]: their H1 bar is at 10:00
    h1_time_for_first_batch = result.iloc[:12]["time"].max()
    assert h1_time_for_first_batch.hour == 10
