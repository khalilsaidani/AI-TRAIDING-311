from pathlib import Path
from dotenv import load_dotenv
import os

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

v = os.getenv("GSHEET_ID")
t = os.getenv("GSHEET_TAB")
c = os.getenv("SHEETS_CREDS_JSON")

print("ENV_PATH:", ENV_PATH)
print("GSHEET_ID repr:", repr(v))
print("GSHEET_ID len:", None if v is None else len(v))
print("GSHEET_TAB repr:", repr(t))
print("CREDS repr:", repr(c))

if v:
    print("GSHEET_ID chars:", [hex(ord(ch)) for ch in v])