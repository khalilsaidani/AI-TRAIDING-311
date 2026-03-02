# make_test_csv.py
import os
import numpy as np
import pandas as pd

def make_ohlc(n=1500, start_price=2000.0, seed=42):
    rng = np.random.default_rng(seed)

    # random walk للـ close
    steps = rng.normal(loc=0.02, scale=0.8, size=n)   # تعديل بسيط باش تكون realistic
    close = start_price + np.cumsum(steps)

    # open = close السابقة
    open_ = np.r_[close[0], close[:-1]]

    # high/low حوالي open/close
    spread = np.abs(rng.normal(loc=0.6, scale=0.25, size=n))
    high = np.maximum(open_, close) + spread
    low  = np.minimum(open_, close) - spread

    # volume
    volume = rng.integers(80, 400, size=n)

    return open_, high, low, close, volume

def main():
    os.makedirs("data", exist_ok=True)

    n = 1500
    start = pd.Timestamp("2024-12-01 00:00:00")
    time_index = pd.date_range(start=start, periods=n, freq="5min")

    o, h, l, c, v = make_ohlc(n=n)

    df = pd.DataFrame({
        "time": time_index.strftime("%Y-%m-%d %H:%M:%S"),
        "open": np.round(o, 2),
        "high": np.round(h, 2),
        "low":  np.round(l, 2),
        "close": np.round(c, 2),
        "volume": v
    })

    out_path = "data/xauusd_m5.csv"
    df.to_csv(out_path, index=False)
    print(f"✅ Saved: {out_path}")
    print("rows:", len(df))
    print(df.head(3))
    print(df.tail(3))

if __name__ == "__main__":
    main()
