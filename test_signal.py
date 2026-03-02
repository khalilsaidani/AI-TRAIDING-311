# test_signal.py
import pandas as pd

from indicators.indicators import add_indicators
from trading.signals import (
    EntryConfig,
    generate_signal,
    explain_signal,
)

CSV_PATH = "data/xauusd_m5.csv"


def build_h1_from_m5(df_m5: pd.DataFrame) -> pd.DataFrame:
    """
    Build H1 candles from M5, calculate indicators on H1,
    then merge EMA200_H1 + trend flags back to M5.
    """
    df = df_m5.copy()
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)

    tmp = df.set_index("time")

    # H1 resample (lowercase 'h' avoids FutureWarning)
    df_h1 = (
        tmp.resample("1h")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum") if "volume" in tmp.columns else ("close", "count"),
        )
        .dropna()
        .reset_index()
    )

    # indicators on H1
    df_h1 = add_indicators(df_h1)

    if "ema_200" not in df_h1.columns:
        raise ValueError("ema_200 missing from H1 indicators")

    df_h1 = df_h1[["time", "ema_200"]].rename(
        columns={"ema_200": "ema_200_h1"}
    )
    df_h1 = df_h1.sort_values("time")

    # merge back to M5
    df_merged = pd.merge_asof(
        df.sort_values("time"),
        df_h1,
        on="time",
        direction="backward",
    )

    # trend flags
    df_merged["trend_up_h1"] = df_merged["close"] > df_merged["ema_200_h1"]
    df_merged["trend_down_h1"] = df_merged["close"] < df_merged["ema_200_h1"]

    return df_merged


def build_signals_no_lookahead(
    df: pd.DataFrame,
    cfg: EntryConfig,
    warmup: int = 200,
) -> pd.DataFrame:
    """
    Build signals row-by-row without lookahead.
    """
    out = df.copy()
    signals = []

    for i in range(len(out)):
        if i < warmup:
            signals.append("NO_TRADE")
            continue

        sub = out.iloc[: i + 1].copy()
        sig = generate_signal(sub, cfg=cfg)
        signals.append(sig)

    out["signal"] = signals
    return out


def main():
    # Load CSV
    df = pd.read_csv(CSV_PATH)
    df.columns = [c.lower().strip() for c in df.columns]

    needed = {"time", "open", "high", "low", "close"}
    if not needed.issubset(df.columns):
        raise ValueError(f"CSV missing columns: {needed}")

    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)

    print("✅ CSV rows:", len(df))
    print("✅ Columns:", df.columns.tolist())

    # Indicators on M5
    df = add_indicators(df)

    # Add H1 trend
    df = build_h1_from_m5(df)

    # Quick check
    cols_show = [
        "time",
        "close",
        "ema_200",
        "ema_200_h1",
        "trend_up_h1",
        "trend_down_h1",
    ]
    cols_show = [c for c in cols_show if c in df.columns]

    print("\n=== INDICATORS CHECK (tail 5) ===")
    print(df[cols_show].tail(5))

    # =========================
    # CONFIG (Day Trading H1)
    # =========================
    cfg = EntryConfig(
        rr=2.0,
        sl_atr_mult=1.0,
        risk_per_trade=0.01,   # 1%
        rsi_buy_min=55.0,
        rsi_sell_max=45.0,
        use_supertrend=True,
        supertrend_buy_dir=1,
        supertrend_sell_dir=-1,
    )

    # Explain last signal
    print("\n=== SIGNAL DEBUG (Day Trading H1) ===")
    exp = explain_signal(df, cfg=cfg)
    for k, v in exp.items():
        print(f"{k}: {v}")

    print(f"\n✅ FINAL SIGNAL: {exp['signal']}")

    # Build all signals (no lookahead)
    warmup = 200
    print(f"\n=== BUILDING SIGNALS (no look-ahead) warmup={warmup} ===")
    df_sig = build_signals_no_lookahead(df, cfg=cfg, warmup=warmup)

    print("\n=== SIGNAL COUNTS ===")
    print(df_sig["signal"].value_counts(dropna=False))


if __name__ == "__main__":
    main()