import pandas as pd
df = pd.read_csv("data/xauusd_m5.csv")
df.columns = [c.lower().strip() for c in df.columns]

df = add_indicators(df)

print("=== INDICATORS CHECK ===")
print(df[["close", "ema_50", "rsi_14", "atr_14"]].tail(20))