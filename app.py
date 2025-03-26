from flask import Flask, request, jsonify
import requests
import json
import yfinance as yf
import threading
import time
import os

app = Flask(__name__)

# Telegram Bot Token & Chat ID from Environment Variables
TELEGRAM_TOKEN = os.environ.get("7958399333:AAEGvMvyD_MhzDT47ZMHXGmJnJ0B_vh9KdU")
TELEGRAM_CHAT_ID = os.environ.get("805285674")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
TELEGRAM_WEBHOOK_PATH = "/telegram"

# Speicher für aktive Setups
active_setups = []

# Setup-Parser (vereinfacht)
def parse_signal(message):
    score = 4  # Dummy-Score für Signalqualität
    return {
        "direction": "Long" if "long" in message.lower() else "Short",
        "entry": 3042100,
        "tp": 42800,
        "sl": 41900,
        "type": "Smack",
        "rsi": 29,
        "momentum": "bullish",
        "score": score,
        "raw": message
    }

def send_telegram_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram-Konfiguration fehlt.")
        return
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    response = requests.post(TELEGRAM_API_URL, json=payload)
    print("📨 Telegram API Antwort:", response.status_code, response.text)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON"}), 400

    if isinstance(data, dict):
        message_text = data.get("message") or data.get("text")
    else:
        return jsonify({"error": "Invalid format"}), 400

    if not message_text:
        return jsonify({"error": "No message provided"}), 400

    response = handle_bot_message(message_text.strip())
    return jsonify(response)

@app.route(TELEGRAM_WEBHOOK_PATH, methods=["POST"])
def telegram_webhook():
    try:
        data = request.get_json(force=True)  # <-- wichtig: force=True
    except Exception as e:
        print("❌ Fehler beim JSON-Parsing:", str(e))
        return jsonify({"status": "invalid"}), 400

    print("🔔 Telegram Webhook-Eingang:", json.dumps(data, indent=2))

    if not data or "message" not in data:
        return jsonify({"status": "no message"}), 400

    message = data["message"].get("text")
    if message:
        response = handle_bot_message(message.strip())
        if isinstance(response, dict) and "reply" in response:
            send_telegram_message(response["reply"])
    return jsonify({"status": "ok"})


def handle_bot_message(message):
    message = message.strip()

    if message.startswith("/help"):
        return {"reply": send_help()}
    if message.startswith("/status"):
        return {"reply": send_status()}
    if message.startswith("/reset"):
        active_setups.clear()
        return {"reply": "✅ Alle aktiven Setups wurden zurückgesetzt."}

    # Setup erkannt
    signal = parse_signal(message)
    active_setups.append(signal)
    return {"reply": f"📌 Neues US30 Setup erkannt\n➡️ Richtung: {signal['direction']}\n🎯 Entry: {signal['entry']}\n🎯 TP: {signal['tp']}\n🛑 SL: {signal['sl']}\n🎯 Entry-Typ: {signal['type']}\n📊 RSI: {signal['rsi']}\n📈 Momentum: {signal['momentum']}\n⚙️ Signalqualität: {signal['score']}/10"}

def send_help():
    return """
🤖 *US30 Trading Bot Hilfe*

Verfügbare Befehle:
/status – zeigt alle aktiven Setups
/reset – löscht alle aktiven Setups
/help – zeigt diese Hilfe

Du kannst auch direkt Signale posten:
"US30 Long @42100 TP:42800 SL:41900"
"take partial profit"
"move SL to 42600"
    """

def send_status():
    if not active_setups:
        return "🚫 Keine aktiven Setups."
    msg = "📊 Aktive US30 Setups:\n"
    for i, s in enumerate(active_setups, 1):
        msg += f"{i}) {s['direction']} @ {s['entry']} | TP {s['tp']} | SL {s['sl']}\n"
    return msg

@app.route("/")
def index():
    return "US30 Trading Alert Bot is running."

if __name__ == "__main__":
    app.run(debug=True)
