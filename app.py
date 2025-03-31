import json
import re
import time
from flask import Flask, request, jsonify
import os
import sys
import requests

app = Flask(__name__)

VERSION = "v4.4"

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
    return jsonify({
        "method": "sendMessage",
        "chat_id": chat_id,
        "text": text
    })

def get_help():
    return f"""📘 Befehle ({VERSION}):
/status – offene Positionen
/trade – Setup senden
/close [Preis] – Trade schließen
/update – STDV aktualisieren
/openprice [Preis] – STDV Startpreis setzen
/zones – STDV Zonen anzeigen
/signals – aktuelle Signale
/resetsignals – Signal-Reset
/batch – mehrere Trades"""

def parse_signal(text):
    text_lower = text.lower()
    score = 0
    signals = []

    if "rsi below 30" in text_lower or "rsi crossing up 30" in text_lower:
        score += 40
        signals.append("RSI < 30")
    if "rsi above 70" in text_lower or "rsi crossing down 70" in text_lower:
        score += 20
        signals.append("RSI > 70")
    if "momentum: bullish" in text_lower:
        score += 30
        signals.append("Momentum Bullish")
    if "momentum: bearish" in text_lower:
        score += 30
        signals.append("Momentum Bearish")
    if "mss bullish break" in text_lower:
        score += 20
        signals.append("MSS Bullish Break")
    if "mss bearish break" in text_lower:
        score += 20
        signals.append("MSS Bearish Break")

    if score > 0:
        return (" + ".join(signals), score)
    return (None, 0)

def generate_trade_suggestion(reason, score):
    direction = "LONG" if "bullish" in reason.lower() or "rsi < 30" in reason.lower() else "SHORT"
    price = get_live_price()
    if not price:
        price = "(aktuell)"
    sl = round(40 + (100 - score) * 0.5)  # SL enger bei hohem Score
    tp = round(100 + score)              # TP größer bei hohem Score
    return f"🚀 Tradevorschlag (Score {score})\nTyp: {direction}\nEntry: {price}\nTrigger: {reason}\nSL: {sl} Punkte\nTP: {tp} Punkte\nTag: signal-auto\nNutze /trade um manuell zu speichern."

# (Rest des Codes bleibt unverändert)
# ...

if __name__ == "__main__":
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as e:
        print(f"❌ Fehler beim Starten des Servers: {e}", file=sys.stderr)
        sys.exit(1)
