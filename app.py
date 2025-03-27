from flask import Flask, request, jsonify
import os
import requests
import re

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Hilfsfunktionen
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def parse_trade_command(text):
    pattern = r"/trade (\w+) (long|short) (\d+(?:\.\d+)?) SL=(\d+(?:\.\d+)?) TP=(\d+(?:\.\d+)?) score=(\d+) tag=(.+)"
    match = re.match(pattern, text, re.IGNORECASE)
    if not match:
        return None
    symbol, direction, entry, sl, tp, score, tag = match.groups()
    return symbol.upper(), direction.lower(), float(entry), float(sl), float(tp), int(score), tag.strip()

def parse_close_command(text):
    pattern = r"/close (\w+) (\d+(?:\.\d+)?)(?: (\w+))?"
    match = re.match(pattern, text, re.IGNORECASE)
    if not match:
        return None, None, None
    symbol, entry, tag = match.groups()
    return symbol.upper(), float(entry), tag or ""

# Handler-Funktionen
def handle_trade_command(user_text, chat_id):
    result = parse_trade_command(user_text)
    if not result:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade US30 long 42650 SL=42500 TP=43000 score=80 tag=Breakout")
        return

    symbol, direction, entry, sl, tp, score, tag = result
    msg = f"📥 Neuer Trade-Eingang\n🔹 Symbol: {symbol}\n🔹 Richtung: {direction}\n🔹 Entry: {entry}\n🔹 SL: {sl}\n🔹 TP: {tp}\n🔹 Score: {score}/100\n🔹 Tag: {tag}"
    send_message(chat_id, msg)

def handle_close_command(user_text, chat_id):
    symbol, entry, tag = parse_close_command(user_text)
    if not symbol:
        send_message(chat_id, "❌ Bitte gib die Position an, die du schließen willst. Beispiel: /close US30 42650 profit")
    else:
        send_message(chat_id, f"💼 Position {symbol} bei {entry} wird geschlossen. Tag: {tag}")

@app.route("/")
def index():
    return "US30-Bot läuft ✅"

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

    if user_text.startswith("/status"):
        send_message(chat_id, "✅ Der US30-Bot läuft und empfängt Signale.")
    elif user_text.startswith("/help"):
        send_message(chat_id, "📘 Befehle:\n/status – zeigt den aktuellen Bot-Status\n/trade – sendet Trade-Setup\n/close – Position schließen\n/help – Hilfe anzeigen")
    elif user_text.startswith("/trade"):
        handle_trade_command(user_text, chat_id)
    elif user_text.startswith("/close"):
        handle_close_command(user_text, chat_id)
    else:
        send_message(chat_id, "❓ Unbekannter Befehl.")

    return jsonify({"status": "ok"}), 200
