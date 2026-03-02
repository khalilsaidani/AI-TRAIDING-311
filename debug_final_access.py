import os, json
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

sheet_id = os.getenv("GSHEET_ID", "").strip()
creds_path = os.getenv("SHEETS_CREDS_JSON", "").strip()

print("GSHEET_ID =", sheet_id)
print("CREDS PATH =", creds_path)

with open(creds_path, "r", encoding="utf-8") as f:
    data = json.load(f)
print("CLIENT EMAIL =", data.get("client_email"))

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
gc = gspread.authorize(creds)

print("Trying open_by_key...")
sh = gc.open_by_key(sheet_id)
print("✅ OPENED:", sh.title)

ws = sh.worksheet(os.getenv("GSHEET_TAB", "TradesV2").strip())
ws.append_row(["FINAL_TEST_OK"])
print("✅ WROTE ROW OK")