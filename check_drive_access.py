from pathlib import Path
from dotenv import load_dotenv
import os

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

load_dotenv()

GSHEET_ID = os.getenv("GSHEET_ID", "").strip()
CREDS_FILE = os.getenv("SHEETS_CREDS_JSON", "").strip()

print("GSHEET_ID:", repr(GSHEET_ID))
print("CREDS_FILE:", repr(CREDS_FILE))

creds = Credentials.from_service_account_file(
    CREDS_FILE,
    scopes=[
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/spreadsheets.readonly",
    ],
)

drive = build("drive", "v3", credentials=creds)

try:
    meta = drive.files().get(fileId=GSHEET_ID, fields="id,name,mimeType,owners,driveId").execute()
    print("✅ DRIVE CAN SEE FILE:", meta)
except Exception as e:
    print("❌ DRIVE CANNOT SEE FILE:", e)