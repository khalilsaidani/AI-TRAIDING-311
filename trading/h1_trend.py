# trading/h1_trend.py
import pandas as pd
from indicators.indicators import add_indicators


def build_h1_trend_from_m5(df_m5: pd.DataFrame) -> pd.DataFrame:
    df = df_m5.copy()
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)

    tmp = df.set_index("time")

    df_h1 = tmp.resample("1h").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum") if "volume" in tmp.columns else ("close", "count"),
    ).dropna().reset_index()

    df_h1 = add_indicators(df_h1)

    if "ema_200" not in df_h1.columns:
        raise ValueError("Missing ema_200 in H1 indicators output. Check add_indicators().")

    df_h1 = df_h1[["time", "ema_200"]].rename(columns={"ema_200": "ema_200_h1"})
    df_h1 = df_h1.sort_values("time")

    df_merged = pd.merge_asof(
        df.sort_values("time"),
        df_h1.sort_values("time"),
        on="time",
        direction="backward",
    )

    df_merged["trend_up_h1"] = df_merged["close"] > df_merged["ema_200_h1"]
    df_merged["trend_down_h1"] = df_merged["close"] < df_merged["ema_200_h1"]
    return df_merged