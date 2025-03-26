from flask import Flask, request, jsonify
import requests
import json
import yfinance as yf
import threading
import time

app = Flask(__name__)

# Telegram Bot Token & Chat ID
TELEGRAM_TOKEN = "7958399333:AAEGvMvyD_MhzDT47ZMHXGmJnJ0B_vh9KdU"
TELEGRAM_CHAT_ID = "805285674"
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
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(TELEGRAM_API_URL, json=payload)

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
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"status": "no message"}), 400

    message = data["message"].get("text")
    if message:
        handle_bot_message(message.strip())
    return jsonify({"status": "ok"})

def handle_bot_message(message):
    message = message.strip()

    if message.startswith("/help"):
        return {"reply": send_help()}
    if message.startswith("/status"):
        return {"reply": send_status()}
    if message.startswith("/reset"):
        active_setups.clear()
        send_telegram_message("✅ Alle aktiven Setups wurden zurückgesetzt.")
        return {"status": "reset"}

    # Setup erkannt
    signal = parse_signal(message)
    active_setups.append(signal)
    send_telegram_message(
        f"📌 Neues US30 Setup erkannt\n➡️ Richtung: {signal['direction']}\n🎯 Entry: {signal['entry']}\n🎯 TP: {signal['tp']}\n🛑 SL: {signal['sl']}\n🎯 Entry-Typ: {signal['type']}\n📊 RSI: {signal['rsi']}\n📈 Momentum: {signal['momentum']}\n⚙️ Signalqualität: {signal['score']}/10"
    )
    return {"status": "received", "score": signal["score"]}

def send_help():
    help_text = """
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
    send_telegram_message(help_text)
    return "ok"

def send_status():
    if not active_setups:
        send_telegram_message("🚫 Keine aktiven Setups.")
        return "leer"
    msg = "📊 Aktive US30 Setups:\n"
    for i, s in enumerate(active_setups, 1):
        msg += f"{i}) {s['direction']} @ {s['entry']} | TP {s['tp']} | SL {s['sl']}\n"
    send_telegram_message(msg)
    return "ok"

@app.route("/")
def index():
    return "US30 Trading Alert Bot is running."

if __name__ == "__main__":
    app.run(debug=True)
