# test_sheets.py
from dotenv import load_dotenv
load_dotenv()  # IMPORTANT: قبل import

from bridge.sheets_writer import write_to_sheets

entry_payload = {
    "event": "ENTRY",
    "trade_id": "TEST_TP123_001",
    "symbol": "XAUUSD",
    "tf": "15",
    "strategy": "TEST_STRAT_TP123",
    "signal": "BUY",
    "entry": 2000.12345,
    "sl": 1990.12345,
    "tp1": 2005.12345,
    "tp2": 2007.12345,
    "tp3": 2010.12345,
    "rr": 2,
    "time": "2026-02-04 21:00:00",
}

tp1_payload = {
    "event": "TP1",
    "trade_id": "TEST_TP123_001",
    "tp1": 2005.12,
    "time": "2026-02-04 21:05:00",
}

print(write_to_sheets(entry_payload))
print(write_to_sheets(tp1_payload))