# AI-TRADING-311

TradingView webhook → Google Sheets + Telegram bridge.

---

## Quick start (development)

```bash
cp .env.example .env   # fill in your secrets
source .venv/bin/activate
uvicorn webhook_server:app --host 0.0.0.0 --port 8000 --reload
```

Test the connection before starting:
```bash
python scripts/test_sheets.py
```

---

## Production Run

### Option 1 — gunicorn + uvicorn workers (recommended)

```bash
pip install gunicorn
gunicorn webhook_server:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 2 \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

Keep `DEBUG_MODE=0` in `.env` for production — only `INFO` and above will be logged.

> **Security:** `.env` is listed in `.gitignore` and must never be committed. It contains secrets.

### Health check

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected:
```json
{"ok": true, "app": "ai-trading-311-webhook", "tz": "Europe/Zurich", "debug": false}
```

### Option 2 — uvicorn directly (single process)

```bash
uvicorn webhook_server:app --host 0.0.0.0 --port 8000 --log-level info
```

### Option 3 — systemd service (optional)

Create `/etc/systemd/system/ai-trading.service`:

```ini
[Unit]
Description=AI Trading Webhook
After=network.target

[Service]
User=youruser
WorkingDirectory=/path/to/ai-trading-311
EnvironmentFile=/path/to/ai-trading-311/.env
ExecStart=/path/to/.venv/bin/gunicorn webhook_server:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers 2 \
  --bind 0.0.0.0:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ai-trading
sudo journalctl -u ai-trading -f
```

---

## Environment variables

See [.env.example](.env.example) for the full list. Copy it to `.env` and fill in your secrets.
