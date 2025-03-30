# Modul 3.2 – Kontext-Speicher, Smart Setup-Analyse & Push bei High-Score

from flask import Flask, request, jsonify
import os
import requests
import re
import datetime

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === Speicher ===
active_trades = []
signal_context = {
    "momentum_1h": None,
    "momentum_4h": None,
    "rsi": None,
    "mss": None
}

# === Funktionen ===
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

def store_context(signal):
    text = signal.lower()
    now = datetime.datetime.now().strftime("%H:%M %d.%m")

    if "momentum" in text:
        if "1h" in text:
            signal_context["momentum_1h"] = text + f" ({now})"
        elif "4h" in text:
            signal_context["momentum_4h"] = text + f" ({now})"
    elif "rsi" in text:
        signal_context["rsi"] = text + f" ({now})"
    elif "mss" in text:
        signal_context["mss"] = text + f" ({now})"

    check_and_suggest_trade()

def check_and_suggest_trade():
    m = signal_context["momentum_1h"]
    r = signal_context["rsi"]
    s = signal_context["mss"]

    if m and r and s:
        if "bullish" in m and "crossing up 30" in r and "bullish" in s:
            score = 93
            suggestion = f"🚀 Long-Signal erkannt!\nScore: {score}/100\n\n• {m}\n• {r}\n• {s}\n\n👉 Vorschlag:\n/trade US30 long 42500 SL=42200 TP=43200 score={score} tag=AutoSignal"
            send_message(TELEGRAM_CHAT_ID, suggestion)

        elif "bearish" in m and "crossing down 70" in r and "bearish" in s:
            score = 90
            suggestion = f"📉 Short-Signal erkannt!\nScore: {score}/100\n\n• {m}\n• {r}\n• {s}\n\n👉 Vorschlag:\n/trade US30 short 42950 SL=43200 TP=42150 score={score} tag=AutoSignal"
            send_message(TELEGRAM_CHAT_ID, suggestion)

# === Webhook-Empfang ===
@app.route("/webhook", methods=["POST"])
def receive_webhook():
    data = request.get_json()
    message = data.get("message", "").strip()
    if not message:
        return jsonify({"status": "ignored"}), 200

    store_context(message)
    return jsonify({"status": "ok"}), 200

# === Übersichtskommando ===
@app.route("/signalstatus", methods=["GET"])
def signal_status():
    msg = "🧠 Aktueller Signal-Kontext:\n"
    for k, v in signal_context.items():
        msg += f"• {k}: {v or '❌ Kein aktives Signal'}\n"
    return msg, 200

@app.route("/")
def index():
    return "Modul 3.2 Smart Signal Engine aktiv ✅"

if __name__ == "__main__":
    app.run(debug=True)
