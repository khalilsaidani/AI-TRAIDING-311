import pandas as pd

CSV_PATH = "data/xauusd_m5.csv"

df = pd.read_csv(CSV_PATH)
df.columns = [c.lower().strip() for c in df.columns]

print("rows:", len(df))
print("cols:", df.columns.tolist())
print("head:")
print(df.head(3))
print("tail:")
print(df.tail(3))
