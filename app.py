from flask import Flask, request, jsonify
import os, json, requests, re, datetime
from threading import Timer

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
active_trades = []
signal_memory_file = "us30_memory.json"
stdv_file = "stdv_zones.json"

# 📦 Helper
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def save_signals(signals):
    with open(signal_memory_file, "w") as f:
        json.dump(signals, f)

def load_signals():
    if not os.path.exists(signal_memory_file):
        return []
    with open(signal_memory_file, "r") as f:
        return json.load(f)

def add_signal(text):
    signals = load_signals()
    if text not in signals:
        signals.append(text)
        save_signals(signals)

def reset_signals():
    if os.path.exists(signal_memory_file):
        os.remove(signal_memory_file)

# 🧠 Score Engine
def evaluate_score():
    signals = load_signals()
    score = 0
    context = []

    if "Momentum: Bullish 1h" in signals: score += 30; context.append("📈 Bullish Momentum 1h")
    if "RSI Below 30 on US30, 1h" in signals: score += 30; context.append("🟢 RSI < 30")
    if "MSS Bullish Break on US30, 1h" in signals: score += 40; context.append("🚀 Strukturbruch 1h")

    if score >= 70:
        send_message(TELEGRAM_CHAT_ID, f"✅ Setup Score: {score}/100\n" + "\n".join(context))
    elif score >= 40:
        send_message(TELEGRAM_CHAT_ID, f"⚠️ Frühwarnung – Score {score}/100\n" + "\n".join(context))

# 📊 STDV-Zonen
def save_stdv_zones(open_price):
    zones = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "open": open_price,
        "zones": {f"{i:+d}%": round(open_price * (1 + i / 100), 2) for i in range(-5, 6)}
    }
    with open(stdv_file, "w") as f:
        json.dump(zones, f)

def load_stdv_zones():
    if not os.path.exists(stdv_file):
        return None
    with open(stdv_file, "r") as f:
        return json.load(f)

# 🧾 Telegram Commands
def parse_trade_command(text):
    pattern = r"/trade(?=.*\b(?P<symbol>\w+)\b)(?=.*\b(?P<direction>long|short)\b)(?=.*\b(?P<entry>\d+(?:\.\d+)?))(?=.*SL=(?P<sl>\d+(?:\.\d+)?))?(?=.*TP=(?P<tp>\d+(?:\.\d+)?))?(?=.*score=(?P<score>\d+))?(?=.*tag=(?P<tag>.+))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match: return None
    data = match.groupdict()
    return {
        "symbol": data["symbol"].upper(),
        "direction": data["direction"].lower(),
        "entry": float(data["entry"]),
        "sl": float(data["sl"]) if data["sl"] else None,
        "tp": float(data["tp"]) if data["tp"] else None,
        "score": int(data["score"]) if data["score"] else None,
        "tag": data["tag"].strip() if data["tag"] else ""
    }

def handle_trade(text, chat_id):
    result = parse_trade_command(text)
    if not result:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade US30 long 42650 SL=42500 TP=43000 score=80 tag=Breakout")
        return
    active_trades.append(result)
    msg = f"📥 Neuer Trade:\n{result['symbol']} {result['direction']} @ {result['entry']}"
    if result['sl']: msg += f" | SL: {result['sl']}"
    if result['tp']: msg += f" | TP: {result['tp']}"
    if result['score']: msg += f" | Score: {result['score']}"
    if result['tag']: msg += f"\n📝 {result['tag']}"
    send_message(chat_id, msg)

def handle_status(chat_id):
    if not active_trades:
        send_message(chat_id, "📊 Keine offenen Positionen.")
        return
    msg = "📈 Offene Positionen:\n"
    for t in active_trades:
        line = f"{t['symbol']} {t['direction']} @ {t['entry']}"
        if t['tp']: line += f" → TP {t['tp']}"
        if t['sl']: line += f", SL {t['sl']}"
        if t['score']: line += f" (Score {t['score']})"
        if t['tag']: line += f" – {t['tag']}"
        msg += f"• {line}\n"
    send_message(chat_id, msg)

def handle_help(chat_id):
    send_message(chat_id, f"""📘 Befehle (v3.4):
/status – offene Positionen
/trade – Trade-Setup senden
/close – Position schließen
/update – STDV Zones aktualisieren
/OpenPrice 44100 – STDV Startpreis setzen
/zones – STDV Zonen anzeigen
/resetsignals – Signal-Speicher leeren
/batch – Mehrere Trades senden
/help – Hilfe anzeigen""")

# 📩 Telegram Webhook
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    message = data.get("message", {})
    if not message: return jsonify({"status": "no message"}), 200

    user_text = message.get("text", "")
    chat_id = message["chat"]["id"]

    # 🔀 Befehlshandler
    if user_text.startswith("/status"):
        handle_status(chat_id)
    elif user_text.startswith("/help"):
        handle_help(chat_id)
    elif user_text.startswith("/trade"):
        handle_trade(user_text, chat_id)
    elif user_text.startswith("/resetsignals"):
        reset_signals()
        send_message(chat_id, "🧹 Signal-Speicher wurde gelöscht.")
    elif "Momentum" in user_text or "RSI" in user_text or "MSS" in user_text:
        add_signal(user_text)
        evaluate_score()
    else:
        send_message(chat_id, "❓ Unbekannter Befehl.")

    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return "US30 Trading Bot v3.4 läuft ✅"
