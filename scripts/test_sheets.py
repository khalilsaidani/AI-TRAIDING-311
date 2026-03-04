#!/usr/bin/env python3
"""Quick smoke-test for the Google Sheets connection.

Run from the repo root:
    python scripts/test_sheets.py
"""
import os
import sys
import traceback
from pathlib import Path

# Load .env from repo root (one level up from scripts/)
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

import gspread
from google.oauth2.service_account import Credentials

creds_path = os.getenv("GOOGLE_CREDS_FILE", "")
sid        = os.getenv("SPREADSHEET_ID", "")
sheet_name = os.getenv("SHEET_NAME", "")

print(f"GOOGLE_CREDS_FILE = {creds_path!r}")
print(f"  exists          = {os.path.exists(creds_path)}")
print(f"SPREADSHEET_ID    = {sid!r}")
print(f"SHEET_NAME        = {sheet_name!r}")
print()

try:
    if not os.path.exists(creds_path):
        raise FileNotFoundError(f"Credentials file not found: {creds_path}")

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds  = Credentials.from_service_account_file(creds_path, scopes=scopes)
    print("[1/4] Credentials loaded         OK")

    gc = gspread.authorize(creds)
    print("[2/4] gspread.authorize()         OK")

    sh = gc.open_by_key(sid)
    print(f"[3/4] open_by_key()               OK  (title={sh.title!r})")

    ws = sh.worksheet(sheet_name)
    print(f"[4/4] worksheet()                 OK  (id={ws.id}, rows={ws.row_count})")

    print("\nSHEETS CONNECTION OK")

except Exception:
    print("\nSHEETS CONNECTION FAILED")
    traceback.print_exc()
    sys.exit(1)
