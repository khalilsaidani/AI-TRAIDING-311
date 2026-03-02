# analyzer.py

def analyze_btc_multitf(payload: dict) -> dict:
    """
    v2 placeholder:
    - TradingView يبعث signal + timeframe (قرار الدخول النهائي عادة 1H)
    - هنا لاحقاً باش نقرأ multi-timeframes (1m/5m/15m/1h) ونقرر
    """

    symbol = payload.get("symbol", "UNKNOWN")
    tf = payload.get("timeframe", "1h")
    signal = payload.get("signal", "BUY")

    # حاليا: نخليها بسيطة (باش ما تعملش errors)
    if signal not in ("BUY", "SELL"):
        return {
            "symbol": symbol,
            "decision_tf": tf,
            "bias": "NEUTRAL",
            "action": "IGNORE",
            "reason": "Invalid signal"
        }

    return {
        "symbol": symbol,
        "decision_tf": tf,
        "bias": "BULLISH" if signal == "BUY" else "BEARISH",
        "action": signal,
        "reason": "Analyzer v2 placeholder (no multi-TF data yet)"
    }