import pandas as pd
from indicators.indicators import add_indicators

CSV_PATH = "data/xauusd_m5.csv"

df = pd.read_csv(CSV_PATH)
df.columns = [c.lower().strip() for c in df.columns]

df["time"] = pd.to_datetime(df["time"])
df = df.sort_values("time").reset_index(drop=True)

# جرّب periods صغار باش بما إنو عندك 7 rows يطلعلك أرقام
df = add_indicators(df, ema_fast=3, ema_slow=5, rsi_period=3, atr_period=3)

print("rows:", len(df))
print(df[["time","close","ema_50","ema_200","rsi_14","atr_14","macd","macd_signal"]].tail(10))
print("\nNaN count:")
print(df[["ema_50","ema_200","rsi_14","atr_14","macd","macd_signal"]].isna().sum())
