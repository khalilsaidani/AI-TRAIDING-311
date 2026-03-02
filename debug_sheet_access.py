from dotenv import load_dotenv
import os
import gspread
from google.oauth2.service_account import Credentials

load_dotenv()

GSHEET_ID = os.getenv("GSHEET_ID")
GSHEET_TAB = os.getenv("GSHEET_TAB", "TradesV2")
CREDS_FILE = os.getenv("SHEETS_CREDS_JSON")

print("GSHEET_ID =", GSHEET_ID)
print("GSHEET_TAB =", GSHEET_TAB)
print("CREDS_FILE =", CREDS_FILE)

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_file(
    CREDS_FILE,
    scopes=scopes
)

print("SERVICE ACCOUNT =", creds.service_account_email)

gc = gspread.authorize(creds)
sh = gc.open_by_key(GSHEET_ID)
print("OPEN OK:", sh.title)

ws = sh.worksheet(GSHEET_TAB)
ws.append_row(["DEBUG_OK"])
print("APPEND OK ✅")