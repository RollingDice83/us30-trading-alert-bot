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
/close all – alle Trades löschen
/update – Check & Statusmeldung
/openprice [Preis] – STDV Startpreis setzen
/zones – STDV Zonen anzeigen
/signals – aktuelle Signale
/resetsignals – Signal-Reset
/batch – mehrere Trades"""


def parse_signal(text):
    text_lower = text.lower()
    score = 0
    signals = []

    rsi_match = re.search(r"rsi\s*(\d{1,2}(\.\d+)?|\d{2})", text_lower)
    if rsi_match:
        value = float(rsi_match.group(1))
        if value < 30:
            score += 40
            signals.append("RSI < 30")
        elif value > 70:
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


# ... Rest bleibt unverändert
