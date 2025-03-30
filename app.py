# --- ANFANG: US30 Telegram Bot v4.0.1 ---

from flask import Flask, request, jsonify
import os, re, json, requests
from datetime import datetime, timedelta
import yfinance as yf

app = Flask(__name__)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
active_trades = []
signal_store_path = "us30_memory.json"
context_store_path = "us30_context.json"
version = "4.0.1"

# === Helper Functions ===

def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)

def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

def save_signals(signals):
    save_json(signal_store_path, signals)

def load_signals():
    return load_json(signal_store_path) or []

def reset_signals():
    save_signals([])

def get_opening_price():
    context = load_json(context_store_path)
    return float(context.get("open_price", 0))

def set_opening_price(price):
    context = load_json(context_store_path)
    context["open_price"] = price
    save_json(context_store_path, context)

def fetch_open_price_yahoo():
    try:
        df = yf.download("^DJI", period="5d", interval="1h")
        df = df[df.index.strftime("%H:%M") == "00:00"]
        if not df.empty:
            price = round(df.iloc[-1]["Open"], 2)
            set_opening_price(price)
            return price
    except Exception as e:
        print("Yahoo Price Error:", e)
    return None

def calc_stdv_zones(base):
    return {f"{i:+d}%": round(base * (1 + i / 100), 2) for i in range(-5, 6)}

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
    if any("crossing up" in t or "crossing down" in t for t in tags):
        score += 10
        reasons.append("Preis Break")
    if len(reasons) >= 3:
        score += 10
    return score, reasons

# === Command Handlers ===

def handle_openprice(text, chat_id):
    match = re.search(r"/openprice\s+(\d+(?:\.\d+)?)", text.lower())
    if match:
        price = float(match.group(1))
        set_opening_price(price)
        zones = calc_stdv_zones(price)
        msg = "📊 STDV Zonen:\n"
        for k, v in zones.items():
            color = "🟥" if "-" in k else "🟩" if "+" in k else "🔵"
            msg += f"{color} {k}: {v}\n"
        send_message(chat_id, msg)
    else:
        send_message(chat_id, "❌ Ungültiger /openprice-Befehl. Beispiel: /openprice 44100")

def handle_signal_push(data):
    text = data.get("text", "").strip()
    if any(k in text for k in ["RSI", "Momentum", "MSS", "Zone", "crossing"]):
        signals = load_signals()
        signals.append({"text": text, "time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")})
        save_signals(signals)
        score, reasons = score_signals()
        if score >= 70:
            msg = f"📊 Signal-Vorschlag (Score {score}/100)\nUS30 Long\nEntry: TBD\nSL: TBD\nTP: TBD\n➕ {', '.join(reasons)}"
            send_message(TELEGRAM_CHAT_ID, msg)

def handle_signals(text, chat_id):
    signals = load_signals()
    if not signals:
        send_message(chat_id, "ℹ️ Keine aktiven Signale gespeichert.")
    else:
        msg = "📍 Aktive Signale:\n"
        for s in signals[-10:]:
            msg += f"• {s['text']} ({s['time'].split('T')[1]})\n"
        score, reasons = score_signals()
        msg += f"\n🧠 Aktueller Score: {score}/100\n➕ {', '.join(reasons)}"
        send_message(chat_id, msg)

# === Webhook ===

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"status": "ignored"}), 200
    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()

    if text.lower().startswith("/openprice"):
        handle_openprice(text, chat_id)
    elif text.lower().startswith("/help"):
        send_message(chat_id, f"📘 Befehle (v{version}):\n/openprice – STDV setzen\n/signals – akt. Signale\n/resetsignals – leeren\n/batch – Trades eintragen")
    elif text.lower().startswith("/signals"):
        handle_signals(text, chat_id)
    elif text.lower().startswith("/resetsignals"):
        reset_signals()
        send_message(chat_id, "✅ Signal-Speicher gelöscht.")
    elif text.lower().startswith("/batch"):
        lines = text.splitlines()
        parsed = []
        for line in lines:
            if not line.strip().upper().startswith("LONG") and not line.strip().upper().startswith("SHORT"):
                continue
            try:
                pos = {
                    "type": "LONG" if "LONG" in line.upper() else "SHORT",
                    "lot": float(re.search(r"(\d+(\.\d+)?) lot", line).group(1)),
                    "entry": float(re.search(r"@ (\d+(\.\d+)?)", line).group(1)),
                    "tp": float(re.search(r"TP: (\d+(\.\d+)?)", line).group(1)) if "TP:" in line else None,
                    "sl": re.search(r"SL: (\d+(\.\d+)?|manual)", line).group(1),
                    "tag": re.search(r"Tag: ([\w ]+)", line).group(1)
                }
                parsed.append(pos)
            except Exception as e:
                print(f"Fehler beim Parsen einer Zeile: {line} Fehler: {e}")
        if parsed:
            active_trades.extend(parsed)
            send_message(chat_id, f"✅ {len(parsed)} Position(en) hinzugefügt.")
        else:
            send_message(chat_id, "⚠️ Keine gültigen Trades erkannt.")
    else:
        handle_signal_push(msg)

    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return f"US30-Bot v{version} läuft ✅"

# --- ENDE: US30 Telegram Bot v4.0.1 ---
