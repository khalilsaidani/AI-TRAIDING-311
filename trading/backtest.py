import pandas as pd

def backtest(df, start_balance=10000, risk_per_trade=0.01, rr=2.0, sl_atr_mult=1.0):
    """
    Backtest بسيط:
    - يدخل على close متاع الشمعة وقت signal = BUY/SELL
    - يخرج ب SL/TP داخل الشموع الجاية باستعمال high/low
    - PnL محسوب كنسبة من الرصيد (risk_per_trade) مع rr
    ملاحظة: إذا في نفس الشمعة ضرب SL و TP مع بعضهم، نخليها Conservative = SL أولاً.
    """

    required = {"time", "high", "low", "close", "atr_14", "signal"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in df: {missing}")

    balance = float(start_balance)
    trades = wins = losses = 0
    trade_log = []

    position = None  # None / "LONG" / "SHORT"
    entry_price = sl = tp = None
    entry_time = None
    entry_idx = None

    for i in range(1, len(df)):
        row = df.iloc[i]
        signal = row["signal"]

        # 1) دخول
        if position is None:
            if signal == "BUY":
                position = "LONG"
                entry_price = float(row["close"])
                entry_time = row["time"]
                entry_idx = i

                atr = float(row["atr_14"])
                sl = entry_price - (atr * sl_atr_mult)
                tp = entry_price + (atr * sl_atr_mult * rr)

            elif signal == "SELL":
                position = "SHORT"
                entry_price = float(row["close"])
                entry_time = row["time"]
                entry_idx = i

                atr = float(row["atr_14"])
                sl = entry_price + (atr * sl_atr_mult)
                tp = entry_price - (atr * sl_atr_mult * rr)

            continue

        # 2) إدارة الصفقة (على الشموع التالية)
        high = float(row["high"])
        low = float(row["low"])

        hit = None
        exit_price = None

        if position == "LONG":
            # Conservative: SL قبل TP إذا الزوز تضربو
            if low <= sl:
                hit = "SL"
                exit_price = sl
            elif high >= tp:
                hit = "TP"
                exit_price = tp

        elif position == "SHORT":
            if high >= sl:
                hit = "SL"
                exit_price = sl
            elif low <= tp:
                hit = "TP"
                exit_price = tp

        if hit is None:
            continue

        # 3) تسجيل النتيجة
        trades += 1
        risk_amount = balance * float(risk_per_trade)

        if hit == "TP":
            pnl = risk_amount * float(rr)
            wins += 1
        else:
            pnl = -risk_amount
            losses += 1

        balance += pnl

        trade_log.append({
            "entry_time": entry_time,
            "exit_time": row["time"],
            "side": position,
            "entry": entry_price,
            "exit": exit_price,
            "result": hit,
            "pnl": pnl,
            "balance_after": balance,

            # snapshot indicators at entry
            "atr_14": float(df.iloc[entry_idx]["atr_14"]),
            "ema_200": float(df.iloc[entry_idx]["ema_200"]) if "ema_200" in df.columns else None,
            "rsi_14": float(df.iloc[entry_idx]["rsi_14"]) if "rsi_14" in df.columns else None,
            "macd": float(df.iloc[entry_idx]["macd"]) if "macd" in df.columns else None,
            "macd_signal": float(df.iloc[entry_idx]["macd_signal"]) if "macd_signal" in df.columns else None,
        })

        # reset
        position = None
        entry_price = sl = tp = None
        entry_time = None
        entry_idx = None

    winrate = (wins / trades * 100) if trades else 0.0
    trades_df = pd.DataFrame(trade_log)

    return {
        "final_balance": round(balance, 2),
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "winrate": round(winrate, 2),
        "rr": rr,
        "sl_atr_mult": sl_atr_mult,
        "risk_per_trade": risk_per_trade,
        "trades_df": trades_df,
    }
