import json
import re
import time
from flask import Flask, request, jsonify
import os
import sys
import requests

app = Flask(__name__)

VERSION = "v4.5"

active_trades = []
signal_memory = []
open_price = None

def get_live_price():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/US30USD=X?interval=1m&range=1d"
        res = requests.get(url)
        data = res.json()
        price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
        return round(price, 2)
    except:
        return None

@app.route("/", methods=["GET"])
def home():
    return "US30 Bot Live"

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.json
    if not data or "message" not in data:
        return jsonify(ok=True)

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if text.lower().startswith("/help"):
        return send_message(chat_id, get_help())
    elif text.lower().startswith("/status"):
        return send_message(chat_id, format_status())
    elif text.lower().startswith("/trade"):
        return handle_trade(text, chat_id)
    elif text.lower().startswith("/batch"):
        return handle_batch(text, chat_id)
    elif text.lower().startswith("/openprice"):
        return handle_open_price(text, chat_id)
    elif text.lower().startswith("/resetsignals"):
        signal_memory.clear()
        return send_message(chat_id, "♻️ Signal-Speicher geleert.")
    elif text.lower().startswith("/signals"):
        return send_message(chat_id, format_signals())
    elif text.lower().startswith("/zones"):
        return send_message(chat_id, format_zones())
    elif text.lower().startswith("/close"):
        return handle_close(text, chat_id)
    elif text.lower().startswith("/update"):
        return send_message(chat_id, f"🔄 Update erhalten ({VERSION}) – alle Systeme aktiv.")

    parsed, score = parse_signal(text)
    if parsed:
        signal_memory.append(f"{parsed} [{time.strftime('%H:%M:%S')}] (Score {score})")
        if score >= 60:
            return send_message(chat_id, generate_trade_suggestion(parsed, score))
        else:
            return send_message(chat_id, f"✅ Signal erkannt: {parsed} (Score {score})")

    return send_message(chat_id, "❌ Unbekannter Befehl. Nutze /help für alle Kommandos.")

def send_message(chat_id, text):
    print(f"SEND TO {chat_id}: {text}")
    return jsonify({"method": "sendMessage", "chat_id": chat_id, "text": text})

def get_help():
    return f"""📘 Befehle ({VERSION}):
/status – offene Positionen
/trade – Setup senden
/close [Preis] – Trade schließen
/close all – alle Trades löschen
/update – Check & Statusmeldung
/openprice [Preis] – STDV Startpreis setzen
/zones – STDV Zonen anzeigen
/signals – aktuelle Signale
/resetsignals – Signal-Reset
/batch – mehrere Trades"""

def handle_trade(text, chat_id):
    match = re.match(r'/trade (long|short) (\d+) SL=(\d+) TP=(\d+)', text, re.I)
    if not match:
        return send_message(chat_id, "❌ Ungültiges Format. Beispiel: /trade long 42500 SL=42250 TP=43200")
    direction, entry, sl, tp = match.groups()
    active_trades.append({"type": direction.lower(), "entry": float(entry), "sl": float(sl), "tp": float(tp), "tag": "manual"})
    return send_message(chat_id, f"✅ {direction.upper()} Trade @ {entry} gespeichert.")

def handle_batch(text, chat_id):
    return send_message(chat_id, "⚙️ Batch-Funktion in Bearbeitung.")

def handle_open_price(text, chat_id):
    global open_price
    match = re.match(r'/openprice (\d+(\.\d+)?)', text)
    if not match:
        return send_message(chat_id, "❌ Beispiel: /openprice 44100")
    open_price = float(match.group(1))
    return send_message(chat_id, f"📍 Opening Price gesetzt: {open_price}")

def format_status():
    if not active_trades:
        return "ℹ️ Keine aktiven Positionen."
    msg = "📈 Aktive Positionen:\n"
    for t in active_trades:
        msg += f"{t['type'].capitalize()} @ {t['entry']} TP: {t['tp']} SL: {t['sl']}\n"
    return msg

def handle_close(text, chat_id):
    if text.strip().lower() == "/close all":
        active_trades.clear()
        return send_message(chat_id, "✅ Alle Positionen wurden gelöscht.")
    match = re.match(r'/close (\d+)', text)
    if not match:
        return send_message(chat_id, "❌ Beispiel: /close 42500")
    price = float(match.group(1))
    active_trades[:] = [t for t in active_trades if t["entry"] != price]
    return send_message(chat_id, f"✅ Position bei {price} gelöscht.")

def format_zones():
    return f"📊 STDV-Zonen: [Platzhalter, Open Price: {open_price}]"

def format_signals():
    if not signal_memory:
        return "📡 Keine aktiven Signale."
    return "📡 Signale:\n" + "\n".join(signal_memory)

# parse_signal und generate_trade_suggestion unverändert beibehalten

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
