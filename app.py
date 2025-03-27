from flask import Flask, request, jsonify
import os
import requests

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Hilfsfunktionen
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def parse_trade_command(text):
    parts = text.split()
    if len(parts) < 4:
        return None
    try:
        entry = float(parts[1].replace(',', '.'))
        sl = float(parts[2].replace(',', '.'))
        tp = float(parts[3].replace(',', '.'))
        return entry, sl, tp
    except ValueError:
        return None

def evaluate_trade_score(entry, sl, tp):
    try:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        if risk == 0:
            return 0, "Ungültiges Setup – SL ist gleich Entry."
        crv = reward / risk

        score = 50

        if crv > 2:
            score += 30
        elif crv > 1.5:
            score += 15
        elif crv < 1:
            score -= 15

        if reward > 100:
            score += 10
        elif reward > 50:
            score += 5

        if risk > 150:
            score -= 10
        elif risk < 20:
            score += 5

        reason = f"CRV: {crv:.2f}, Risiko: {risk:.1f} Punkte, Ziel: {reward:.1f} Punkte"
        return max(0, min(100, score)), reason
    except Exception as e:
        return 0, f"Fehler bei der Bewertung: {str(e)}"

def parse_close_command(text):
    try:
        parts = text.split()
        entry = float(parts[1].replace(',', '.'))
        percent = float(parts[2]) if len(parts) > 2 else 100
        return entry, percent
    except:
        return None, None

# Handler-Funktionen
def handle_trade_command(user_text, chat_id):
    result = parse_trade_command(user_text)
    if not result:
        send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade 42650 42500 43000")
        return

    entry, sl, tp = result
    score, info = evaluate_trade_score(entry, sl, tp)
    send_message(chat_id, f"📊 Trade-Analyse:\nEntry: {entry}\nSL: {sl}\nTP: {tp}\nScore: {score}/100\n🔍 {info}")

def handle_close_command(user_text, chat_id):
    entry, percent = parse_close_command(user_text)
    if entry is None:
        send_message(chat_id, "❌ Bitte gib die Position an, die du schließen willst. Beispiel: /close 42650 [optional %]")
    else:
        send_message(chat_id, f"💼 Position bei {entry} wird zu {percent}% geschlossen. (Demo-Modus)")

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
