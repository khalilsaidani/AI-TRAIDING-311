# TradingView Alert Setup

## Webhook URL

```
https://your-server.com/tv-webhook
```

---

## Required fields (all events)

| Field | Type | Description |
|---|---|---|
| `secret` | string | Must match `WEBHOOK_SECRET` in `.env` |
| `event` | string | One of: `ENTRY`, `TP1`, `TP2`, `TP3`, `SL` |
| `trade_id` | string | Stable ID that ties all events to the same trade |

---

## How to send the secret

### Option A — in the JSON body (primary, recommended)
```json
{ "secret": "{{input.secret}}" }
```
Set a TradingView Input in your script and pass it here.

### Option B — in the HTTP header
Add a custom header in the alert dialog:
```
x-webhook-secret: your-secret-here
```
Both are accepted. JSON takes priority if both are present.

---

## JSON payload templates

Copy each block into the **"Message"** field of the TradingView alert.

### ENTRY
```json
{
  "secret":    "{{input.secret}}",
  "event":     "ENTRY",
  "trade_id":  "{{ticker}}_{{interval}}_{{timenow}}",
  "symbol":    "{{ticker}}",
  "tf":        "{{interval}}",
  "signal":    "BUY",
  "strategy":  "MyStrategy",
  "entry":     {{close}},
  "sl":        0,
  "tp1":       0,
  "tp2":       0,
  "tp3":       0,
  "server_time": "{{timenow}}"
}
```

### TP1 hit
```json
{
  "secret":    "{{input.secret}}",
  "event":     "TP1",
  "trade_id":  "{{strategy.order.id}}",
  "symbol":    "{{ticker}}",
  "tf":        "{{interval}}",
  "server_time": "{{timenow}}"
}
```

### TP2 hit
```json
{
  "secret":    "{{input.secret}}",
  "event":     "TP2",
  "trade_id":  "{{strategy.order.id}}",
  "symbol":    "{{ticker}}",
  "tf":        "{{interval}}",
  "server_time": "{{timenow}}"
}
```

### TP3 hit
```json
{
  "secret":    "{{input.secret}}",
  "event":     "TP3",
  "trade_id":  "{{strategy.order.id}}",
  "symbol":    "{{ticker}}",
  "tf":        "{{interval}}",
  "server_time": "{{timenow}}"
}
```

### SL hit
```json
{
  "secret":    "{{input.secret}}",
  "event":     "SL",
  "trade_id":  "{{strategy.order.id}}",
  "symbol":    "{{ticker}}",
  "tf":        "{{interval}}",
  "server_time": "{{timenow}}"
}
```

---

## Stable trade_id in Pine Script

The biggest pitfall: if `trade_id` changes every bar, TP/SL events won't match the ENTRY row in the sheet.

### Pattern — persistent var (works in studies and strategies)

```pine
//@version=5
indicator("MyStrategy", overlay=true)

// Input for webhook secret (never hardcode it)
secret = input.string("", title="Webhook Secret", group="Webhook")

// Persistent trade_id — set once on ENTRY, held until position closes
var string trade_id = ""

entrySignal = ta.crossover(ta.ema(close, 9), ta.ema(close, 21))
tp1Hit      = high >= strategy.position_avg_price * 1.02
slHit       = low  <= strategy.position_avg_price * 0.99

if entrySignal
    // Build a stable ID: symbol + timeframe + bar_index
    trade_id := syminfo.ticker + "_" + timeframe.period + "_" + str.tostring(bar_index)

    payload = '{"secret":"' + secret + '",' +
              '"event":"ENTRY",' +
              '"trade_id":"' + trade_id + '",' +
              '"symbol":"' + syminfo.ticker + '",' +
              '"tf":"' + timeframe.period + '",' +
              '"signal":"BUY",' +
              '"entry":' + str.tostring(close) + '}'
    alert(payload, alert.freq_once_per_bar)

if tp1Hit and trade_id != ""
    payload = '{"secret":"' + secret + '",' +
              '"event":"TP1",' +
              '"trade_id":"' + trade_id + '",' +
              '"symbol":"' + syminfo.ticker + '",' +
              '"tf":"' + timeframe.period + '"}'
    alert(payload, alert.freq_once_per_bar)

if slHit and trade_id != ""
    payload = '{"secret":"' + secret + '",' +
              '"event":"SL",' +
              '"trade_id":"' + trade_id + '",' +
              '"symbol":"' + syminfo.ticker + '",' +
              '"tf":"' + timeframe.period + '"}'
    alert(payload, alert.freq_once_per_bar)
    trade_id := ""  // reset — trade is closed
```

**Key rule:** `var string trade_id = ""` uses Pine's `var` keyword so the value persists across bars. It is set only on ENTRY and reset only on SL/TP close. This guarantees every TP/SL alert carries the same `trade_id` as the ENTRY.

---

## Alert dialog settings in TradingView

1. Open the alert dialog (`Alt+A`)
2. **Condition** → your indicator/strategy
3. **Message** → paste the JSON template above
4. **Webhook URL** → `https://your-server.com/tv-webhook`
5. **Frequency** → `Once Per Bar Close` (recommended to avoid duplicates)
