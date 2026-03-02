from bridge.sheets_writer import write_to_sheets
import time

trade_id = "TEST-TP123-001"
now = int(time.time())

write_to_sheets({
    "event": "ENTRY",
    "trade_id": trade_id,
    "symbol": "XAUUSD",
    "tf": "15",
    "signal": "BUY",
    "entry": "2000",
    "sl": "1990",
    "tp1": "2005",
    "tp2": "2007",
    "tp3": "2010",
    "rr": "2",
    "strategy": "TEST_STRAT",
    "time": now,
})

time.sleep(2)
write_to_sheets({"event": "TP1", "trade_id": trade_id, "time": time.time()})
time.sleep(2)
write_to_sheets({"event": "TP2", "trade_id": trade_id, "time": time.time()})
time.sleep(2)
write_to_sheets({"event": "SL", "trade_id": trade_id, "time": time.time()})