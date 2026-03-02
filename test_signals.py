import pandas as pd
from indicators.indicators import add_indicators
from trading.signals import generate_signal

CSV_PATH = "data/xauusd_m5.csv"

df = pd.read_csv(CSV_PATH)
df.columns = [c.lower().strip() for c in df.columns]

df["time"] = pd.to_datetime(df["time"])
df = df.sort_values("time").reset_index(drop=True)

# نفس periods الصغار للتست (خاطر عندك 7 rows)
df = add_indicators(df, ema_fast=3, ema_slow=5, rsi_period=3, atr_period=3)

# نحيو الصفوف اللي فيها NaN في rsi/atr قبل signal
df2 = df.dropna(subset=["rsi_14", "atr_14"]).reset_index(drop=True)

print("rows before:", len(df), "rows after dropna:", len(df2))
print(df2[["time","close","ema_50","ema_200","rsi_14","atr_14","macd","macd_signal"]].tail(5))

if df2.empty:
    print("❌ Not enough data after dropna")
else:
    signal = generate_signal(df2)
    print("✅ SIGNAL =", signal)
