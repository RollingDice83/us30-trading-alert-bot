from flask import Flask, request, jsonify
import os
import requests
import re
from datetime import datetime
import math

app = Flask(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Speicher
active_trades = []
open_price = None
stdv_zones = []

# ✉️ Telegram-Sendung
def send_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

# 📥 STDV-Berechnung
def set_stdv_zones(base_price):
    global stdv_zones
    stdv_zones = []
    for i in range(1, 6):
        stdv_zones.append(round(base_price * (1 + i / 100), 2))
        stdv_zones.append(round(base_price * (1 - i / 100), 2))

# 📥 /OpenPrice 44100
def handle_open_price(text, chat_id):
    global open_price
    try:
        value = float(text.split(" ")[1])
        open_price = value
        set_stdv_zones(open_price)
        send_message(chat_id, f"✅ Opening Price gesetzt auf {open_price}. STDV-Zonen berechnet.")
    except:
        send_message(chat_id, "⚠️ Ungültiger Befehl. Beispiel: /OpenPrice 44100")

# 📊 /zones
def handle_zones(chat_id):
    if not open_price:
        send_message(chat_id, "ℹ️ Kein Opening Price gesetzt.")
        return
    zones = "\n".join([f"{'-' if z < open_price else '+'}{round(abs(z - open_price) / open_price * 100)}% → {z}" for z in sorted(stdv_zones)])
    send_message(chat_id, f"📈 Aktive STDV-Zonen (Basis {open_price}):\n{zones}")

# 🧠 /update 42000 SL=41800 TP=42600 tag=Pullback
def handle_update_command(text, chat_id):
    pattern = r"/update (?P<entry>\d+(?:\.\d+)?)(?:.*?SL=(?P<sl>\d+(?:\.\d+)?))?(?:.*?TP=(?P<tp>\d+(?:\.\d+)?))?(?:.*?tag=(?P<tag>[^\n]+))?"
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        send_message(chat_id, "❌ Ungültiger Format. Beispiel: /update 42600 SL=42400 TP=43000 tag=Breakout")
        return
    data = match.groupdict()
    entry = float(data["entry"])
    updated = False
    for trade in active_trades:
        if trade["entry"] == entry:
            if data["sl"]: trade["sl"] = float(data["sl"])
            if data["tp"]: trade["tp"] = float(data["tp"])
            if data["tag"]: trade["tag"] = data["tag"]
            updated = True
            break
    if updated:
        send_message(chat_id, f"🔄 Trade bei {entry} aktualisiert.")
    else:
        send_message(chat_id, f"⚠️ Kein Trade gefunden bei {entry}.")

# 📤 STDV-Test → Trigger Alerts
def check_stdv_trigger(price, chat_id):
    for zone in stdv_zones:
        diff = abs(price - zone)
        if diff < 10:  # Schwelle, anpassbar
            perc = round(abs(price - open_price) / open_price * 100, 2)
            direction = "Pullback" if price < open_price else "Hedge"
            send_message(chat_id, f"🚨 STDV-Zone {perc}% erreicht → Vorschlag: {direction}-Setup prüfen (Level: {zone})")

# 📋 Bisherige Funktionen (Status, Help, Trade, Close) unverändert…
# ➕ Nur ergänzen:
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

    if user_text.startswith("/OpenPrice"):
        handle_open_price(user_text, chat_id)
    elif user_text.startswith("/zones"):
        handle_zones(chat_id)
    elif user_text.startswith("/update"):
        handle_update_command(user_text, chat_id)
    # ⬇️ Restliche Commands wie /trade, /status, /close etc...
    elif user_text.startswith("/help"):
        send_message(chat_id, "📘 Befehle:\n/status – Offene Trades\n/trade – Einzel-Trade\n/batch – Multi-Trades\n/update – SL/TP/Tag ändern\n/OpenPrice – Setze Opening Preis\n/zones – STDV-Zonen anzeigen\n/help – Diese Hilfe\n\n🔁 Version: Modul 3.3")
    else:
        send_message(chat_id, "❓ Unbekannter Befehl.")

    return jsonify({"status": "ok"}), 200
