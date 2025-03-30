from flask import Flask, request, jsonify
import os
import requests
import re
import datetime
import json

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

MEMORY_FILE = "us30_memory.json"

# Load + Save Persistent Memory
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)
    return {"active_trades": [], "stdv_zones": {}, "signals": {}}

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

memory = load_memory()

# Telegram Nachricht senden
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

# Signal speichern
def append_signal(key):
    now = datetime.datetime.utcnow().isoformat()
    memory["signals"][key] = now
    save_memory(memory)

# Signal-Speicher zurücksetzen
def reset_signals():
    memory["signals"] = {}
    save_memory(memory)

# Score berechnen aus gesammelten Signalen
def calculate_score():
    score = 0
    signals = memory.get("signals", {})
    now = datetime.datetime.utcnow()

    def is_recent(signal_time, minutes=60):
        try:
            dt = datetime.datetime.fromisoformat(signal_time)
            return (now - dt).total_seconds() < minutes * 60
        except:
            return False

    if is_recent(signals.get("momentum_bullish_1h")):
        score += 30
    if is_recent(signals.get("rsi_below_30")):
        score += 20
    if is_recent(signals.get("mss_bullish_1h")):
        score += 30
    if is_recent(signals.get("stdv_zone_hit")):
        score += 10

    return score

# Webhook-Signale analysieren
def handle_webhook_signal(text):
    lower = text.lower()

    if "momentum: bullish 1h" in lower:
        append_signal("momentum_bullish_1h")
        send_message(TELEGRAM_CHAT_ID, "📈 Momentum Bullish 1h erkannt.")
    elif "rsi below 30" in lower:
        append_signal("rsi_below_30")
        send_message(TELEGRAM_CHAT_ID, "📉 RSI unter 30 erkannt.")
    elif "mss bullish break" in lower:
        append_signal("mss_bullish_1h")
        send_message(TELEGRAM_CHAT_ID, "📊 Strukturbruch Bullish 1h erkannt.")
    elif "stdv zone" in lower:
        append_signal("stdv_zone_hit")
        send_message(TELEGRAM_CHAT_ID, "📍 Preis an STDV-Zone erkannt.")

    score = calculate_score()
    if score >= 70:
        msg = f"🎯 Smart Signal erkannt!\nUS30 Long?\nScore: {score}/100\nSL: optional | TP: optional\nTag: Breakout/Pullback"
        send_message(TELEGRAM_CHAT_ID, msg)

# Webhook + Telegram Entry
@app.route("/telegram", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Kein JSON erhalten"}), 400

    message = data.get("message", {})
    if not message:
        return jsonify({"status": "ok"}), 200

    user_text = message.get("text", "")
    chat_id = message["chat"]["id"]

    if user_text.startswith("/resetsignals"):
        reset_signals()
        send_message(chat_id, "♻️ Signal-Speicher wurde zurückgesetzt.")
    elif user_text.lower().startswith(("momentum", "rsi", "mss", "stdv")):
        handle_webhook_signal(user_text)
    elif user_text.startswith("/help"):
        send_message(chat_id, "📘 Befehle:\n/status – offene Positionen\n/trade – Trade-Setup\n/close – Position schließen\n/resetsignals – Signal-Speicher leeren\n/help – Hilfe")
    else:
        send_message(chat_id, "❓ Unbekannter Befehl.")

    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return "US30-Bot Modul 3.4 ✅ aktiv"
