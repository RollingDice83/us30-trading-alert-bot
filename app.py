from flask import Flask, request, jsonify
import os, re, json, requests
from datetime import datetime, timedelta

app = Flask(__name__)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
active_trades = []
signal_store_path = "us30_memory.json"
version = "3.9.2"

# === Helper Functions ===

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def save_signals(signals):
    with open(signal_store_path, "w") as f:
        json.dump(signals, f)

def load_signals():
    if not os.path.exists(signal_store_path):
        return []
    with open(signal_store_path, "r") as f:
        return json.load(f)

def reset_signals():
    save_signals([])

def score_signals():
    signals = load_signals()
    now = datetime.utcnow()
    active = [s for s in signals if datetime.strptime(s["time"], "%Y-%m-%dT%H:%M:%S") > now - timedelta(minutes=45)]
    tags = [s["text"] for s in active]
    score = 0
    reasons = []
    if any("RSI" in t and "<30" in t for t in tags):
        score += 20
        reasons.append("RSI < 30")
    if any("Momentum: Bullish" in t for t in tags):
        score += 25
        reasons.append("Momentum bullish")
    if any("MSS Bullish" in t for t in tags):
        score += 30
        reasons.append("MSS Bullish Break")
    if any("Zone -2%" in t for t in tags):
        score += 15
        reasons.append("STDV -2% Pullback")
    if any("crossing up" in t for t in tags):
        score += 10
        reasons.append("Preis Break")
    if len(reasons) >= 3:
        score += 10
    return score, reasons

# === Command Handlers ===

def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return
    longs = [t for t in active_trades if t["direction"] == "long"]
    shorts = [t for t in active_trades if t["direction"] == "short"]
    msg = f"📈 Offene Positionen\n\n🟢 Longs ({len(longs)}):\n"
    for t in longs:
        msg += f"• {t['lot']} lot @ {t['entry']} → TP {t.get('tp', 'open')} – SL: {t.get('sl','manual')}\n"
    msg += f"\n🔴 Shorts ({len(shorts)}):\n"
    for t in shorts:
        msg += f"• {t['lot']} lot @ {t['entry']} → TP {t.get('tp', 'open')} – SL: {t.get('sl','manual')}\n"
    send_message(chat_id, msg)

def handle_trade(text, chat_id):
    match = re.search(r"(long|short) (\d+(?:\.\d+)?) SL=(\d+(?:\.\d+)?) TP=(\d+(?:\.\d+)?)", text.lower())
    if not match:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade long 42500 SL=42250 TP=43200")
        return
    direction, entry, sl, tp = match.groups()
    trade = {"direction": direction, "entry": float(entry), "sl": float(sl), "tp": float(tp), "lot": 1.0, "tag": "manual"}
    active_trades.append(trade)
    send_message(chat_id, f"✅ Trade hinzugefügt: {direction.upper()} @ {entry}")

def handle_close(text, chat_id):
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        send_message(chat_id, "❌ Bitte gib den Entry-Preis an. Beispiel: /close 42500")
        return
    entry = float(match.group(1))
    for t in active_trades:
        if t["entry"] == entry:
            active_trades.remove(t)
            send_message(chat_id, f"❎ Position @ {entry} geschlossen.")
            return
    send_message(chat_id, "⚠️ Keine passende Position gefunden.")

def handle_resetsignals(chat_id):
    reset_signals()
    send_message(chat_id, "🧹 Signal-Speicher wurde geleert.")

def handle_signals(chat_id):
    signals = load_signals()
    if not signals:
        send_message(chat_id, "📭 Keine aktiven Signale erkannt.")
        return
    msg = "📡 Aktive Signale:\n"
    for s in signals:
        msg += f"• {s['text']} ({s['time']})\n"
    score, reasons = score_signals()
    if reasons:
        msg += f"\n🧠 Kontext-Score: {score}/100\n➕ Gründe: {', '.join(reasons)}"
    send_message(chat_id, msg)

def handle_batch(text, chat_id):
    trades = []
    lines = text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line.upper().startswith("LONG") or line.upper().startswith("SHORT"):
            try:
                direction_match = re.match(r"(LONG|SHORT)", line, re.IGNORECASE)
                lot_match = re.search(r"(\d+(?:\.\d+)?) lot", line)
                entry_match = re.search(r"@(\d+(?:\.\d+)?)", line)
                tp_match = re.search(r"TP: ([\d\.]+|open)", line)
                sl_match = re.search(r"SL: ([\d\.]+|manual)", line)
                tag_match = re.search(r"Tag: (.+)$", line)

                direction = direction_match.group(1).lower()
                lot = float(lot_match.group(1)) if lot_match else 1.0
                entry = float(entry_match.group(1))
                tp = tp_match.group(1) if tp_match else "open"
                sl = sl_match.group(1) if sl_match else "manual"
                tag = tag_match.group(1).strip() if tag_match else "manual"

                trades.append({"direction": direction, "lot": lot, "entry": entry, "tp": tp, "sl": sl, "tag": tag})
            except Exception as e:
                print("Fehler beim Parsen einer Zeile:", line, "Fehler:", str(e))
                continue
    if trades:
        active_trades.extend(trades)
        send_message(chat_id, f"✅ {len(trades)} Trades hinzugefügt.")
    else:
        send_message(chat_id, "⚠️ Keine gültigen Trades erkannt.")

def handle_signal_push(data):
    text = data.get("text", "").strip()
    if any(keyword in text for keyword in ["RSI", "Momentum", "MSS", "Zone", "crossing"]):
        signals = load_signals()
        signals.append({"text": text, "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")})
        save_signals(signals)
        score, reasons = score_signals()
        if score >= 70:
            msg = f"📊 Signal-Vorschlag (Score {score}/100)\nUS30 Long\nEntry: TBD\nSL: TBD\nTP: TBD\n➕ {', '.join(reasons)}"
            send_message(TELEGRAM_CHAT_ID, msg)

# === Telegram Webhook ===

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"status": "ignored"}), 200

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()

    if text.lower().startswith("/status"):
        handle_status(chat_id)
    elif text.lower().startswith("/trade"):
        handle_trade(text, chat_id)
    elif text.lower().startswith("/close"):
        handle_close(text, chat_id)
    elif text.lower().startswith("/resetsignals"):
        handle_resetsignals(chat_id)
    elif text.lower().startswith("/signals"):
        handle_signals(chat_id)
    elif text.lower().startswith("/batch"):
        handle_batch(text, chat_id)
    elif text.lower().startswith("/help"):
        send_message(chat_id, f"📘 Befehle (v{version}):\n/status – offene Positionen\n/trade – Setup senden\n/close – Trade schließen\n/update – STDV aktualisieren\n/openprice – STDV Startpreis setzen\n/zones – STDV Zonen anzeigen\n/signals – aktuelle Signale\n/resetsignals – Signal-Reset\n/batch – mehrere Trades")
    else:
        handle_signal_push(msg)

    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return "US30-Bot läuft ✅"
